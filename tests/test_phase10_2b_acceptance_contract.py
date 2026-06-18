from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_phase10_2b_verifier_writes_split_authoritative_artifacts(tmp_path: Path) -> None:
    from scripts.verify_phase10_2b import build_summary_payload, write_artifacts

    backend = {
        "status": "PASSED",
        "commands": [{"name": "dashboard-backend-tests", "status": "PASSED"}],
        "checks": {
            "evidence_path_security": "PASSED",
            "experiment_runner_allowlist": "PASSED",
            "websocket_auth_replay": "PASSED",
            "no_hardware_route": "PASSED",
            "real_robot_not_started": "PASSED",
            "hardware_level_none": "PASSED",
        },
    }
    frontend = {
        "status": "PASSED",
        "commands": [
            {"name": "dashboard-openapi-drift", "status": "PASSED"},
            {"name": "dashboard-format", "status": "PASSED"},
            {"name": "dashboard-lint", "status": "PASSED"},
            {"name": "dashboard-typecheck", "status": "PASSED"},
            {"name": "dashboard-unit-tests", "status": "PASSED"},
            {"name": "dashboard-build", "status": "PASSED"},
        ],
        "openapi_path_count": 52,
        "vite_chunk_warning": "manualChunks configured; warning is non-blocking if emitted",
    }
    e2e = {
        "status": "PASSED",
        "commands": [{"name": "dashboard-e2e", "status": "PASSED"}],
        "playwright_test_count": 10,
        "uses_real_fastapi": True,
    }

    summary = build_summary_payload(backend=backend, frontend=frontend, e2e=e2e)
    write_artifacts(tmp_path, backend=backend, frontend=frontend, e2e=e2e, summary=summary)

    expected_files = {
        "backend_verification.json",
        "frontend_verification.json",
        "e2e_verification.json",
        "phase10_2b_summary.json",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected_files
    loaded_summary = json.loads((tmp_path / "phase10_2b_summary.json").read_text())
    assert loaded_summary["status"] == "PHASE10_2B_CONSOLE_ACCEPTED"
    assert loaded_summary["real_controller_contacted"] is False
    assert loaded_summary["hardware_motion_observed"] is False
    assert loaded_summary["highest_acceptance_level"] == "NONE"


def test_phase10_2b_verifier_supports_backend_only_mode() -> None:
    script = (ROOT / "scripts/verify_phase10_2b.py").read_text(encoding="utf-8")

    assert "--backend-only" in script
    assert "PHASE10_2B_PARTIAL_VERIFICATION" in script
    assert "backend_verification.json" in script
    assert "frontend_verification.json" in script
    assert "e2e_verification.json" in script
    assert "phase10_2b_summary.json" in script


def test_phase10_2b_backend_only_does_not_claim_full_acceptance() -> None:
    from scripts.verify_phase10_2b import build_summary_payload, skipped_section

    backend = {
        "status": "PASSED",
        "commands": [{"name": "dashboard-backend-tests", "status": "PASSED"}],
    }
    summary = build_summary_payload(
        backend=backend,
        frontend=skipped_section("frontend", "backend-only"),
        e2e=skipped_section("e2e", "backend-only"),
    )

    assert summary["status"] == "PHASE10_2B_PARTIAL_VERIFICATION"
    assert summary["validation_claimed"] is False


def test_phase10_2b_verifier_redacts_local_paths() -> None:
    from scripts.verify_phase10_2b import _redact_argv, _redact_text, _relative_cwd

    repo = ROOT

    assert _redact_argv([str(repo / ".venv/bin/python"), "-m", "pytest"], repo=repo)[0] == "python"
    assert _relative_cwd(repo / "dashboard", repo=repo) == "dashboard"
    assert "<repo>/dashboard" in _redact_text(f"{repo}/dashboard", repo=repo)


def test_ci_splits_python_frontend_and_e2e_jobs() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    jobs = workflow["jobs"]

    assert {"python", "frontend", "e2e"}.issubset(jobs)
    assert any(
        "verify_phase10_2b.py --backend-only" in step.get("run", "")
        for step in jobs["python"]["steps"]
    )
    frontend_runs = "\n".join(step.get("run", "") for step in jobs["frontend"]["steps"])
    for command in (
        "npm ci",
        "npm run api:check",
        "npm run format:check",
        "npm run lint",
        "npm run typecheck",
        "npm run test",
        "npm run build",
    ):
        assert command in frontend_runs
    e2e_runs = "\n".join(step.get("run", "") for step in jobs["e2e"]["steps"])
    assert "npm run e2e" in e2e_runs
    assert any(
        step.get("uses", "").startswith("actions/upload-artifact") for step in jobs["e2e"]["steps"]
    )


def test_playwright_has_required_phase10_2b_scenarios() -> None:
    spec = (ROOT / "dashboard/tests/e2e/console.spec.ts").read_text(encoding="utf-8")

    assert spec.count("test(") == 10
    for required in (
        "Mock experiment state flow",
        "Synthetic dry-run evidence",
        "BLOCKED_BY_ENV",
        "path traversal rejection",
        "real hardware action locked",
        "WebSocket fallback polling",
        "VIEWER write rejection",
        "no direct ROS MoveIt controller inputs",
    ):
        assert required in spec
