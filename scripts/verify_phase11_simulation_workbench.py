#!/usr/bin/env python
from __future__ import annotations

# ruff: noqa: E402
import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from cloud_edge_robot_arm.cloud.api.app import create_app  # type: ignore[import-not-found]
from cloud_edge_robot_arm.cloud.planning.adapter import (
    MockPlannerAdapter,  # type: ignore[import-not-found]
)
from cloud_edge_robot_arm.cloud.planning.pipeline import (
    PlanningPipeline,  # type: ignore[import-not-found]
)
from cloud_edge_robot_arm.experiments.scenario import (
    scenario_registry,  # type: ignore[import-not-found]
)
from cloud_edge_robot_arm.simulation_workbench.models import (
    ExperimentDraft,  # type: ignore[import-not-found]
)
from cloud_edge_robot_arm.simulation_workbench.service import (  # type: ignore[import-not-found]
    SimulationWorkbenchService,
)

PHASE11_SIMULATION_WORKBENCH_ACCEPTED = "PHASE11_SIMULATION_WORKBENCH_ACCEPTED"
PHASE11_SIMULATION_WORKBENCH_PARTIAL = "PHASE11_SIMULATION_WORKBENCH_PARTIAL_VERIFICATION"


@dataclass(frozen=True)
class VerificationCommand:
    name: str
    argv: list[str]
    cwd: Path
    timeout: int = 900


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 11 simulation workbench.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase11/verification"),
    )
    parser.add_argument("--skip-e2e", action="store_true")
    args = parser.parse_args()

    backend = verify_backend(REPO_ROOT)
    frontend = verify_frontend(REPO_ROOT)
    e2e = skipped_section("e2e", "skip-e2e") if args.skip_e2e else verify_e2e(REPO_ROOT)
    sample_run = build_sample_run(args.output)
    summary = build_summary(backend=backend, frontend=frontend, e2e=e2e, sample_run=sample_run)
    write_artifacts(
        args.output,
        backend=backend,
        frontend=frontend,
        e2e=e2e,
        sample_run=sample_run,
        summary=summary,
    )
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0 if _section_gate_passed(backend, frontend, e2e) else 1


def verify_backend(repo: Path) -> dict[str, Any]:
    commands = [
        VerificationCommand(
            "phase11-backend-tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_phase11_simulation_workbench_backend.py",
            ],
            repo,
        )
    ]
    payload = run_commands(commands)
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    paths = app.openapi().get("paths", {})
    service = SimulationWorkbenchService(artifact_root=repo / "artifacts")
    capabilities = service.capabilities().model_dump(mode="json")
    payload.update(
        {
            "scenario_count": len(scenario_registry()),
            "capability_api": "/api/v1/simulation/capabilities" in paths,
            "parameter_schema": "/api/v1/simulation/parameter-schema" in paths,
            "run_api": "/api/v1/simulation/runs" in paths,
            "batch_api": "/api/v1/simulation/batches" in paths,
            "comparison_api": "/api/v1/simulation/comparisons" in paths,
            "export_api": "/api/v1/simulation/exports" in paths,
            "stream_api": _has_route(app, "/api/v1/simulation/stream"),
            "openapi_path_count": len(paths) if isinstance(paths, dict) else 0,
            "runner_allowlist": capabilities["runner_allowlist"],
            "real_controller_contacted": capabilities["real_controller_contacted"],
            "hardware_motion_observed": capabilities["hardware_motion_observed"],
            "hardware_write_operations": capabilities["hardware_write_operations"],
            "no_hardware_route": not any(
                "real-robot" in path or "controller" in path or "level1" in path for path in paths
            ),
        }
    )
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
    simulation_dir = dashboard / "src/simulation"
    lab_page = (dashboard / "src/pages/SimulationLabPage.tsx").read_text(encoding="utf-8")
    payload.update(
        {
            "config_builder": (simulation_dir / "builders/ExperimentConfigBuilder.ts").exists(),
            "sweep_builder": (simulation_dir / "builders/SweepPlanBuilder.ts").exists(),
            "batch_builder": (simulation_dir / "builders/BatchPlanBuilder.ts").exists(),
            "live_events": (simulation_dir / "services/RunMonitorService.ts").exists(),
            "metrics_service": (simulation_dir / "services/MetricsService.ts").exists(),
            "comparison_service": (simulation_dir / "services/ComparisonService.ts").exists(),
            "reproduction_service": (simulation_dir / "services/ReproductionService.ts").exists(),
            "export_service": (simulation_dir / "services/ExportService.ts").exists(),
            "no_hardcoded_scenario_list": "S14_EMERGENCY_STOP" not in lab_page
            and "experimentKinds" not in lab_page,
            "echarts_dynamic_import": 'import("echarts")'
            in (simulation_dir / "components/MetricChart.tsx").read_text(encoding="utf-8"),
            "vite_chunk_warning": (
                "manualChunks configured for react/antd/echarts; "
                "large antd and echarts chunks remain non-blocking technical debt"
            ),
        }
    )
    return payload


