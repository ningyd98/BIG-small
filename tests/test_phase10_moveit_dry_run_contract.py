from __future__ import annotations

import json
from pathlib import Path


def test_phase10_moveit_dry_run_runtime_is_planning_only() -> None:
    source = Path("scripts/phase10/run_moveit_dry_run_runtime.py").read_text(encoding="utf-8")

    assert "_plan(REACHABLE" in source
    assert "_start_bigsmall_bridge" not in source
    assert "_send_boundary_trajectory" not in source
    assert "/bigsmall/follow_joint_trajectory" not in source
    assert "sent_to_hardware" in source
    assert "hardware_motion_observed" in source


def test_phase10_2a_aggregate_accepts_moveit_runtime_dry_run(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.real_robot.provenance import current_source_provenance
    from cloud_edge_robot_arm.real_robot.verification import verify_phase10_2a

    phase10_0 = tmp_path / "phase10_0"
    phase10_1 = tmp_path / "phase10_1"
    moveit = tmp_path / "moveit_dry_run"
    phase10_0.mkdir()
    phase10_1.mkdir()
    moveit.mkdir()
    provenance = current_source_provenance(
        command=["python", "scripts/verify_phase10_2a.py"],
        verifier_version="phase10.2a-test",
    ).model_dump(mode="json")
    provenance["worktree_clean"] = True
    (phase10_0 / "phase10_0_verification.json").write_text(
        json.dumps(
            {
                "status": "PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED",
                "validation_claimed": True,
                "provenance": provenance,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (phase10_1 / "phase10_summary.json").write_text(
        json.dumps(
            {
                "status": "PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED",
                "validation_claimed": True,
                "hardware_motion_observed": False,
                "provenance": provenance,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (moveit / "moveit_dry_run_verification.json").write_text(
        json.dumps(
            {
                "status": "MOVEIT_DRY_RUN_VALIDATED",
                "validation_claimed": True,
                "moveit_runtime_used": True,
                "sent_to_hardware": False,
                "hardware_motion_observed": False,
                "provenance": provenance,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    payload = verify_phase10_2a(
        tmp_path / "final",
        phase10_0_dir=phase10_0,
        phase10_1_dir=phase10_1,
        moveit_dry_run_dir=moveit,
    )

    assert payload["status"] == "PHASE10_MOVEIT_DRY_RUN_ACCEPTED"
    assert payload["hardware_motion_observed"] is False
    assert payload["real_robot_validation"] == "NOT_STARTED"
