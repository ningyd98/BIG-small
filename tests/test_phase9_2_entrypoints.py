from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_phase9_2_environment_entrypoint_writes_report(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_phase9_2_environment.py",
            "--output",
            str(tmp_path / "environment"),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] in {"BLOCKED_BY_ENV", "ISAAC_ENV_READY"}
    assert (tmp_path / "environment" / "compatibility_report.json").exists()


def test_phase9_2_isaac_smoke_entrypoint_rejects_missing_evidence(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("ISAAC_SIM_ROOT", None)
    env.pop("ISAAC_RUNTIME_MODE", None)
    env["PHASE9_2_DISABLE_ISAAC_AUTO_DETECT"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_phase9_2_isaac_smoke.py",
            "--output",
            str(tmp_path / "isaac"),
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "INCOMPLETE"
    assert payload["validation_claimed"] is False


def test_phase9_2_cross_backend_entrypoint_rejects_missing_runs(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase9_2_cross_backend.py",
            "--output",
            str(tmp_path / "cross_backend"),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "REJECTED"
    assert payload["validation_claimed"] is False


def test_phase9_2_isaac_benchmark_entrypoint_requires_smoke_validation(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.pop("ISAAC_SIM_ROOT", None)
    env.pop("ISAAC_RUNTIME_MODE", None)
    env["HOME"] = str(tmp_path / "home")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase9_2_isaac_benchmark.py",
            "--output",
            str(tmp_path / "isaac_benchmark"),
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["benchmark_status"] != "PASSED"
    assert payload["validation_claimed"] is False


def test_phase9_2_aggregate_entrypoint_rejects_without_runtime_artifacts(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_phase9_2.py",
            "--output",
            str(tmp_path / "final"),
            "--artifacts-root",
            str(artifacts_root),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "PHASE9_2_REJECTED"


def test_pytest_registers_isaac_runtime_marker() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "isaac_runtime: requires real Isaac Sim 6.0 runtime" in pyproject