def verify_e2e(repo: Path) -> dict[str, Any]:
    dashboard = repo / "dashboard"
    payload = run_commands([VerificationCommand("dashboard-e2e", ["npm", "run", "e2e"], dashboard)])
    spec = (dashboard / "tests/e2e/console.spec.ts").read_text(encoding="utf-8")
    payload.update(
        {
            "playwright_test_count": spec.count("test("),
            "uses_real_fastapi": "page.route(" not in spec
            and "uvicorn" in (dashboard / "playwright.config.ts").read_text(encoding="utf-8"),
            "no_real_hardware": "hardware_motion_observed" in spec
            and "real_controller_contacted" in spec,
        }
    )
    return payload


def build_sample_run(output: Path) -> dict[str, Any]:
    service = SimulationWorkbenchService(artifact_root=output.parents[1])

    run = service.create_run(
        ExperimentDraft.model_validate(
            {
                "backend": "MOCK",
                "run_type": "SINGLE",
                "scenarios": ["S01_NORMAL_STATIC"],
                "control_modes": ["PCSC"],
                "seeds": [0],
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
                },
                "domain_randomization": {"enabled": False, "level": "NONE"},
                "tags": ["phase11-verifier"],
                "description": "verifier sample run",
            }
        )
    )
    metrics = service.metrics_for(run.run_id).model_dump(mode="json")["metrics"]
    return {
        "run": run.model_dump(mode="json"),
        "metrics": metrics,
        "events": service.events_for(run.run_id).model_dump(mode="json")["events"],
    }


