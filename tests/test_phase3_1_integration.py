from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest

from cloud_edge_robot_arm.contracts import (
    ActionResult,
    RobotState,
    SafetyDecision,
    SkillName,
)
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
from cloud_edge_robot_arm.edge.safety.models import Obstacle, SafetyContext
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
from cloud_edge_robot_arm.simulation.mock_robot import FaultCode, MockRobotAdapter, MockScene
from tests.phase2_helpers import contract, step


def _shield() -> SafetyShield:
    return SafetyShield()


def _executor(
    robot: MockRobotAdapter,
    shield: SafetyShield | None = None,
    repository: InMemoryRepository | None = None,
) -> TaskExecutor:
    return TaskExecutor(
        robot=robot,
        shield=shield or _shield(),
        repository=repository or InMemoryRepository(),
    )


def test_task_executor_requires_safety_shield() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    with pytest.raises(TypeError):
        TaskExecutor(robot=robot)  # type: ignore[call-arg]


def test_unsafe_contract_never_reaches_robot_handler() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    task = contract(
        steps=[
            step(
                "step-move",
                SkillName.MOVE_ABOVE,
                parameters={"object_id": "red_cube", "z_offset_m": 0.12},
            ),
        ],
        local_retry_limit=0,
    )
    payload = task.model_dump(mode="json")
    payload["steps"][0]["parameters"]["disable_safety"] = True

    result = _executor(robot).submit_contract(payload)

    assert result.success is False
    assert robot.history == []


def test_workspace_target_violation_blocks_task_execution() -> None:
    c = contract(
        task_id="task-ws-violation",
        steps=[
            step(
                "step-move",
                SkillName.MOVE_ABOVE,
                parameters={"object_id": "red_cube", "z_offset_m": 0.12},
            ),
        ],
        local_retry_limit=0,
    )
    shield = _shield()
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-move",
        skill="MOVE_ABOVE",
        contract=c,
        robot_connected=True,
        tcp_x=1.0,
        tcp_y=0.0,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=datetime.now(UTC),
        telemetry_timestamp=datetime.now(UTC),
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    assert result.allowed is False
    assert result.decision == SafetyDecision.REJECT


def test_path_collision_blocks_task_execution() -> None:
    shield = _shield()
    c = contract(task_id="task-path-collision")
    obs = Obstacle(obstacle_id="wall", x=0.1, y=0.0, z=0.18, radius_m=0.05)
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-move",
        skill="MOVE_ABOVE",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=0.0,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=datetime.now(UTC),
        telemetry_timestamp=datetime.now(UTC),
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        obstacles=[obs],
        parameters={"object_id": "red_cube", "target_pose": {"x": 0.2, "y": 0.0, "z": 0.3}},
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    assert result.allowed is False


def test_safety_pause_transitions_task_to_paused() -> None:
    shield = _shield()
    c = contract(task_id="task-pause")
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-home",
        skill="HOME",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=None,
        telemetry_timestamp=None,
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    assert result.allowed is False
    assert result.decision == SafetyDecision.PAUSE


def test_emergency_stop_decision_invokes_stop_controller() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.inject_fault(FaultCode.COLLISION_DETECTED)
    result = _executor(robot).submit_contract(contract().model_dump(mode="json"))

    assert result.success is False
    assert result.context is not None
    assert result.context.state == "SAFETY_STOPPED"
    assert robot.get_state().stopped is True


def test_allow_with_limits_executes_limited_parameters() -> None:
    shield = _shield()
    c = contract(task_id="task-limits")
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-home",
        skill="HOME",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
        tcp_velocity=0.1,
        scene_version=1,
        scene_updated_at=datetime.now(UTC),
        telemetry_timestamp=datetime.now(UTC),
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    assert result.decision in {SafetyDecision.ALLOW, SafetyDecision.ALLOW_WITH_LIMITS}


def test_post_check_failure_stops_remaining_steps() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        auto_connect=True,
        grasp_failures_remaining=5,
    )
    task = contract(
        steps=[
            step(
                "step-grasp", SkillName.GRASP, parameters={"object_id": "red_cube"}, retry_limit=0
            ),
            step(
                "step-lift",
                SkillName.LIFT,
                parameters={"height_m": 0.16},
                preconditions=["object_attached"],
            ),
        ],
        local_retry_limit=0,
    )
    result = _executor(robot).submit_contract(task.model_dump(mode="json"))

    assert result.success is False
    assert result.context is not None
    assert "LIFT" not in [e.action_type for e in robot.history]


def test_missing_telemetry_fails_closed() -> None:
    shield = _shield()
    c = contract(task_id="task-no-tel")
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-home",
        skill="HOME",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=datetime.now(UTC),
        telemetry_timestamp=None,
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    assert result.allowed is False
    assert result.decision == SafetyDecision.PAUSE


def test_missing_scene_timestamp_fails_closed() -> None:
    shield = _shield()
    c = contract(task_id="task-no-scene")
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-home",
        skill="HOME",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=None,
        telemetry_timestamp=datetime.now(UTC),
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    assert result.allowed is False
    assert result.decision == SafetyDecision.PAUSE


