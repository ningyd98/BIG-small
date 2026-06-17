from __future__ import annotations

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


def test_real_robot_config_requires_site_values_and_hashes_source(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.real_robot.config import RealRobotConfig, load_real_robot_config

    config_path = tmp_path / "real_robot.yaml"
    config_path.write_text(
        "\n".join(f"{key}: {value}" for key, value in {"robot_vendor": "REPLACE_ME"}.items()),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="placeholder"):
        load_real_robot_config(config_path)

    config = RealRobotConfig.model_validate(_valid_config_payload())
    sourced = config.with_source("unit-test", raw_payload=_valid_config_payload())

    assert sourced.config_hash
    assert sourced.config_source == "unit-test"
    assert sourced.velocity_scale <= 0.1
    assert sourced.acceleration_scale <= 0.1


def test_simulation_profile_and_simulation_config_are_rejected_for_real_robot() -> None:
    from cloud_edge_robot_arm.real_robot.config import (
        ExecutionMode,
        RealRobotConfig,
        RealRobotRuntimeSettings,
    )

    cfg = RealRobotConfig.model_validate(_valid_config_payload())
    with pytest.raises(ValueError, match="simulation"):
        RealRobotRuntimeSettings(
            runtime_profile="simulation",
            execution_mode=ExecutionMode.HARDWARE_LOW_SPEED,
            enable_real_robot=True,
            config=cfg,
            operator_confirmation_token="operator-confirmed",
        )

    with pytest.raises(ValueError, match="simulation config"):
        RealRobotConfig.model_validate(
            {
                **_valid_config_payload(),
                "config_source": "configs/phase9/simulator.yaml",
            }
        )


def test_hardware_gate_fails_closed_and_records_rejection_reason() -> None:
    from cloud_edge_robot_arm.real_robot.config import (
        ExecutionMode,
        RealRobotConfig,
        RealRobotRuntimeSettings,
    )
    from cloud_edge_robot_arm.real_robot.gate import (
        HardwareExecutionGate,
        HardwareGateInput,
        HardwareTelemetryStatus,
    )

    cfg = RealRobotConfig.model_validate(_valid_config_payload())
    settings = RealRobotRuntimeSettings(
        runtime_profile="production",
        execution_mode=ExecutionMode.HARDWARE_LOW_SPEED,
        enable_real_robot=False,
        config=cfg,
        operator_confirmation_token="operator-confirmed",
    )
    gate = HardwareExecutionGate(settings=settings)
    decision = gate.evaluate(
        HardwareGateInput(
            controller_connected=True,
            emergency_stop_active=False,
            safety_shield_healthy=True,
            telemetry=HardwareTelemetryStatus(
                sample_time=datetime.now(UTC),
                monotonic_age_ms=100,
                max_allowed_age_ms=500,
            ),
            requested_velocity_scale=0.05,
            requested_acceleration_scale=0.05,
            acceptance_level="LEVEL_2",
            required_acceptance_level="LEVEL_2",
        )
    )

    assert decision.allowed is False
    assert "ENABLE_REAL_ROBOT_FALSE" in decision.reason_codes
    assert gate.audit_events[-1].event_type == "HARDWARE_GATE_REJECTED"


def test_dry_run_validates_contract_without_hardware_execution() -> None:
    from cloud_edge_robot_arm.real_robot.config import ExecutionMode, RealRobotRuntimeSettings
    from cloud_edge_robot_arm.real_robot.dry_run import DryRunValidationService

    task = contract(
        task_id="phase10-dry-run",
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
    )

    result = service.validate(task.model_dump(mode="json"))

    assert result.status == "DRY_RUN_VALIDATED"
    assert result.validation_claimed is True
    assert result.hardware_execution_status == "PLANNED_ONLY"
    assert result.sent_to_hardware is False
    assert result.trajectory_summary.path_length_m >= 0
    assert result.safety_margin.minimum_distance_m >= 0


def test_acceptance_levels_are_persistent_and_block_higher_level_skills(tmp_path: Path) -> None:
    from cloud_edge_robot_arm.real_robot.acceptance import (
        RealRobotAcceptanceLevel,
        RealRobotAcceptanceStore,
        required_level_for_skill,
    )

    store = RealRobotAcceptanceStore(tmp_path / "acceptance_state.json")
    assert store.current_level() == RealRobotAcceptanceLevel.NONE
    assert store.is_allowed(RealRobotAcceptanceLevel.LEVEL_2) is False

    store.mark_passed(RealRobotAcceptanceLevel.LEVEL_1, evidence_path="artifact.json")
    assert RealRobotAcceptanceStore(tmp_path / "acceptance_state.json").current_level() == (
        RealRobotAcceptanceLevel.LEVEL_1
    )
    assert required_level_for_skill("single_joint_small_motion") == RealRobotAcceptanceLevel.LEVEL_2
    assert store.is_allowed(required_level_for_skill("single_joint_small_motion")) is False


def test_real_result_claim_protection_rejects_dry_run_as_hardware_executed() -> None:
    from cloud_edge_robot_arm.real_robot.evidence import RealRobotRunEvidence

    with pytest.raises(ValueError, match="dry-run"):
        RealRobotRunEvidence(
            run_id="run-1",
            execution_status="HARDWARE_EXECUTED",
            execution_mode="DRY_RUN",
            validation_claimed=True,
            artifact_provenance_complete=True,
            hardware_motion_observed=False,
        )


def test_sim_to_real_pair_schema_requires_real_backend_identity() -> None:
    from cloud_edge_robot_arm.real_robot.sim_to_real import SimToRealPair

    with pytest.raises(ValueError, match="real hardware"):
        SimToRealPair(
            pair_id="pair-1",
            task_contract_hash="abc123",
            simulation_backend="isaac",
            real_backend="mock",
            software_commit="e36e28d",
            metrics={
                "planning_time_ms": 10,
                "actual_execution_time_ms": 0,
                "tcp_trajectory_length_m": 0.0,
                "final_position_error_m": 0.0,
                "skill_duration_ms": 0,
                "safety_interventions": 0,
                "retry_count": 0,
                "success_rate": 0.0,
            },
            gap_labels=["model_gap"],
        )


def test_stale_telemetry_blocks_hardware_gate() -> None:
    from cloud_edge_robot_arm.real_robot.config import (
        ExecutionMode,
        RealRobotConfig,
        RealRobotRuntimeSettings,
    )
    from cloud_edge_robot_arm.real_robot.gate import (
        HardwareExecutionGate,
        HardwareGateInput,
        HardwareTelemetryStatus,
    )

    cfg = RealRobotConfig.model_validate(_valid_config_payload())
    gate = HardwareExecutionGate(
        settings=RealRobotRuntimeSettings(
            runtime_profile="production",
            execution_mode=ExecutionMode.HARDWARE_LOW_SPEED,
            enable_real_robot=True,
            config=cfg,
            operator_confirmation_token="operator-confirmed",
        )
    )
    decision = gate.evaluate(
        HardwareGateInput(
            controller_connected=True,
            emergency_stop_active=False,
            safety_shield_healthy=True,
            telemetry=HardwareTelemetryStatus(
                sample_time=datetime.now(UTC) - timedelta(seconds=3),
                monotonic_age_ms=3_000,
                max_allowed_age_ms=500,
            ),
            requested_velocity_scale=0.05,
            requested_acceleration_scale=0.05,
            acceptance_level="LEVEL_2",
            required_acceptance_level="LEVEL_2",
        )
    )

    assert decision.allowed is False
    assert "TELEMETRY_STALE" in decision.reason_codes
