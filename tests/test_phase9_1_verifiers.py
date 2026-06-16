from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import cast


def _run(script: str, output: Path) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, script, "--output", str(output)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return cast(dict[str, object], json.loads(result.stdout))


def test_phase9_1_isaac_smoke_verifier_does_not_claim_success_when_blocked(
    tmp_path: Path,
) -> None:
    payload = _run("scripts/verify_phase9_1_isaac_smoke.py", tmp_path)

    assert payload["status"] == "BLOCKED_BY_ENV"
    assert payload["validation_claimed"] is False
    assert payload["real_isaac_run_count"] == 0


def test_phase9_1_ros2_and_moveit_verifiers_report_runtime_contract(tmp_path: Path) -> None:
    ros = _run("scripts/verify_phase9_1_ros2_integration.py", tmp_path / "ros")
    moveit = _run("scripts/verify_phase9_1_moveit_safety.py", tmp_path / "moveit")

    assert ros["status"] in {"BLOCKED_BY_ENV", "ROS2_INTEGRATION_VALIDATED"}
    assert moveit["status"] in {"BLOCKED_BY_ENV", "MOVEIT_SAFETY_VALIDATED"}

    if ros["status"] == "BLOCKED_BY_ENV":
        assert ros["validation_claimed"] is False
    else:
        assert ros["validation_claimed"] is True
        assert ros["runtime_evidence_complete"] is True

    if moveit["status"] == "BLOCKED_BY_ENV":
        assert moveit["validation_claimed"] is False
    else:
        assert moveit["validation_claimed"] is True
        assert moveit["runtime_evidence_complete"] is True


def test_phase9_1_cross_backend_verifier_marks_isaac_comparison_not_run(
    tmp_path: Path,
) -> None:
    payload = _run("scripts/verify_phase9_1_cross_backend.py", tmp_path)

    assert payload["status"] == "BLOCKED_BY_ENV"
    assert payload["mujoco_reference_status"] == "AVAILABLE"
    assert payload["isaac_comparison_status"] == "NOT_RUN_BLOCKED_BY_ENV"
