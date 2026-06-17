from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cloud_edge_robot_arm.contracts import SkillName
from cloud_edge_robot_arm.edge.safety.providers import TelemetrySample
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from tests.phase2_helpers import contract, step


def _valid_config_payload() -> dict[str, object]:
    return {
        "robot_vendor": "site_vendor",
        "robot_model": "site_model",
        "robot_serial": "SITE-SERIAL-001",
        "controller_address": "robot-controller.local",
        "ros_namespace": "/real_robot",
        "planning_group": "panda_arm",
        "end_effector_link": "panda_hand",
        "base_link": "panda_link0",
        "joint_names": [f"panda_joint{i}" for i in range(1, 8)],
        "velocity_scale": 0.05,
        "acceleration_scale": 0.05,
        "workspace_limits": {
            "x_min": -0.3,
            "x_max": 0.3,
            "y_min": -0.3,
            "y_max": 0.3,
            "z_min": 0.05,
            "z_max": 0.45,
        },
        "payload_limit_kg": 0.2,
        "emergency_stop_topic": "/real_robot/emergency_stop",
        "hardware_status_topic": "/real_robot/hardware_status",
    }


def test_phase10_0_verifier_executes_checks_instead_of_hardcoding_true(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.real_robot.verification import verify_phase10_0

    payload = verify_phase10_0(tmp_path)

    assert payload["status"] == "PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED"
    checks = payload["checks"]
    assert checks
    for check_id, item in checks.items():
        assert item["check_id"] == check_id
        assert item["executed"] is True
        assert item["passed"] is True
        assert item["expected_result"]
        assert item["actual_result"]
        assert isinstance(item["evidence"], dict)

    for item in payload["safety_fault_coverage"]:
        assert set(item) >= {
            "check_id",
            "executed",
            "passed",
            "evidence",
            "expected_result",
            "actual_result",
        }
        assert item["executed"] is True


def test_synthetic_dry_run_does_not_claim_moveit_or_collision_validation() -> None:
    from cloud_edge_robot_arm.real_robot.config import ExecutionMode, RealRobotRuntimeSettings
    from cloud_edge_robot_arm.real_robot.dry_run import DryRunValidationService
    from cloud_edge_robot_arm.real_robot.planners import SyntheticDryRunPlanner

    task = contract(
        task_id="phase10-2a-synthetic",
        steps=[step("step-home", SkillName.HOME, success_conditions=["robot_in_safe_pose"])],
    )
    service = DryRunValidationService(
        shield=SafetyShield(),
        runtime_settings=RealRobotRuntimeSettings(
            runtime_profile="test",
            execution_mode=ExecutionMode.DRY_RUN,
            enable_real_robot=False,
            config=None,
        ),
        telemetry_sample=TelemetrySample(
            timestamp=datetime.now(UTC),
            tcp_velocity=0.0,
            joint_velocities=[0.0] * 7,
            acceleration=0.0,
        ),
        planner=SyntheticDryRunPlanner(),
    )

    result = service.validate(task.model_dump(mode="json"))

    assert result.status == "DRY_RUN_VALIDATED"
    assert result.planner_backend == "SYNTHETIC"
    assert result.moveit_runtime_used is False
    assert result.collision_validation_claimed is False
    assert result.hardware_readiness_claimed is False
    assert result.safety_margin.limiting_rule == "SYNTHETIC_NOT_COLLISION_VALIDATED"


def test_phase10_1_synthetic_only_status_is_framework_dry_run(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.real_robot.verification import verify_phase10_1

    payload = verify_phase10_1(tmp_path)

    assert payload["status"] == "PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED"
    assert payload["dry_run_status"] == "DRY_RUN_VALIDATED"
    assert payload["moveit_runtime_used"] is False
    assert payload["hardware_motion_observed"] is False


def test_phase10_2a_rejects_source_tree_hash_mismatch(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.real_robot.provenance import (
        EvidenceProvenance,
        current_source_provenance,
        provenance_matches_current_source,
    )

    provenance = current_source_provenance(
        command=["python", "scripts/verify_phase10_2a.py"],
        config_hash="cfg",
        verifier_version="phase10.2a-test",
    )
    mismatched = EvidenceProvenance.model_validate(
        {
            **provenance.model_dump(mode="json"),
            "source_tree_hash": "0" * 64,
        }
    )

    assert provenance_matches_current_source(provenance) is True
    assert provenance_matches_current_source(mismatched) is False
    path = tmp_path / "evidence.json"
    path.write_text(
        json.dumps({"provenance": mismatched.model_dump(mode="json")}) + "\n",
        encoding="utf-8",
    )


def test_phase10_2a_rejects_dirty_authoritative_provenance(tmp_path: Path) -> None:
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
    provenance["worktree_clean"] = False
    for path, payload in {
        phase10_0 / "phase10_0_verification.json": {
            "status": "PHASE10_IMPLEMENTATION_READY_ENV_BLOCKED",
            "validation_claimed": True,
        },
        phase10_1 / "phase10_summary.json": {
            "status": "PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED",
            "validation_claimed": True,
            "hardware_motion_observed": False,
        },
        moveit / "moveit_dry_run_verification.json": {
            "status": "MOVEIT_DRY_RUN_VALIDATED",
            "validation_claimed": True,
            "moveit_runtime_used": True,
            "sent_to_hardware": False,
            "hardware_motion_observed": False,
        },
    }.items():
        path.write_text(
            json.dumps({**payload, "provenance": provenance}) + "\n",
            encoding="utf-8",
        )

    payload = verify_phase10_2a(
        tmp_path / "final",
        phase10_0_dir=phase10_0,
        phase10_1_dir=phase10_1,
        moveit_dry_run_dir=moveit,
    )

    assert payload["status"] == "PHASE10_2A_REJECTED"
    assert payload["validation_claimed"] is False


def test_acceptance_store_rejects_jump_and_requires_complete_evidence(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.real_robot.acceptance import (
        RealRobotAcceptanceLevel,
        RealRobotAcceptanceStore,
    )

    store = RealRobotAcceptanceStore(tmp_path / "acceptance_state.json")
    missing = tmp_path / "missing.json"

    with pytest.raises(ValueError, match="evidence file"):
        store.mark_passed(
            RealRobotAcceptanceLevel.LEVEL_0,
            evidence_path=missing,
            config_hash="cfg",
            source_tree_hash="tree",
            robot_identity_hash="robot",
            operator_confirmation={"confirmation_id": "session-1"},
        )

    level2_evidence = tmp_path / "level2.json"
    level2_evidence.write_text(
        json.dumps(
            {
                "status": "ACCEPTED",
                "requested_level": "LEVEL_2",
                "config_hash": "cfg",
                "source_tree_hash": "tree",
                "robot_identity_hash": "robot",
                "operator_confirmation": {"confirmation_id": "session-1"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sequential"):
        store.mark_passed(
            RealRobotAcceptanceLevel.LEVEL_2,
            evidence_path=level2_evidence,
            config_hash="cfg",
            source_tree_hash="tree",
            robot_identity_hash="robot",
            operator_confirmation={"confirmation_id": "session-1"},
        )


def test_operator_confirmation_is_short_lived_one_time_and_action_bound() -> None:
    from cloud_edge_robot_arm.real_robot.operator_confirmation import OperatorConfirmation

    issued = datetime.now(UTC)
    confirmation = OperatorConfirmation.issue(
        confirmation_id="confirm-1",
        token="site-secret-token",
        issued_at=issued,
        expires_at=issued + timedelta(seconds=30),
        allowed_robot_hash="robot",
        allowed_config_hash="cfg",
        allowed_level="LEVEL_2",
        allowed_action="single_joint_small_motion",
        local_origin_verified=True,
    )

    assert confirmation.token_hash != "site-secret-token"
    consumed = confirmation.consume(
        token="site-secret-token",
        robot_hash="robot",
        config_hash="cfg",
        level="LEVEL_2",
        action="single_joint_small_motion",
        now=issued + timedelta(seconds=1),
    )
    assert consumed.consumed_at is not None

    with pytest.raises(ValueError, match="already consumed"):
        consumed.consume(
            token="site-secret-token",
            robot_hash="robot",
            config_hash="cfg",
            level="LEVEL_2",
            action="single_joint_small_motion",
            now=issued + timedelta(seconds=2),
        )

    expired = OperatorConfirmation.issue(
        confirmation_id="confirm-2",
        token="another-token",
        issued_at=issued,
        expires_at=issued + timedelta(seconds=1),
        allowed_robot_hash="robot",
        allowed_config_hash="cfg",
        allowed_level="LEVEL_2",
        allowed_action="single_joint_small_motion",
        local_origin_verified=True,
    )
    with pytest.raises(ValueError, match="expired"):
        expired.consume(
            token="another-token",
            robot_hash="robot",
            config_hash="cfg",
            level="LEVEL_2",
            action="single_joint_small_motion",
            now=issued + timedelta(seconds=2),
        )

    wrong_action = OperatorConfirmation.issue(
        confirmation_id="confirm-3",
        token="third-token",
        issued_at=issued,
        expires_at=issued + timedelta(seconds=30),
        allowed_robot_hash="robot",
        allowed_config_hash="cfg",
        allowed_level="LEVEL_2",
        allowed_action="single_joint_small_motion",
        local_origin_verified=True,
    )
    with pytest.raises(ValueError, match="action"):
        wrong_action.consume(
            token="third-token",
            robot_hash="robot",
            config_hash="cfg",
            level="LEVEL_2",
            action="tcp_free_space_small_motion",
            now=issued + timedelta(seconds=2),
        )
