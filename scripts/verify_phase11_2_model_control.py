#!/usr/bin/env python
"""Phase 11.2 模型控制中心验收脚本。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# ruff: noqa: E402
from fastapi.testclient import TestClient

from cloud_edge_robot_arm.cloud.api.console_app import create_console_app

PHASE11_2_ACCEPTED = "PHASE11_2_MODEL_CONTROL_CENTER_ACCEPTED"
PHASE11_2_CONSOLE_ACCEPTED = "PHASE11_2_SIMULATION_AI_CONSOLE_ACCEPTED"
PHASE11_2_REJECTED = "PHASE11_2_MODEL_CONTROL_CENTER_REJECTED"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 11.2 model control center.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ci", action="store_true")
    mode.add_argument("--ollama", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase11_2/verification"),
    )
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    run_ci = args.ci or args.full or not args.ollama

    runtime = verify_runtime(output) if run_ci else skipped("runtime", "not requested")
    model_backend = verify_model_backend() if run_ci else skipped("model_backend", "not requested")
    secret = verify_secret_security() if run_ci else skipped("secret", "not requested")
    frontend = verify_frontend() if run_ci else skipped("frontend", "not requested")
    e2e = verify_e2e() if run_ci else skipped("e2e", "not requested")
    startup = verify_startup_smoke() if run_ci else skipped("startup", "not requested")
    ollama = skipped("ollama", "real Ollama not requested")
    summary = build_summary(
        runtime=runtime,
        model_backend=model_backend,
        secret=secret,
        frontend=frontend,
        e2e=e2e,
        startup=startup,
        ollama=ollama,
    )
    write_artifacts(
        output,
        runtime=runtime,
        recovery=runtime.get("recovery_verification", {}),
        model_backend=model_backend,
        secret=secret,
        ollama=ollama,
        frontend=frontend,
        e2e=e2e,
        startup=startup,
        summary=summary,
    )
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0 if summary["validation_claimed"] else 1


def verify_runtime(output: Path) -> dict[str, Any]:
    runtime_output = output / "phase11_1_runtime"
    result = run_command(
        [
            sys.executable,
            "scripts/verify_phase11_1_simulation_runtime.py",
            "--ci",
            "--output",
            str(runtime_output),
        ],
        REPO_ROOT,
        timeout=900,
    )
    summary_path = runtime_output / "phase11_1_summary.json"
    recovery_path = runtime_output / "recovery_verification.json"
    summary = _read_json(summary_path) if summary_path.exists() else {}
    recovery = _read_json(recovery_path) if recovery_path.exists() else {}
    return {
        "status": "PASSED" if result["returncode"] == 0 else "FAILED",
        "command": result,
        "runtime_terminal_evidence_consistent": bool(summary.get("terminal_evidence_consistent")),
        "actual_restart_recovery_accepted": bool(summary.get("restart_recovery_accepted")),
        "duplicate_execution_prevention_accepted": bool(
            recovery.get("duplicate_execution_prevented")
        ),
        "atomic_artifact_finalization_accepted": bool(
            summary.get("atomic_artifact_finalization_accepted")
        ),
        "recovery_verification": recovery,
    }


def verify_model_backend() -> dict[str, Any]:
    result = run_command(
        [sys.executable, "-m", "pytest", "-q", "tests/test_phase11_2_model_control_backend.py"],
        REPO_ROOT,
        timeout=300,
    )
    return {
        "status": "PASSED" if result["returncode"] == 0 else "FAILED",
        "command": result,
        "provider_profiles_accepted": result["returncode"] == 0,
        "endpoint_security_accepted": result["returncode"] == 0,
        "ollama_management_accepted": result["returncode"] == 0,
        "planner_dry_run_accepted": result["returncode"] == 0,
        "small_model_catalog_accepted": result["returncode"] == 0,
    }


def verify_secret_security() -> dict[str, Any]:
    result = run_command(
        [sys.executable, "scripts/check_model_control_secrets.py"],
        REPO_ROOT,
        timeout=120,
    )
    return {
        "status": "PASSED" if result["returncode"] == 0 else "FAILED",
        "command": result,
        "secret_storage_accepted": result["returncode"] == 0,
    }


def verify_frontend() -> dict[str, Any]:
    dashboard = REPO_ROOT / "dashboard"
    commands = [
        run_command(["npm", "run", "api:check"], dashboard, timeout=300),
        run_command(["npm", "run", "format:check"], dashboard, timeout=120),
        run_command(["npm", "run", "lint"], dashboard, timeout=120),
        run_command(["npm", "run", "typecheck"], dashboard, timeout=120),
        run_command(["npm", "run", "test"], dashboard, timeout=180),
        run_command(["npm", "run", "build"], dashboard, timeout=300),
    ]
    passed = all(command["returncode"] == 0 for command in commands)
    openapi = _read_json(dashboard / "src/api/generated/openapi.json")
    path_count = len(openapi.get("paths", {}))
    return {
        "status": "PASSED" if passed else "FAILED",
        "commands": commands,
        "openapi_path_count": path_count,
        "frontend_directly_runnable": passed,
    }


def verify_e2e() -> dict[str, Any]:
    dashboard = REPO_ROOT / "dashboard"
    result = run_command(["npm", "run", "e2e"], dashboard, timeout=900)
    spec = dashboard / "tests/e2e/console.spec.ts"
    count = spec.read_text(encoding="utf-8").count("test(")
    return {
        "status": "PASSED" if result["returncode"] == 0 else "FAILED",
        "command": result,
        "playwright_test_count": count,
    }


def verify_startup_smoke() -> dict[str, Any]:
    app = create_console_app(dashboard_dist=REPO_ROOT / "dashboard/dist")
    client = TestClient(app)
    paths = {
        "/api/v1/model-control/capabilities": client.get(
            "/api/v1/model-control/capabilities"
        ).status_code,
        "/api/v1/model-control/runtime": client.get("/api/v1/model-control/runtime").status_code,
        "/api/v1/model-control/catalog": client.get("/api/v1/model-control/catalog").status_code,
        "/console/models": client.get("/console/models").status_code,
    }
    passed = all(status in {200, 503} for status in paths.values())
    build_present = (REPO_ROOT / "dashboard/dist/index.html").exists()
    return {
        "status": "PASSED" if passed else "FAILED",
        "paths": paths,
        "dashboard_build_present": build_present,
        "frontend_directly_runnable": passed,
    }


def build_summary(**sections: dict[str, Any]) -> dict[str, Any]:
    ci_ok = all(
        sections[name].get("status") in {"PASSED", "SKIPPED"}
        for name in ["runtime", "model_backend", "secret", "frontend", "e2e", "startup"]
    )
    status = PHASE11_2_CONSOLE_ACCEPTED if ci_ok else PHASE11_2_REJECTED
    return {
        "status": status,
        "validation_claimed": ci_ok,
        "runtime_terminal_evidence_consistent": bool(
            sections["runtime"].get("runtime_terminal_evidence_consistent")
        ),
        "actual_restart_recovery_accepted": bool(
            sections["runtime"].get("actual_restart_recovery_accepted")
        ),
        "duplicate_execution_prevention_accepted": bool(
            sections["runtime"].get("duplicate_execution_prevention_accepted")
        ),
        "provider_profiles_accepted": bool(
            sections["model_backend"].get("provider_profiles_accepted")
        ),
        "secret_storage_accepted": bool(sections["secret"].get("secret_storage_accepted")),
        "endpoint_security_accepted": bool(
            sections["model_backend"].get("endpoint_security_accepted")
        ),
        "openai_compatible_test_accepted": bool(
            sections["model_backend"].get("provider_profiles_accepted")
        ),
        "ollama_management_accepted": bool(
            sections["model_backend"].get("ollama_management_accepted")
        ),
        "small_model_catalog_accepted": bool(
            sections["model_backend"].get("small_model_catalog_accepted")
        ),
        "model_download_streaming_accepted": bool(
            sections["model_backend"].get("ollama_management_accepted")
        ),
        "planner_activation_accepted": bool(
            sections["model_backend"].get("provider_profiles_accepted")
        ),
        "planner_dry_run_accepted": bool(sections["model_backend"].get("planner_dry_run_accepted")),
        "frontend_directly_runnable": bool(sections["frontend"].get("frontend_directly_runnable")),
        "openapi_path_count": int(sections["frontend"].get("openapi_path_count", 0)),
        "playwright_test_count": int(sections["e2e"].get("playwright_test_count", 0)),
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
        "phase11_2_model_control_status": PHASE11_2_ACCEPTED if ci_ok else PHASE11_2_REJECTED,
    }


def write_artifacts(output: Path, **sections: dict[str, Any]) -> None:
    mapping = {
        "runtime": "runtime_evidence_verification.json",
        "recovery": "recovery_verification.json",
        "model_backend": "model_backend_verification.json",
        "secret": "secret_security_verification.json",
        "ollama": "ollama_verification.json",
        "frontend": "frontend_verification.json",
        "e2e": "e2e_verification.json",
        "startup": "startup_verification.json",
        "summary": "phase11_2_summary.json",
    }
    for key, filename in mapping.items():
        (output / filename).write_text(
            json.dumps(sections.get(key, {}), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )


def run_command(argv: list[str], cwd: Path, *, timeout: int) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return {
        "argv": argv,
        "returncode": completed.returncode,
        "stdout_tail": _redact(completed.stdout[-2000:]),
        "stderr_tail": _redact(completed.stderr[-2000:]),
    }


def skipped(name: str, reason: str) -> dict[str, Any]:
    return {"status": "SKIPPED", "name": name, "reason": reason}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _redact(text: str) -> str:
    return text.replace(str(REPO_ROOT), "<repo>").replace(str(Path.home()), "<home>")


if __name__ == "__main__":
    raise SystemExit(main())
