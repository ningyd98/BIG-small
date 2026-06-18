"""Phase 10.2C Level 0 只读框架回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


def _site_payload() -> dict[str, object]:
    return {
        "session_id": "site-session-001",
        "robot_identity_hash": "robot-hash",
        "config_hash": "config-hash",
        "software_commit": "commit",
        "source_tree_hash": "tree",
        "operator_ids": ["operator-a", "operator-b"],
        "safety_reviewer": "reviewer-a",
        "site_checklist": {
            "isolated_workspace_confirmed": True,
            "estop_reachable_confirmed": True,
            "no_motion_mode_confirmed": True,
        },
        "started_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        "isolated_workspace_confirmed": True,
        "estop_reachable_confirmed": True,
        "no_motion_mode_confirmed": True,
        "physical_power_state": "controller_on_servos_disabled",
        "notes": "read-only validation",
    }


def test_read_only_adapter_protocol_has_no_motion_methods() -> None:
    from cloud_edge_robot_arm.real_robot.level0 import (
        READ_ONLY_ALLOWED_METHODS,
        FakeReadOnlyAdapter,
    )

    adapter = FakeReadOnlyAdapter()

    assert set(READ_ONLY_ALLOWED_METHODS) == {
        "connect",
        "disconnect",
        "health",
        "get_robot_identity",
        "get_controller_state",
        "get_joint_state",
        "get_tcp_pose",
        "get_emergency_stop_state",
        "get_fault_state",
        "get_operation_mode",
    }
    for forbidden in (
        "execute",
        "move",
        "command",
        "send_trajectory",
        "enable_controller",
        "servo_enable",
        "release_brake",
        "home",
        "safe_stop",
        "gripper_command",
    ):
        assert not hasattr(adapter, forbidden)


def test_fake_adapter_samples_are_fresh_structured_and_finite() -> None:
    from cloud_edge_robot_arm.real_robot.level0 import (
        EmergencyStopReadout,
        FakeReadOnlyAdapter,
        Level0BaseReadout,
        emergency_stop_is_inactive,
        is_fresh_readout,
    )

    adapter = FakeReadOnlyAdapter()
    with pytest.raises(TimeoutError):
        adapter.connect(timeout_ms=0)
    assert adapter.connect(timeout_ms=100).success is True
    identity = adapter.get_robot_identity(timeout_ms=100)
    joint = adapter.get_joint_state(timeout_ms=100)
    tcp = adapter.get_tcp_pose(timeout_ms=100)
    estop = adapter.get_emergency_stop_state(timeout_ms=100)
    fault = adapter.get_fault_state(timeout_ms=100)
    mode = adapter.get_operation_mode(timeout_ms=100)

    assert identity.robot_identity_hash
    assert identity.raw_vendor_state
    assert joint.freshness == "FRESH"
    assert joint.sample_sequence > 0
    assert len(joint.joint_names) == len(joint.positions)
    assert all(math.isfinite(value) for value in joint.positions)
    assert all(math.isfinite(value) for value in tcp.pose_xyzrpy)
    assert estop.state in {"ACTIVE", "INACTIVE", "UNKNOWN"}
    assert fault.state in {"FAULTED", "CLEAR", "UNKNOWN"}
    assert mode.operation_mode
    assert adapter.write_operation_count == 0
    assert is_fresh_readout(joint) is True
    assert is_fresh_readout(Level0BaseReadout(monotonic_age_ms=1000, max_allowed_age_ms=1)) is False
    assert emergency_stop_is_inactive(estop) is True
    assert emergency_stop_is_inactive(EmergencyStopReadout(state="UNKNOWN")) is False
    adapter.disconnect(timeout_ms=100)
    disconnected = adapter.get_controller_state(timeout_ms=100)
    assert disconnected.status == "UNAVAILABLE"
    assert disconnected.freshness == "UNAVAILABLE"


def test_site_session_requires_two_people_and_expires() -> None:
    from cloud_edge_robot_arm.real_robot.level0 import SiteReadOnlySession

    with pytest.raises(ValueError, match="at least two"):
        SiteReadOnlySession.model_validate({**_site_payload(), "operator_ids": ["solo"]})

    expired = SiteReadOnlySession.model_validate(
        {
            **_site_payload(),
            "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
        }
    )
    assert expired.is_valid(now=datetime.now(UTC)) is False


def test_level0_evidence_fake_output_is_redacted_and_framework_only(tmp_path: Path) -> None:
    from scripts.verify_phase10_2c_level0 import run_fake_verification

    payload = run_fake_verification(tmp_path)

    assert payload["status"] == "PHASE10_LEVEL0_FRAMEWORK_ACCEPTED"
    assert payload["controller_contacted"] is False
    assert payload["hardware_state_sampled"] is False
    assert payload["write_operation_count"] == 0
    assert payload["hardware_motion_observed"] is False
    expected = {
        "environment.json",
        "site_session.json",
        "controller_readback.jsonl",
        "joint_state_samples.jsonl",
        "tcp_pose_samples.jsonl",
        "estop_samples.jsonl",
        "fault_samples.jsonl",
        "read_only_api_audit.jsonl",
        "no_write_operation_evidence.json",
        "level0_summary.json",
    }
    assert {path.name for path in tmp_path.iterdir()} == expected
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.iterdir())
    for forbidden in ("/home/", "192.168.", "SITE-SERIAL-001", "credential", "token"):
        assert forbidden not in rendered


def test_level0_acceptance_requires_reviewer_and_does_not_promote_level1(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.real_robot.level0 import (
        Level0AcceptanceInput,
        evaluate_level0_acceptance,
    )

    accepted = evaluate_level0_acceptance(
        Level0AcceptanceInput(
            checks={f"L0-{index:02d}": True for index in range(1, 21)},
            evidence_complete=True,
            robot_identity_hash_matches=True,
            config_hash_matches=True,
            site_session_valid=True,
            safety_reviewer_approved=True,
            write_operation_count=0,
            hardware_motion_observed=False,
            worktree_clean=True,
            source_tree_hash_matches=True,
        )
    )

    assert accepted.status == "PHASE10_HARDWARE_READ_ONLY_ACCEPTED"
    assert accepted.highest_acceptance_level == "LEVEL_0"
    assert accepted.level1_allowed is False

    rejected = evaluate_level0_acceptance(
        Level0AcceptanceInput(
            checks={f"L0-{index:02d}": True for index in range(1, 20)},
            evidence_complete=True,
            robot_identity_hash_matches=True,
            config_hash_matches=True,
            site_session_valid=True,
            safety_reviewer_approved=False,
            write_operation_count=0,
            hardware_motion_observed=False,
            worktree_clean=True,
            source_tree_hash_matches=True,
        )
    )

    assert rejected.status == "PHASE10_LEVEL0_REJECTED"
    assert "safety reviewer approval missing" in rejected.blockers

    mismatch = evaluate_level0_acceptance(
        Level0AcceptanceInput(
            checks={f"L0-{index:02d}": True for index in range(1, 21)},
            evidence_complete=False,
            robot_identity_hash_matches=False,
            config_hash_matches=False,
            site_session_valid=True,
            safety_reviewer_approved=True,
            write_operation_count=0,
            hardware_motion_observed=False,
            worktree_clean=True,
            source_tree_hash_matches=True,
        )
    )

    assert mismatch.highest_acceptance_level == "NONE"
    assert "evidence incomplete" in mismatch.blockers
    assert "robot identity hash mismatch" in mismatch.blockers
    assert "config hash mismatch" in mismatch.blockers


def test_hardware_mode_without_site_config_is_environment_blocked(tmp_path: Path) -> None:
    from scripts.verify_phase10_2c_level0 import run_hardware_verification

    payload = run_hardware_verification(tmp_path, config_path=None)

    assert payload["status"] == "PHASE10_LEVEL0_ENV_BLOCKED"
    assert payload["controller_contacted"] is False
    assert payload["write_operation_count"] == 0


def test_no_write_operation_evidence_schema(tmp_path: Path) -> None:
    from scripts.verify_phase10_2c_level0 import run_fake_verification

    run_fake_verification(tmp_path)
    payload = json.loads((tmp_path / "no_write_operation_evidence.json").read_text())

    assert payload["write_operation_count"] == 0
    assert payload["forbidden_methods_exposed"] == []
    assert payload["hardware_motion_observed"] is False


def test_dashboard_acceptance_surfaces_level0_fake_read_only_without_promotion(
    tmp_path: Path,
) -> None:
    from scripts.verify_phase10_2c_level0 import run_fake_verification

    from cloud_edge_robot_arm.dashboard.service import DashboardService

    artifact_root = tmp_path / "artifacts"
    run_fake_verification(artifact_root / "phase10" / "level0")

    snapshot = DashboardService(artifact_root=artifact_root).acceptance()
    level0 = snapshot.level0_read_only

    assert snapshot.current_level == "NONE"
    assert snapshot.hardware_motion_allowed is False
    assert level0.mode_label == "REAL HARDWARE - READ ONLY"
    assert level0.controller_state == "READ_ONLY"
    assert level0.emergency_stop_state == "INACTIVE"
    assert level0.fault_state == "CLEAR"
    assert level0.operation_mode == "READ_ONLY"
    assert level0.joint_state_freshness == "FRESH"
    assert level0.tcp_pose_freshness == "FRESH"
    assert level0.evidence_complete is True
    assert "fake adapter" in " ".join(level0.blockers)


def test_dashboard_has_no_level1_or_hardware_write_route(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fastapi.testclient import TestClient

    from cloud_edge_robot_arm.cloud.api.app import create_app
    from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
    from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline

    monkeypatch.setenv("DASHBOARD_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    client = TestClient(create_app(PlanningPipeline(planner=MockPlannerAdapter())))

    capabilities = client.get("/api/v1/dashboard/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json()["hardware_write_operations"] == []
    assert client.post("/api/v1/dashboard/acceptance/level1").status_code == 404


def test_acceptance_store_accepts_only_complete_level0_hardware_evidence(
    tmp_path: Path,
) -> None:
    from scripts.verify_phase10_2c_level0 import run_fake_verification

    from cloud_edge_robot_arm.real_robot.acceptance import (
        RealRobotAcceptanceLevel,
        RealRobotAcceptanceStore,
    )

    fake_summary = tmp_path / "fake" / "level0_summary.json"
    run_fake_verification(tmp_path / "fake")
    store = RealRobotAcceptanceStore(tmp_path / "acceptance_state.json")

    with pytest.raises(ValueError, match="real hardware"):
        store.mark_passed(
            RealRobotAcceptanceLevel.LEVEL_0,
            evidence_path=fake_summary,
            config_hash="fake-config-hash",
            source_tree_hash="tree",
            robot_identity_hash="robot",
            operator_confirmation={"confirmation_id": "fake-level0-session"},
        )

    hardware_summary = tmp_path / "hardware_level0_summary.json"
    hardware_summary.write_text(
        json.dumps(
            {
                "status": "PHASE10_HARDWARE_READ_ONLY_ACCEPTED",
                "requested_level": "LEVEL_0",
                "validation_claimed": True,
                "real_hardware_validation_claimed": True,
                "controller_contacted": True,
                "hardware_state_sampled": True,
                "hardware_motion_observed": False,
                "write_operation_count": 0,
                "highest_acceptance_level": "LEVEL_0",
                "level1_allowed": False,
                "robot_identity_hash": "robot",
                "config_hash": "config",
                "source_tree_hash": "tree",
                "worktree_clean": True,
                "evidence_complete": True,
                "checks": {f"L0-{index:02d}": True for index in range(1, 21)},
                "operator_confirmation": {"confirmation_id": "session-accepted"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    store.mark_passed(
        RealRobotAcceptanceLevel.LEVEL_0,
        evidence_path=hardware_summary,
        config_hash="config",
        source_tree_hash="tree",
        robot_identity_hash="robot",
        operator_confirmation={"confirmation_id": "session-accepted"},
    )

    assert store.current_level() == RealRobotAcceptanceLevel.LEVEL_0
