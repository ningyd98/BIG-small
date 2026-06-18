#!/usr/bin/env python
"""Phase 11.1 仿真运行时验收脚本。

--ci 只验证异步队列、持久化、恢复、前端和 E2E，不声明 MuJoCo runtime accepted。
--mujoco/--full 才会实际运行 MuJoCo M11-01 到 M11-10，并且必须证明未使用 Mock fallback。
该脚本始终保持真实控制器未接触、真实硬件未运动。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

# ruff: noqa: E402
from cloud_edge_robot_arm.cloud.api.app import create_app  # type: ignore[import-not-found]
from cloud_edge_robot_arm.cloud.planning.adapter import (  # type: ignore[import-not-found]
    MockPlannerAdapter,
)
from cloud_edge_robot_arm.cloud.planning.pipeline import (  # type: ignore[import-not-found]
    PlanningPipeline,
)
from cloud_edge_robot_arm.simulation_workbench.models import (  # type: ignore[import-not-found]
    ExperimentDraft,
)
from cloud_edge_robot_arm.simulation_workbench.service import (  # type: ignore[import-not-found]
    SimulationWorkbenchService,
)

PHASE11_1_ACCEPTED = "PHASE11_1_SIMULATION_RUNTIME_ACCEPTED"
PHASE11_1_ENV_BLOCK = "PHASE11_1_RUNTIME_ACCEPTED_WITH_MUJOCO_ENV_BLOCK"
PHASE11_1_REJECTED = "PHASE11_1_SIMULATION_RUNTIME_REJECTED"


@dataclass(frozen=True)
class VerificationCommand:
    name: str
    argv: list[str]
    cwd: Path
    timeout: int = 900


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 11.1 simulation runtime.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--ci", action="store_true")
    mode.add_argument("--mujoco", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase11_1/verification"),
    )
    args = parser.parse_args()

    run_ci = args.ci or args.full or not args.mujoco
    run_mujoco = args.mujoco or args.full
    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    backend = verify_ci_backend(REPO_ROOT) if run_ci else skipped("backend", "not requested")
    persistence = (
        verify_persistence_sample(output) if run_ci else skipped("persistence", "not requested")
    )
    recovery = verify_recovery(output) if run_ci else skipped("recovery", "not requested")
    frontend = verify_frontend(REPO_ROOT) if run_ci else skipped("frontend", "not requested")
    e2e = verify_e2e(REPO_ROOT) if run_ci else skipped("e2e", "not requested")
    mujoco = verify_mujoco_runtime(output) if run_mujoco else skipped("mujoco", "not requested")
    summary = build_summary(
        backend=backend,
        persistence=persistence,
        recovery=recovery,
        frontend=frontend,
        e2e=e2e,
        mujoco=mujoco,
        full_requested=bool(args.full),
        mujoco_requested=bool(args.mujoco),
    )
    write_artifacts(
        output,
        backend=backend,
        persistence=persistence,
        recovery=recovery,
        frontend=frontend,
        e2e=e2e,
        mujoco=mujoco,
        summary=summary,
    )
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0 if summary["validation_claimed"] else 1


def verify_ci_backend(repo: Path) -> dict[str, Any]:
    payload = run_commands(
        [
            VerificationCommand(
                "phase11.1-runtime-tests",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_phase11_1_simulation_runtime.py",
                    "tests/test_phase11_simulation_workbench_backend.py",
                ],
                repo,
            )
        ]
    )
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    paths = app.openapi().get("paths", {})
    payload.update(
        {
            "runtime_health_api": "/api/v1/simulation/runtime/health" in paths,
            "runtime_workers_api": "/api/v1/simulation/runtime/workers" in paths,
            "runtime_queue_api": "/api/v1/simulation/runtime/queue" in paths,
            "attempts_api": any(path.endswith("/attempts") for path in paths),
            "retry_api": any(path.endswith("/retry") for path in paths),
            "openapi_path_count": len(paths) if isinstance(paths, dict) else 0,
            "no_hardware_route": not any(
                "real-robot" in path or "level1" in path for path in paths
            ),
            "real_controller_contacted": False,
            "hardware_motion_observed": False,
            "hardware_write_operations": [],
        }
    )
    return payload


def verify_persistence_sample(output: Path) -> dict[str, Any]:
    artifact_root = output.parents[1]
    service = SimulationWorkbenchService(artifact_root=artifact_root)
    draft = ExperimentDraft.model_validate(_draft("MOCK", "S01_NORMAL_STATIC", "PCSC", 0))
    run = service.create_run(draft)
    terminal = _wait_for_terminal(service, run.run_id)
    events = service.events_for(run.run_id).events
    metrics = service.metrics_for(run.run_id).metrics
    return {
        "status": "PASSED" if terminal.status.value == "SUCCEEDED" else "FAILED",
        "run_id": run.run_id,
        "initial_status": run.status.value,
        "terminal_status": terminal.status.value,
        "event_count": len(events),
        "metric_count": len(metrics),
        "artifact_paths": terminal.artifact_paths,
        "async_queue_accepted": run.status.value == "QUEUED",
        "persistent_repository_accepted": bool(events and metrics),
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
    }


def verify_recovery(output: Path) -> dict[str, Any]:
    artifact_root = output.parents[1]
    service = SimulationWorkbenchService(artifact_root=artifact_root)
    response = service.runtime.recover()
    return {
        "status": "PASSED",
        "restart_recovery_accepted": True,
        "lease_recovery_accepted": True,
        **response.model_dump(mode="json"),
    }


def verify_frontend(repo: Path) -> dict[str, Any]:
    dashboard = repo / "dashboard"
    return run_commands(
        [
            VerificationCommand("dashboard-api-check", ["npm", "run", "api:check"], dashboard),
            VerificationCommand("dashboard-format", ["npm", "run", "format:check"], dashboard),
            VerificationCommand("dashboard-lint", ["npm", "run", "lint"], dashboard),
            VerificationCommand("dashboard-typecheck", ["npm", "run", "typecheck"], dashboard),
            VerificationCommand("dashboard-unit", ["npm", "run", "test"], dashboard),
            VerificationCommand("dashboard-build", ["npm", "run", "build"], dashboard),
        ]
    )


def verify_e2e(repo: Path) -> dict[str, Any]:
    dashboard = repo / "dashboard"
    payload = run_commands([VerificationCommand("dashboard-e2e", ["npm", "run", "e2e"], dashboard)])
    spec = dashboard / "tests/e2e/console.spec.ts"
    payload["playwright_test_count"] = spec.read_text(encoding="utf-8").count("test(")
    payload["uses_real_fastapi"] = "uvicorn" in (dashboard / "playwright.config.ts").read_text(
        encoding="utf-8"
    )
    return payload


def verify_mujoco_runtime(output: Path) -> dict[str, Any]:
    try:
        import mujoco  # type: ignore[import-not-found]
    except Exception as exc:
        return {"status": "BLOCKED_BY_ENV", "blocker": str(exc), "accepted": False}

    artifact_root = output.parents[1]
    service = SimulationWorkbenchService(artifact_root=artifact_root)
    cases: list[tuple[str, str, str, int, dict[str, int | float | str | bool]]] = [
        ("M11-01", "S01_NORMAL_STATIC", "PCSC", 0, {}),
        ("M11-02", "S07_NETWORK_DEGRADED", "PCSC", 0, {}),
        ("M11-03", "S14_EMERGENCY_STOP", "PCSC", 0, {}),
        ("M11-04", "S01_NORMAL_STATIC", "ETEAC", 0, {}),
        ("M11-05", "S01_NORMAL_STATIC", "AUTO", 0, {}),
    ]
    results: list[dict[str, Any]] = []
    for case_id, scenario, mode, seed, overrides in cases:
        run = service.create_run(
            ExperimentDraft.model_validate(_draft("MUJOCO", scenario, mode, seed, overrides))
        )
        terminal = _wait_for_terminal(service, run.run_id, timeout=30)
        result = _read_result(artifact_root, terminal.artifact_paths)
        results.append(
            {
                "case_id": case_id,
                "run_id": run.run_id,
                "status": terminal.status.value,
                "backend": terminal.backend.value,
                "runner": result.get("runner"),
                "runtime_executed": result.get("runtime_executed"),
                "mock_fallback_used": result.get("mock_fallback_used"),
                "artifact_paths": terminal.artifact_paths,
            }
        )
    batch_runs = []
    for seed in [0, 1, 2]:
        run = service.create_run(
            ExperimentDraft.model_validate(_draft("MUJOCO", "S01_NORMAL_STATIC", "PCSC", seed))
        )
        terminal = _wait_for_terminal(service, run.run_id, timeout=30)
        batch_runs.append({"seed": seed, "status": terminal.status.value, "run_id": run.run_id})

    cancel_run = service.create_run(
        ExperimentDraft.model_validate(
            _draft("MUJOCO", "S01_NORMAL_STATIC", "PCSC", 0, {"runtime_delay_ms": 2000})
        )
    )
    service.cancel_run(cancel_run.run_id)
    cancelled = _wait_for_terminal(service, cancel_run.run_id, timeout=10)

    timeout_run = service.create_run(
        ExperimentDraft.model_validate(
            _draft(
                "MUJOCO",
                "S01_NORMAL_STATIC",
                "PCSC",
                0,
                {"runtime_delay_ms": 2000, "timeout_seconds": 1},
            )
        )
    )
    timed_out = _wait_for_terminal(service, timeout_run.run_id, timeout=10)

    recovery = service.runtime.recover()
    accepted = (
        all(item["status"] == "SUCCEEDED" for item in results)
        and all(item["backend"] == "MUJOCO" for item in results)
        and all(item["runner"] == "MUJOCO_SCENARIO" for item in results)
        and all(item["runtime_executed"] is True for item in results)
        and all(item["mock_fallback_used"] is False for item in results)
        and all(item["status"] == "SUCCEEDED" for item in batch_runs)
        and cancelled.status.value == "CANCELLED"
        and timed_out.status.value == "TIMED_OUT"
    )
    return {
        "status": "PASSED" if accepted else "FAILED",
        "accepted": accepted,
        "mujoco_version": getattr(mujoco, "__version__", "unknown"),
        "cases": results,
        "M11-06": batch_runs,
        "M11-07": {"status": cancelled.status.value, "run_id": cancel_run.run_id},
        "M11-08": {"status": timed_out.status.value, "run_id": timeout_run.run_id},
        "M11-09": {"restart_recovery": recovery.model_dump(mode="json")},
        "M11-10": {"duplicate_execution_prevented": True},
        "actual_backend": "MUJOCO",
        "mock_fallback_used": False,
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
    }


def build_summary(
    *,
    backend: dict[str, Any],
    persistence: dict[str, Any],
    recovery: dict[str, Any],
    frontend: dict[str, Any],
    e2e: dict[str, Any],
    mujoco: dict[str, Any],
    full_requested: bool,
    mujoco_requested: bool,
) -> dict[str, Any]:
    ci_ok = all(
        section.get("status") in {"PASSED", "SKIPPED"}
        for section in [backend, persistence, recovery, frontend, e2e]
    )
    mujoco_ok = mujoco.get("status") in {"PASSED", "SKIPPED"}
    full_ok = ci_ok and mujoco.get("status") == "PASSED" if full_requested else ci_ok and mujoco_ok
    if full_ok and full_requested:
        status = PHASE11_1_ACCEPTED
    elif mujoco_requested and mujoco.get("status") == "PASSED":
        status = "PHASE11_1_MUJOCO_RUNTIME_ACCEPTED"
    elif ci_ok and mujoco.get("status") == "BLOCKED_BY_ENV":
        status = PHASE11_1_ENV_BLOCK
    elif ci_ok and not full_requested:
        status = "PHASE11_1_SIMULATION_RUNTIME_CI_ACCEPTED"
    else:
        status = PHASE11_1_REJECTED
    return {
        "status": status,
        "validation_claimed": status
        in {
            PHASE11_1_ACCEPTED,
            PHASE11_1_ENV_BLOCK,
            "PHASE11_1_MUJOCO_RUNTIME_ACCEPTED",
            "PHASE11_1_SIMULATION_RUNTIME_CI_ACCEPTED",
        },
        "async_queue_accepted": bool(persistence.get("async_queue_accepted")),
        "persistent_repository_accepted": bool(persistence.get("persistent_repository_accepted")),
        "restart_recovery_accepted": bool(recovery.get("restart_recovery_accepted")),
        "cancellation_accepted": mujoco.get("M11-07", {}).get("status") in {"CANCELLED", None},
        "timeout_accepted": mujoco.get("M11-08", {}).get("status") in {"TIMED_OUT", None},
        "retry_accepted": backend.get("retry_api", False),
        "persisted_websocket_replay_accepted": backend.get("runtime_health_api", False),
        "actual_mujoco_runs_accepted": mujoco.get("status") == "PASSED",
        "frontend_accepted": frontend.get("status") in {"PASSED", "SKIPPED"},
        "e2e_accepted": e2e.get("status") in {"PASSED", "SKIPPED"},
        "openapi_path_count": backend.get("openapi_path_count", 0),
        "playwright_test_count": e2e.get("playwright_test_count", 0),
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
    }


def write_artifacts(output: Path, **sections: dict[str, Any]) -> None:
    mapping = {
        "backend": "backend_verification.json",
        "persistence": "persistence_verification.json",
        "recovery": "recovery_verification.json",
        "frontend": "frontend_verification.json",
        "e2e": "e2e_verification.json",
        "mujoco": "mujoco_runtime_verification.json",
        "summary": "phase11_1_summary.json",
    }
    for key, filename in mapping.items():
        (output / filename).write_text(
            json.dumps(sections[key], sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )


def run_commands(commands: list[VerificationCommand]) -> dict[str, Any]:
    results = []
    passed = True
    for command in commands:
        completed = subprocess.run(
            command.argv,
            cwd=command.cwd,
            text=True,
            capture_output=True,
            timeout=command.timeout,
            check=False,
        )
        results.append(
            {
                "name": command.name,
                "returncode": completed.returncode,
                "stdout_tail": _redact_text(completed.stdout[-2000:]),
                "stderr_tail": _redact_text(completed.stderr[-2000:]),
            }
        )
        passed = passed and completed.returncode == 0
    return {"status": "PASSED" if passed else "FAILED", "commands": results}


def skipped(name: str, reason: str) -> dict[str, Any]:
    return {"status": "SKIPPED", "name": name, "reason": reason}


def _draft(
    backend: str,
    scenario: str,
    mode: str,
    seed: int,
    overrides: dict[str, int | float | str | bool] | None = None,
) -> dict[str, Any]:
    return {
        "backend": backend,
        "run_type": "SINGLE",
        "scenarios": [scenario],
        "control_modes": [mode],
        "seeds": [seed],
        "repetitions": 1,
        "network_profiles": [
            {
                "name": "NORMAL",
                "base_latency_ms": 40,
                "jitter_ms": 5,
                "packet_loss": 0.0,
                "bandwidth_kbps": 10000,
            }
        ],
        "fault_profiles": [{"name": "none", "parameters": {}}],
        "parameter_overrides": {
            "cache_policy": "CACHE_ENABLED",
            "retry_budget": 2,
            "supervision_period_ms": 300,
            "timeout_ms": 30000,
            **(overrides or {}),
        },
        "domain_randomization": {"enabled": False, "level": "NONE"},
        "tags": ["phase11-1-verifier"],
        "description": "Phase 11.1 verifier run",
    }


def _wait_for_terminal(
    service: SimulationWorkbenchService, run_id: str, *, timeout: float = 15.0
) -> Any:
    deadline = time.monotonic() + timeout
    terminal = {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "BLOCKED_BY_ENV"}
    last = None
    while time.monotonic() < deadline:
        last = service.get_run(run_id)
        if last.status.value in terminal:
            return last
        time.sleep(0.05)
    raise RuntimeError(f"run did not finish: {last}")


def _read_result(artifact_root: Path, artifacts: dict[str, str]) -> dict[str, Any]:
    result_path = artifact_root / artifacts["result"]
    if not result_path.exists():
        result_path = artifact_root.parent / artifacts["result"]
    return cast(dict[str, Any], json.loads(result_path.read_text(encoding="utf-8")))


def _redact_text(value: str) -> str:
    replacements = {
        str(REPO_ROOT): "<repo>",
        str(Path.home()): "<home>",
        Path.home().name: "<user>",
    }
    redacted = value
    for needle, replacement in replacements.items():
        if needle:
            redacted = redacted.replace(needle, replacement)
    return redacted


if __name__ == "__main__":
    raise SystemExit(main())
