from __future__ import annotations

from cloud_edge_robot_arm.contracts import SkillName
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
from cloud_edge_robot_arm.simulation.mock_robot import FaultCode, MockRobotAdapter, MockScene
from tests.phase2_helpers import contract, step


def _executor(
    robot: MockRobotAdapter, repository: InMemoryRepository | None = None
) -> TaskExecutor:
    return TaskExecutor(
        robot=robot,
        shield=SafetyShield(),
        repository=repository or InMemoryRepository(),
    )


def test_complete_valid_task_reaches_completed_state_and_records_audit_log() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    repository = InMemoryRepository()

    result = _executor(robot, repository).submit_contract(contract().model_dump(mode="json"))

    assert result.success is True
    assert result.context is not None
    assert result.context.state == "COMPLETED"
    assert result.context.completed_step_ids == [
        item.step_id for item in result.context.contract.steps
    ]
    assert robot.object_region("red_cube") == "bin_a"
    assert [event.event_type for event in repository.list_audit_events(result.context.task_id)] == [
        "CONTRACT_RECEIVED",
        "CONTRACT_ACCEPTED",
        "TASK_STATE_CHANGED",
        "TASK_STATE_CHANGED",
        "TASK_STATE_CHANGED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "STEP_STARTED",
        "STEP_COMPLETED",
        "TASK_STATE_CHANGED",
        "TASK_COMPLETED",
    ]


def test_invalid_contract_performs_zero_robot_actions() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    payload = contract().model_dump(mode="json")
    payload["steps"][0]["skill"] = "RUN_ARBITRARY_CODE"

    result = _executor(robot).submit_contract(payload)

    assert result.success is False
    assert result.error is not None
    assert result.error.code in {"UNSUPPORTED_SKILL", "CONTRACT_SCHEMA_INVALID"}
    assert robot.history == []


def test_step_failure_short_circuits_remaining_steps() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        auto_connect=True,
        grasp_failures_remaining=3,
    )
    task = contract(local_retry_limit=0)

    result = _executor(robot).submit_contract(task.model_dump(mode="json"))

    assert result.success is False
    assert result.context is not None
    assert result.context.failed_step_id == "step-grasp"
    assert "LIFT" not in [entry.action_type for entry in robot.history]
    assert result.context.state == "FAILED"


def test_retry_budget_uses_minimum_of_step_and_failure_policy_limits() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        auto_connect=True,
        grasp_failures_remaining=1,
    )
    task = contract(local_retry_limit=1)

    result = _executor(robot).submit_contract(task.model_dump(mode="json"))

    assert result.success is True
    assert result.context is not None
    assert result.context.step_attempts["step-grasp"] == 2
    retry_events = [
        event
        for event in result.repository.list_audit_events(result.context.task_id)
        if event.event_type == "STEP_RETRYING"
    ]
    assert len(retry_events) == 1


def test_parameter_validation_failure_does_not_call_robot_action() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    task = contract(
        steps=[
            step(
                "step-move-above",
                SkillName.MOVE_ABOVE,
                parameters={"z_offset_m": 0.12},
                success_conditions=["tcp_above_target"],
            )
        ]
    )

    result = _executor(robot).submit_contract(task.model_dump(mode="json"))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "INVALID_SKILL_PARAMETERS"
    assert robot.history == []


def test_precondition_failure_does_not_call_action() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    task = contract(
        steps=[
            step(
                "step-lift",
                SkillName.LIFT,
                parameters={"height_m": 0.16},
                preconditions=["object_attached"],
                success_conditions=["object_attached"],
            )
        ]
    )

    result = _executor(robot).submit_contract(task.model_dump(mode="json"))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "PRECONDITION_FAILED"
    assert robot.history == []


def test_step_timeout_enters_failed_state_after_retry_budget_exhausted() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        auto_connect=True,
        default_action_duration_ms=100,
    )
    task = contract(
        steps=[step("step-home", SkillName.HOME, timeout_ms=1, retry_limit=0)],
        local_retry_limit=0,
    )

    result = _executor(robot).submit_contract(task.model_dump(mode="json"))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == FaultCode.ACTION_TIMEOUT.value
    assert result.context is not None
    assert result.context.state == "FAILED"


def test_task_timeout_stops_execution() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        auto_connect=True,
        default_action_duration_ms=50,
    )
    task = contract(
        steps=[
            step("step-home", SkillName.HOME, timeout_ms=100),
            step("step-retreat", SkillName.RETREAT, parameters={"distance_m": 0.1}, timeout_ms=100),
        ],
        valid_ms=40,
        local_retry_limit=0,
    )

    result = _executor(robot).submit_contract(task.model_dump(mode="json"))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "TASK_TIMEOUT"
    assert result.context is not None
    assert result.context.state == "FAILED"
    assert "RETREAT" not in [entry.action_type for entry in robot.history]


def test_non_retryable_failure_enters_safety_stopped() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.inject_fault(FaultCode.COLLISION_DETECTED)

    result = _executor(robot).submit_contract(contract().model_dump(mode="json"))

    assert result.success is False
    assert result.error is not None
    assert result.error.code == FaultCode.COLLISION_DETECTED.value
    assert result.context is not None
    assert result.context.state == "SAFETY_STOPPED"
