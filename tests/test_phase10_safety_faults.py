from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from cloud_edge_robot_arm.real_robot.config import RealRobotRuntimeSettings
    from cloud_edge_robot_arm.real_robot.gate import HardwareTelemetryStatus


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


def _gate_settings() -> RealRobotRuntimeSettings:
    from cloud_edge_robot_arm.real_robot.config import (
        ExecutionMode,
        RealRobotConfig,
        RealRobotRuntimeSettings,
    )

    return RealRobotRuntimeSettings(
        runtime_profile="production",
        execution_mode=ExecutionMode.HARDWARE_LOW_SPEED,
        enable_real_robot=True,
        config=RealRobotConfig.model_validate(_valid_config_payload()),
        operator_confirmation_token="operator-confirmed",
    )


def _telemetry() -> HardwareTelemetryStatus:
    from cloud_edge_robot_arm.real_robot.gate import HardwareTelemetryStatus

    return HardwareTelemetryStatus(
        sample_time=datetime.now(UTC),
        monotonic_age_ms=100,
        max_allowed_age_ms=500,
    )


@pytest.mark.parametrize(
    ("field", "expected_code"),
    [
        ("emergency_stop_active", "EMERGENCY_STOP_ACTIVE"),
        ("controller_connected", "CONTROLLER_NOT_CONNECTED"),
        ("safety_shield_healthy", "SAFETY_SHIELD_UNHEALTHY"),
    ],
)
def test_gate_rejects_critical_hardware_faults(field: str, expected_code: str) -> None:
    from cloud_edge_robot_arm.real_robot.gate import HardwareExecutionGate, HardwareGateInput

    payload = {
        "controller_connected": True,
        "emergency_stop_active": False,
        "safety_shield_healthy": True,
        "telemetry": _telemetry(),
        "requested_velocity_scale": 0.05,
        "requested_acceleration_scale": 0.05,
        "acceptance_level": "LEVEL_2",
        "required_acceptance_level": "LEVEL_2",
    }
    payload[field] = not payload[field]

    decision = HardwareExecutionGate(settings=_gate_settings()).evaluate(
        HardwareGateInput.model_validate(payload)
    )

    assert decision.allowed is False
    assert expected_code in decision.reason_codes


def test_gate_rejects_velocity_acceleration_and_acceptance_level_bypass() -> None:
    from cloud_edge_robot_arm.real_robot.gate import HardwareExecutionGate, HardwareGateInput

    decision = HardwareExecutionGate(settings=_gate_settings()).evaluate(
        HardwareGateInput(
            controller_connected=True,
            emergency_stop_active=False,
            safety_shield_healthy=True,
            telemetry=_telemetry(),
            requested_velocity_scale=0.2,
            requested_acceleration_scale=0.2,
            acceptance_level="LEVEL_1",
            required_acceptance_level="LEVEL_2",
        )
    )

    assert decision.allowed is False
    assert "VELOCITY_SCALE_EXCEEDS_REAL_LIMIT" in decision.reason_codes
    assert "ACCELERATION_SCALE_EXCEEDS_REAL_LIMIT" in decision.reason_codes
    assert "ACCEPTANCE_LEVEL_INSUFFICIENT" in decision.reason_codes


def test_environment_blocked_real_robot_adapter_is_read_only_and_structured() -> None:
    from cloud_edge_robot_arm.real_robot.adapter import EnvironmentBlockedRealRobotAdapter

    adapter = EnvironmentBlockedRealRobotAdapter(blocker="controller not configured")

    assert adapter.connect(timeout_ms=10).success is False
    assert adapter.health().ok is False
    assert adapter.get_controller_state().status == "ENVIRONMENT_BLOCKED"
    assert adapter.get_emergency_stop_state().status == "UNKNOWN"
    assert adapter.get_fault_state().faulted is True


def test_hardware_audit_evidence_completeness() -> None:
    from cloud_edge_robot_arm.real_robot.evidence import audit_evidence_complete

    complete = {
        "config_hash": "abc",
        "software_commit": "e36e28d",
        "operator_confirmation": "operator-confirmed",
        "robot_state_before": {},
        "robot_state_after": {},
        "trajectory_summary": {},
        "safety_decision": {},
        "stop_status": {},
        "result": "REJECTED",
    }

    assert audit_evidence_complete(complete) is True
    incomplete = dict(complete)
    incomplete.pop("operator_confirmation")
    assert audit_evidence_complete(incomplete) is False
