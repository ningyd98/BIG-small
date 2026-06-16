from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_phase9_1_env_block_artifact_records_commands_and_exit_codes(tmp_path: Path) -> None:
    output = tmp_path / "phase9_1"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/verify_phase9_1.py",
            "--output",
            str(output),
            "--skip-history",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    summary = json.loads((output / "phase9_1_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] in {
        "PHASE9_1_ACCEPTED",
        "PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK",
        "PHASE9_1_REJECTED",
    }
    assert summary["status"] == "PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK"
    for component in ("ros2", "moveit", "isaac"):
        artifact = summary["components"][component]
        assert artifact["commands"], component
        assert all("argv" in command and "exit_code" in command for command in artifact["commands"])
    assert summary["components"]["ros2"]["status"] in {
        "BLOCKED_BY_ENV",
        "ROS2_INTEGRATION_VALIDATED",
    }
    assert summary["components"]["moveit"]["status"] in {
        "BLOCKED_BY_ENV",
        "MOVEIT_SAFETY_VALIDATED",
    }
    assert summary["components"]["isaac"]["status"] == "BLOCKED_BY_ENV"
    assert summary["components"]["isaac"]["validation_claimed"] is False
    if summary["components"]["ros2"]["status"] == "ROS2_INTEGRATION_VALIDATED":
        assert summary["components"]["ros2"]["validation_claimed"] is True
        assert summary["components"]["ros2"]["runtime_evidence_complete"] is True
    if summary["components"]["moveit"]["status"] == "MOVEIT_SAFETY_VALIDATED":
        assert summary["components"]["moveit"]["validation_claimed"] is True
        assert summary["components"]["moveit"]["runtime_evidence_complete"] is True


def test_phase9_1_time_domains_are_explicit_in_blocked_artifact(tmp_path: Path) -> None:
    output = tmp_path / "phase9_1"
    subprocess.run(
        [sys.executable, "scripts/verify_phase9_1.py", "--output", str(output), "--skip-history"],
        check=True,
    )
    summary = json.loads((output / "phase9_1_summary.json").read_text(encoding="utf-8"))

    assert summary["time_domains"] == [
        "simulation_time",
        "ros_time",
        "wall_clock_time",
        "sensor_timestamp",
    ]
