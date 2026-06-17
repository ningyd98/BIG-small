from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_phase10_0_entrypoint_reports_gate_ready_without_hardware(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_phase10_0.py",
            "--output",
            str(tmp_path / "phase10_0"),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED"
    assert payload["validation_claimed"] is True
    assert payload["hardware_motion_observed"] is False
    assert set(payload["safety_fault_coverage"]) >= {
        "emergency_stop_active",
        "emergency_stop_during_run",
        "telemetry_stale",
        "ros2_controller_unavailable",
        "moveit_planning_failed",
        "joint_state_missing",
        "tf_unavailable",
        "controller_response_timeout",
        "network_disconnected",
        "edge_runtime_exit",
        "cloud_command_expired",
        "duplicate_command_seq",
        "stale_plan_version",
        "workspace_violation",
        "velocity_acceleration_exceeded",
        "simulation_config_used_for_real",
        "safety_shield_bypass_attempt",
        "acceptance_level_insufficient",
    }


def test_phase10_1_entrypoint_reports_dry_run_accepted(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_phase10_1.py",
            "--output",
            str(tmp_path / "phase10_1"),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "PHASE10_DRY_RUN_ACCEPTED"
    assert payload["dry_run_status"] == "DRY_RUN_VALIDATED"
    assert payload["real_robot_validation"] == "NOT_STARTED"
    assert payload["hardware_motion_observed"] is False


def test_phase10_acceptance_level_cli_never_runs_all_levels_by_default(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase10_acceptance_level.py",
            "--level",
            "LEVEL_2",
            "--output",
            str(tmp_path / "acceptance"),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "ENVIRONMENT_BLOCKED"
    assert payload["requested_level"] == "LEVEL_2"
    assert payload["ran_multiple_levels"] is False
    assert payload["hardware_motion_observed"] is False


def test_phase10_experiment_cli_defaults_to_dry_run(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_phase10_experiment.py",
            "--experiment",
            "R01",
            "--output",
            str(tmp_path / "experiments"),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["experiment_id"] == "R01"
    assert payload["execution_mode"] == "DRY_RUN"
    assert payload["hardware_motion_observed"] is False


def test_pytest_registers_real_robot_runtime_marker() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "real_robot_runtime: requires physical robot hardware and operator approval" in pyproject
