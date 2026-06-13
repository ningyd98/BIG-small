from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cloud_edge_robot_arm.contracts import SafetyDecision
from cloud_edge_robot_arm.edge.safety.errors import (
    COLLISION_DETECTED,
    COMMAND_EXPIRED,
    DEVICE_DISCONNECTED,
    ESTOP_ACTIVE,
    FORBIDDEN_ZONE_VIOLATION,
    MINIMUM_HEIGHT_VIOLATION,
    OBSTACLE_DISTANCE_VIOLATION,
    REACHABILITY_VIOLATION,
    SCENE_VERSION_MISMATCH,
    TASK_DEADLINE_EXCEEDED,
    VELOCITY_EXCEEDED,
    WATCHDOG_TIMEOUT,
    WORKSPACE_VIOLATION,
)
from cloud_edge_robot_arm.edge.safety.models import (
    Obstacle,
    SafetyContext,
    WorkspaceDefinition,
)
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield, load_safety_config
from tests.phase2_helpers import contract


def _base_context(**overrides: object) -> SafetyContext:
    c = contract()
    now = datetime.now(UTC)
    defaults = dict(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-home",
        skill="HOME",
        contract=c,
        robot_connected=True,
        robot_stopped=False,
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=now,
        telemetry_timestamp=now,
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=now,
        task_deadline_utc=c.valid_until,
        task_started_at_mono=None,
    )
    for key, val in overrides.items():
        defaults[key] = val
    return SafetyContext(**defaults)  # type: ignore[arg-type]


def test_shield_allows_normal_motion_task() -> None:
    shield = SafetyShield()
    ctx = _base_context(
        step_id="step-home",
        skill="HOME",
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
    )

    result = shield.pre_check(ctx)

    assert result.allowed is True
    assert result.decision == SafetyDecision.ALLOW


def test_workspace_violation_is_rejected() -> None:
    shield = SafetyShield()
    ctx = _base_context(
        step_id="step-move",
        skill="MOVE_ABOVE",
        tcp_x=1.0,
        tcp_y=0.0,
        tcp_z=0.18,
    )

    result = shield.pre_check(ctx)

    assert result.allowed is False
    assert result.decision == SafetyDecision.REJECT
    codes = [r.reason_code for r in result.evaluated_rules]
    assert WORKSPACE_VIOLATION in codes


def test_reachability_violation_is_rejected() -> None:
    shield = SafetyShield()
    ctx = _base_context(
        step_id="step-move",
        skill="MOVE_ABOVE",
        tcp_x=0.8,
        tcp_y=0.0,
        tcp_z=0.18,
    )

    result = shield.pre_check(ctx)

    assert result.allowed is False
    codes = [r.reason_code for r in result.evaluated_rules]
    assert REACHABILITY_VIOLATION in codes


def test_velocity_exceeded_is_rejected() -> None:
    shield = SafetyShield()
    ctx = _base_context(
        step_id="step-move",
        skill="MOVE_ABOVE",
        tcp_x=0.2,
        tcp_y=0.0,
        tcp_z=0.18,
        tcp_velocity=10.0,
    )

    result = shield.pre_check(ctx)

    assert result.allowed is False
    codes = [r.reason_code for r in result.evaluated_rules]
    assert VELOCITY_EXCEEDED in codes


def test_minimum_height_violation_is_rejected() -> None:
    shield = SafetyShield()
    ctx = _base_context(
        step_id="step-retreat",
        skill="RETREAT",
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.02,
    )

    result = shield.pre_check(ctx)

    assert result.allowed is False
    codes = [r.reason_code for r in result.evaluated_rules]
    assert MINIMUM_HEIGHT_VIOLATION in codes


def test_low_height_exception_allows_approach() -> None:
    shield = SafetyShield()
    ctx = _base_context(
        step_id="step-approach",
        skill="APPROACH",
        tcp_x=0.2,
        tcp_y=0.0,
        tcp_z=0.02,
    )

    result = shield.pre_check(ctx)

    height_rules = [r for r in result.evaluated_rules if r.rule_id == "MIN_HEIGHT"]
    assert len(height_rules) == 1
    assert height_rules[0].decision == SafetyDecision.ALLOW


def test_obstacle_distance_violation_is_rejected() -> None:
    shield = SafetyShield()
    obs = Obstacle(obstacle_id="obs1", x=0.21, y=0.0, z=0.0, radius_m=0.05)
    ctx = _base_context(
        step_id="step-move",
        skill="MOVE_ABOVE",
        tcp_x=0.2,
        tcp_y=0.0,
        tcp_z=0.18,
        obstacles=[obs],
    )

    result = shield.pre_check(ctx)

    assert result.allowed is False
    codes = [r.reason_code for r in result.evaluated_rules]
    assert OBSTACLE_DISTANCE_VIOLATION in codes