def test_missing_watchdog_fails_closed() -> None:
    shield = _shield()
    c = contract(task_id="task-no-watchdog")
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-home",
        skill="HOME",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=datetime.now(UTC),
        telemetry_timestamp=datetime.now(UTC),
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        step_started_at=time.monotonic(),
        task_started_at_mono=None,
    )
    result = shield.pre_check(ctx)
    assert result.allowed is False
    codes = [r.rule_id for r in result.evaluated_rules if r.decision != SafetyDecision.ALLOW]
    assert "WATCHDOG" in codes


def test_missing_step_start_time_fails_closed() -> None:
    shield = _shield()
    c = contract(task_id="task-no-step-start")
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-home",
        skill="HOME",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=datetime.now(UTC),
        telemetry_timestamp=datetime.now(UTC),
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        step_started_at=None,
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    assert result.allowed is False
    codes = [r.rule_id for r in result.evaluated_rules if r.decision != SafetyDecision.ALLOW]
    assert "STEP_TIMEOUT" in codes


def test_target_pose_not_current_pose_is_checked() -> None:
    shield = _shield()
    c = contract(task_id="task-target-check")
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-move",
        skill="MOVE_ABOVE",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=datetime.now(UTC),
        telemetry_timestamp=datetime.now(UTC),
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        parameters={"object_id": "red_cube", "target_pose": {"x": 1.0, "y": 0.0, "z": 0.18}},
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    assert result.allowed is False
    ws_rules = [r for r in result.evaluated_rules if r.rule_id == "WORKSPACE"]
    assert any(r.decision == SafetyDecision.REJECT for r in ws_rules)


def test_task_contract_cannot_disable_collision_check() -> None:
    shield = _shield()
    c = contract(task_id="task-no-collision-check")
    object.__setattr__(c.safety_constraints, "collision_check_required", False)
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-move",
        skill="MOVE_ABOVE",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=datetime.now(UTC),
        telemetry_timestamp=datetime.now(UTC),
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    path_rules = [r for r in result.evaluated_rules if r.rule_id == "PATH_COLLISION"]
    assert len(path_rules) == 1
    assert path_rules[0].decision == SafetyDecision.REJECT


def test_merged_hard_limit_overrides_contract_limit() -> None:
    c = contract(task_id="task-merged")
    object.__setattr__(c.safety_constraints, "max_tcp_velocity", 100.0)
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-move",
        skill="MOVE_ABOVE",
        contract=c,
        robot_connected=True,
        tcp_x=0.2,
        tcp_y=0.0,
        tcp_z=0.18,
        tcp_velocity=2.0,
        scene_version=1,
        scene_updated_at=datetime.now(UTC),
        telemetry_timestamp=datetime.now(UTC),
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=datetime.now(UTC),
        task_deadline_utc=c.valid_until,
        merged_max_tcp_velocity=0.5,
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    shield = _shield()
    result = shield.pre_check(ctx)
    vel_rules = [r for r in result.evaluated_rules if r.rule_id == "TCP_VEL"]
    assert len(vel_rules) == 1
    assert vel_rules[0].decision == SafetyDecision.REJECT


def test_safety_stop_failure_not_marked_safety_stopped() -> None:
    class AlwaysFailRobot:
        def stop(self, *, timeout_ms: int | None = None) -> ActionResult:
            from cloud_edge_robot_arm.edge.robot_adapter import build_action_result

            return build_action_result(
                action_type="STOP",
                success=False,
                state_before={},
                state_after={},
                duration_ms=0,
                error_code="STOP_FAILED",
                error_message="stop failed",
            )

        def emergency_stop(self, *, timeout_ms: int | None = None) -> ActionResult:
            from cloud_edge_robot_arm.edge.robot_adapter import build_action_result

            return build_action_result(
                action_type="EMERGENCY_STOP",
                success=False,
                state_before={},
                state_after={},
                duration_ms=0,
                error_code="ESTOP_FAILED",
                error_message="estop failed",
            )

        def get_state(self) -> RobotState:
            return RobotState(connected=True, stopped=False, estop_engaged=False)

    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.stop = AlwaysFailRobot().stop  # type: ignore
    robot.emergency_stop = AlwaysFailRobot().emergency_stop  # type: ignore
    robot.state.stopped = False
    robot.state.estop_engaged = False
    robot.inject_fault(FaultCode.COLLISION_DETECTED)

    result = _executor(robot).submit_contract(contract().model_dump(mode="json"))

    assert result.success is False
    assert result.context is not None
    assert result.context.state == "FAILED"


def test_normal_full_task_passes_integrated_safety_shield() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    repository = InMemoryRepository()
    result = _executor(robot, repository=repository).submit_contract(
        contract().model_dump(mode="json")
    )

    assert result.success is True
    assert result.context is not None
    assert result.context.state == "COMPLETED"
    assert result.context.completed_step_ids == [
        item.step_id for item in result.context.contract.steps
    ]
    assert robot.object_region("red_cube") == "bin_a"