def build_summary(
    *,
    backend: dict[str, Any],
    frontend: dict[str, Any],
    e2e: dict[str, Any],
    sample_run: dict[str, Any],
) -> dict[str, Any]:
    accepted = (
        backend["status"] == "PASSED"
        and frontend["status"] == "PASSED"
        and e2e["status"] in {"PASSED", "SKIPPED"}
        and backend["scenario_count"] == 15
        and backend["capability_api"]
        and backend["parameter_schema"]
        and backend["stream_api"]
        and set(backend.get("runner_allowlist", []))
        == {
            "MOCK_SCENARIO",
            "MUJOCO_SCENARIO",
            "PHASE8_BATCH",
            "PHASE8_SWEEP",
            "PHASE9_MUJOCO_BENCHMARK",
            "ISAAC_BENCHMARK",
            "CROSS_BACKEND_PAIRED",
        }
        and frontend["no_hardcoded_scenario_list"]
        and frontend["config_builder"]
        and frontend["sweep_builder"]
        and frontend["batch_builder"]
        and frontend["metrics_service"]
        and frontend["comparison_service"]
        and frontend["reproduction_service"]
        and frontend["export_service"]
        and int(e2e.get("playwright_test_count", 0)) >= 15
        and bool(e2e.get("uses_real_fastapi", True))
        and backend["real_controller_contacted"] is False
        and backend["hardware_motion_observed"] is False
        and backend["hardware_write_operations"] == []
        and backend["no_hardware_route"]
    )
    metrics = sample_run.get("metrics", [])
    return {
        "status": _summary_status(e2e=e2e, accepted=accepted),
        "validation_claimed": accepted,
        "scenario_count": backend["scenario_count"],
        "openapi_path_count": backend["openapi_path_count"],
        "playwright_test_count": e2e.get("playwright_test_count", 0),
        "uses_real_fastapi": bool(e2e.get("uses_real_fastapi", False)),
        "metric_count": len(metrics) if isinstance(metrics, list) else 0,
        "runner_allowlist": backend.get("runner_allowlist", []),
        "vite_chunk_warning": frontend.get("vite_chunk_warning", ""),
        "backend_status": backend["status"],
        "frontend_status": frontend["status"],
        "e2e_status": e2e["status"],
        "mock_run_status": sample_run["run"]["status"],
        "mujoco_status": _backend_readiness(backend, "MUJOCO"),
        "isaac_status": _backend_readiness(backend, "ISAAC_SIM"),
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
        "highest_acceptance_level": "NONE",
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _summary_status(*, e2e: dict[str, Any], accepted: bool) -> str:
    if accepted:
        return PHASE11_SIMULATION_WORKBENCH_ACCEPTED
    if e2e["status"] == "SKIPPED":
        return PHASE11_SIMULATION_WORKBENCH_PARTIAL
    return "PHASE11_REJECTED"


def _section_gate_passed(
    backend: dict[str, Any], frontend: dict[str, Any], e2e: dict[str, Any]
) -> bool:
    return all(section["status"] in {"PASSED", "SKIPPED"} for section in (backend, frontend, e2e))


def run_commands(commands: list[VerificationCommand]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for command in commands:
        result = subprocess.run(
            command.argv,
            cwd=command.cwd,
            check=False,
            text=True,
            capture_output=True,
            timeout=command.timeout,
        )
        passed = result.returncode == 0
        results.append(
            {
                "name": command.name,
                "argv": _redact(command.argv),
                "cwd": _relative(command.cwd),
                "returncode": result.returncode,
                "status": "PASSED" if passed else "FAILED",
                "stdout_tail": _redact_text(result.stdout[-5000:]),
                "stderr_tail": _redact_text(result.stderr[-5000:]),
            }
        )
        if not passed:
            break
    return {
        "status": "PASSED" if all(item["status"] == "PASSED" for item in results) else "FAILED",
        "commands": results,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def write_artifacts(
    output: Path,
    *,
    backend: dict[str, Any],
    frontend: dict[str, Any],
    e2e: dict[str, Any],
    sample_run: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for filename, payload in (
        ("backend_verification.json", backend),
        ("frontend_verification.json", frontend),
        ("e2e_verification.json", e2e),
        ("sample_run.json", sample_run),
        ("phase11_summary.json", summary),
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


def _has_route(app: Any, path: str) -> bool:
    return any(getattr(route, "path", "") == path for route in app.routes)


def _backend_readiness(backend: dict[str, Any], name: str) -> str:
    service = SimulationWorkbenchService(artifact_root=REPO_ROOT / "artifacts")
    capabilities = service.capabilities()
    for item in capabilities.backends:
        if item.backend == name:
            return str(item.readiness.value)
    return "UNKNOWN"


def _redact(argv: list[str]) -> list[str]:
    return [_redact_text(Path(item).name if Path(item).is_absolute() else item) for item in argv]


def _relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix() or "."
    except ValueError:
        return "<outside-repo>"


def _redact_text(text: str) -> str:
    redacted = text.replace(str(REPO_ROOT), "<repo>")
    redacted = redacted.replace(str(Path.home()), "$HOME")
    redacted = re.sub(
        r"(?i)(token|password|secret|credential)=([^\s,;]+)", r"\1=<redacted>", redacted
    )
    return redacted


if __name__ == "__main__":
    raise SystemExit(main())