def test_scene_version_mismatch_is_rejected() -> None:
    shield = SafetyShield()
    ctx = _base_context(scene_version=99)

    result = shield.pre_check(ctx)

    assert result.allowed is False
    codes = [r.reason_code for r in result.evaluated_rules]
    assert SCENE_VERSION_MISMATCH in codes


def test_command_expired_is_rejected() -> None:
    shield = SafetyShield()
    past = datetime(2020, 1, 1, tzinfo=UTC)
    ctx = _base_context(
        command_valid_until=past,
        wall_clock_now=datetime.now(UTC),
    )

    result = shield.pre_check(ctx)

    assert result.allowed is False
    codes = [r.reason_code for r in result.evaluated_rules]
    assert COMMAND_EXPIRED in codes


def test_estop_triggers_emergency_stop() -> None:
    shield = SafetyShield()
    ctx = _base_context(robot_estop_engaged=True)

    result = shield.pre_check(ctx)

    assert result.allowed is False
    assert result.decision == SafetyDecision.EMERGENCY_STOP
    codes = [r.reason_code for r in result.evaluated_rules]
    assert ESTOP_ACTIVE in codes


def test_collision_triggers_emergency_stop() -> None:
    shield = SafetyShield()
    ctx = _base_context(robot_collision_detected=True)

    result = shield.pre_check(ctx)

    assert result.allowed is False
    assert result.decision == SafetyDecision.EMERGENCY_STOP
    codes = [r.reason_code for r in result.evaluated_rules]
    assert COLLISION_DETECTED in codes


def test_disconnected_device_is_rejected() -> None:
    shield = SafetyShield()
    ctx = _base_context(robot_connected=False)

    result = shield.pre_check(ctx)

    assert result.allowed is False
    codes = [r.reason_code for r in result.evaluated_rules]
    assert DEVICE_DISCONNECTED in codes


def test_task_deadline_exceeded_is_rejected() -> None:
    shield = SafetyShield()
    past = datetime(2020, 1, 1, tzinfo=UTC)
    ctx = _base_context(
        task_deadline_utc=past,
        wall_clock_now=datetime.now(UTC),
    )

    result = shield.pre_check(ctx)

    assert result.allowed is False
    codes = [r.reason_code for r in result.evaluated_rules]
    assert TASK_DEADLINE_EXCEEDED in codes


def test_forbidden_zone_violation_is_rejected() -> None:
    shield = SafetyShield()
    zone = WorkspaceDefinition(
        workspace_id="forbidden_a",
        x_min=0.1,
        x_max=0.3,
        y_min=-0.1,
        y_max=0.1,
        z_min=0.0,
        z_max=1.0,
    )
    ctx = _base_context(
        step_id="step-move",
        skill="MOVE_ABOVE",
        tcp_x=0.2,
        tcp_y=0.0,
        tcp_z=0.18,
        forbidden_zones=[zone],
    )

    result = shield.pre_check(ctx)

    assert result.allowed is False
    codes = [r.reason_code for r in result.evaluated_rules]
    assert FORBIDDEN_ZONE_VIOLATION in codes


def test_normal_task_not_falsely_rejected() -> None:
    shield = SafetyShield()
    ctx = _base_context(
        step_id="step-home",
        skill="HOME",
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
    )

    result = shield.pre_check(ctx)

    assert result.allowed is True
    for rule in result.evaluated_rules:
        assert rule.decision in {SafetyDecision.ALLOW, SafetyDecision.ALLOW_WITH_LIMITS}


def test_safety_bypass_parameters_are_rejected() -> None:
    shield = SafetyShield()
    ctx = _base_context()
    object.__setattr__(ctx, "parameters", {"disable_safety": True})

    with pytest.raises(ValueError, match="disable_safety"):
        shield.pre_check(ctx)


def test_watchdog_timeout_triggers_emergency_stop() -> None:
    shield = SafetyShield()
    import time

    ctx = _base_context(
        task_started_at_mono=time.monotonic() - 60,
    )

    result = shield.pre_check(ctx)

    assert result.allowed is False
    codes = [r.reason_code for r in result.evaluated_rules]
    assert WATCHDOG_TIMEOUT in codes


def test_load_default_config() -> None:
    config = load_safety_config()

    assert config.policy_version == "1.0.0"
    assert config.policy_hash
    assert config.merged.max_tcp_velocity > 0
    assert config.merged.max_joint_velocity > 0


def test_rule_count() -> None:
    shield = SafetyShield()
    assert shield.rule_count == 21
