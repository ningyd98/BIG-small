#!/usr/bin/env python
"""Phase 10.2B 控制台验收验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PHASE10_2B_CONSOLE_ACCEPTED = "PHASE10_2B_CONSOLE_ACCEPTED"


@dataclass(frozen=True)
class VerificationCommand:
    name: str
    argv: list[str]
    cwd: Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 10.2B dashboard console.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10/phase10_2b"))
    parser.add_argument("--backend-only", action="store_true", help="Run backend-safe checks only.")
    parser.add_argument("--skip-e2e", action="store_true", help="Skip browser E2E checks.")
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    backend = verify_backend(repo)
    frontend = (
        skipped_section("frontend", "backend-only") if args.backend_only else verify_frontend(repo)
    )
    if args.backend_only or args.skip_e2e:
        e2e = skipped_section("e2e", "backend-only" if args.backend_only else "skip-e2e")
    else:
        e2e = verify_e2e(repo)
    summary = build_summary_payload(backend=backend, frontend=frontend, e2e=e2e)
    write_artifacts(args.output, backend=backend, frontend=frontend, e2e=e2e, summary=summary)
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0 if _section_gate_passed(backend, frontend, e2e) else 1


def verify_backend(repo: Path) -> dict[str, Any]:
    commands = [
        VerificationCommand(
            "dashboard-backend-tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_phase10_2b_dashboard_backend.py",
                "tests/test_phase10_2b_dashboard_websocket.py",
                "tests/test_phase10_2b_acceptance_contract.py",
                "-q",
            ],
            repo,
        )
    ]
    payload = run_commands(commands)
    payload["checks"] = {
        "evidence_path_security": _test_contains(
            repo, "test_evidence_index_rejects_path_traversal"
        ),
        "experiment_runner_allowlist": _file_contains(
            repo / "src/cloud_edge_robot_arm/dashboard/experiment_jobs.py", "allowlist"
        ),
        "websocket_auth_replay": _file_contains(
            repo / "src/cloud_edge_robot_arm/cloud/api/dashboard.py", "last_sequence"
        ),
        "no_hardware_route": _file_contains_without_spaces(
            repo / "src/cloud_edge_robot_arm/dashboard/service.py", "hardware_write_operations=[]"
        ),
        "real_robot_not_started": _file_contains(
            repo / "src/cloud_edge_robot_arm/dashboard/service.py",
            'real_robot_validation="NOT_STARTED"',
        ),
        "hardware_level_none": _file_contains(
            repo / "src/cloud_edge_robot_arm/dashboard/service.py",
            'highest_acceptance_level="NONE"',
        ),
    }
    payload["real_controller_contacted"] = False
    payload["hardware_motion_observed"] = False
    payload["highest_acceptance_level"] = "NONE"
    return payload


def verify_frontend(repo: Path) -> dict[str, Any]:
    dashboard = repo / "dashboard"
    commands = [
        VerificationCommand("dashboard-openapi-drift", ["npm", "run", "api:check"], dashboard),
        VerificationCommand("dashboard-format", ["npm", "run", "format:check"], dashboard),
        VerificationCommand("dashboard-lint", ["npm", "run", "lint"], dashboard),
        VerificationCommand("dashboard-typecheck", ["npm", "run", "typecheck"], dashboard),
        VerificationCommand("dashboard-unit-tests", ["npm", "run", "test"], dashboard),
        VerificationCommand("dashboard-build", ["npm", "run", "build"], dashboard),
    ]
    payload = run_commands(commands)
    payload["openapi_path_count"] = _openapi_path_count(
        dashboard / "src/api/generated/openapi.json"
    )
    payload["vite_chunk_warning"] = (
        "manualChunks configured; chunk warning is non-blocking if emitted"
    )
    return payload


def verify_e2e(repo: Path) -> dict[str, Any]:
    dashboard = repo / "dashboard"
    payload = run_commands([VerificationCommand("dashboard-e2e", ["npm", "run", "e2e"], dashboard)])
    spec = (dashboard / "tests/e2e/console.spec.ts").read_text(encoding="utf-8")
    payload["playwright_test_count"] = spec.count("test(")
    payload["uses_real_fastapi"] = "page.route(" not in spec and "uvicorn" in (
        dashboard / "playwright.config.ts"
    ).read_text(encoding="utf-8")
    return payload


def run_commands(commands: list[VerificationCommand]) -> dict[str, Any]:
    results: list[dict[str, object]] = []
    for command in commands:
        repo = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            command.argv,
            cwd=command.cwd,
            check=False,
            text=True,
            capture_output=True,
            timeout=900,
        )
        passed = result.returncode == 0
        results.append(
            {
                "name": command.name,
                "argv": _redact_argv(command.argv, repo=repo),
                "cwd": _relative_cwd(command.cwd, repo=repo),
                "returncode": result.returncode,
                "status": "PASSED" if passed else "FAILED",
                "stdout_tail": _redact_text(result.stdout[-4000:], repo=repo),
                "stderr_tail": _redact_text(result.stderr[-4000:], repo=repo),
            }
        )
        if not passed:
            break
    return {
        "status": "PASSED" if all(item["status"] == "PASSED" for item in results) else "FAILED",
        "commands": results,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def build_summary_payload(
    *, backend: dict[str, Any], frontend: dict[str, Any], e2e: dict[str, Any]
) -> dict[str, Any]:
    required_sections = [backend]
    if frontend["status"] != "SKIPPED":
        required_sections.append(frontend)
    if e2e["status"] != "SKIPPED":
        required_sections.append(e2e)
    accepted = (
        frontend["status"] == "PASSED"
        and e2e["status"] == "PASSED"
        and all(section["status"] == "PASSED" for section in required_sections)
    )
    return {
        "status": _summary_status(frontend=frontend, e2e=e2e, accepted=accepted),
        "validation_claimed": accepted,
        "backend_status": backend["status"],
        "frontend_status": frontend["status"],
        "e2e_status": e2e["status"],
        "playwright_test_count": e2e.get("playwright_test_count", 0),
        "uses_real_fastapi": bool(e2e.get("uses_real_fastapi", False)),
        "openapi_path_count": int(frontend.get("openapi_path_count", 0)),
        "real_robot_validation": "NOT_STARTED",
        "highest_acceptance_level": "NONE",
        "hardware_motion_authorized": False,
        "hardware_motion_observed": False,
        "real_controller_contacted": False,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _summary_status(*, frontend: dict[str, Any], e2e: dict[str, Any], accepted: bool) -> str:
    if accepted:
        return PHASE10_2B_CONSOLE_ACCEPTED
    if frontend["status"] == "SKIPPED" or e2e["status"] == "SKIPPED":
        return "PHASE10_2B_PARTIAL_VERIFICATION"
    return "PHASE10_2B_CONSOLE_FAILED"


def _section_gate_passed(
    backend: dict[str, Any], frontend: dict[str, Any], e2e: dict[str, Any]
) -> bool:
    return all(section["status"] in {"PASSED", "SKIPPED"} for section in (backend, frontend, e2e))


def write_artifacts(
    output: Path,
    *,
    backend: dict[str, Any],
    frontend: dict[str, Any],
    e2e: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for filename, payload in (
        ("backend_verification.json", backend),
        ("frontend_verification.json", frontend),
        ("e2e_verification.json", e2e),
        ("phase10_2b_summary.json", summary),
    ):
        (output / filename).write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )


def skipped_section(name: str, reason: str) -> dict[str, Any]:
    return {
        "status": "SKIPPED",
        "section": name,
        "reason": reason,
        "commands": [],
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _openapi_path_count(path: Path) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    paths = payload.get("paths", {})
    return len(paths) if isinstance(paths, dict) else 0


def _file_contains(path: Path, text: str) -> str:
    return "PASSED" if text in path.read_text(encoding="utf-8") else "FAILED"


def _file_contains_without_spaces(path: Path, text: str) -> str:
    content = path.read_text(encoding="utf-8").replace(" ", "")
    return "PASSED" if text in content else "FAILED"


def _test_contains(repo: Path, text: str) -> str:
    return _file_contains(repo / "tests/test_phase10_2b_dashboard_backend.py", text)


def _redact_argv(argv: list[str], *, repo: Path) -> list[str]:
    redacted: list[str] = []
    for index, item in enumerate(argv):
        if index == 0 and Path(item).is_absolute():
            redacted.append(Path(item).name)
            continue
        redacted.append(_redact_text(item, repo=repo))
    return redacted


def _relative_cwd(cwd: Path, *, repo: Path) -> str:
    try:
        return cwd.resolve().relative_to(repo.resolve()).as_posix() or "."
    except ValueError:
        return "<external>"


def _redact_text(text: str, *, repo: Path) -> str:
    return text.replace(str(repo), "<repo>")


if __name__ == "__main__":
    raise SystemExit(main())
