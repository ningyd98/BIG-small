from __future__ import annotations

from cloud_edge_robot_arm.contracts import ActionResult, RobotState
from cloud_edge_robot_arm.edge.safety.errors import STOP_FAILED
from cloud_edge_robot_arm.edge.safety.stop_controller import StopController
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene


def test_safety_stopped_invokes_robot_stop() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    controller = StopController(robot)

    result = controller.execute_stop()

    assert result.success is True
    assert result.method_used == "stop"
    assert result.verified_stopped is True
    assert robot.get_state().stopped is True


def test_stop_failure_falls_back_to_emergency_stop() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.state.stopped = False

    class FailingStopRobot:
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
                success=True,
                state_before={},
                state_after={},
                duration_ms=10,
            )

        def get_state(self) -> RobotState:
            return RobotState(connected=True, stopped=True, estop_engaged=True)

    controller = StopController(FailingStopRobot())
    result = controller.execute_stop()

    assert result.success is True
    assert result.method_used == "emergency_stop"
    assert result.verified_estop is True


def test_stop_actions_are_persisted() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    controller = StopController(robot)

    result = controller.execute_stop()

    assert result.stop_action_result is not None
    assert result.stop_action_result.action_type == "STOP"
    assert result.stop_action_result.success is True


def test_stop_state_is_verified() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    controller = StopController(robot)

    result = controller.execute_stop()

    state = robot.get_state()
    assert state.stopped is True
    assert result.verified_stopped is True


def test_both_stop_methods_failure_returns_safety_stop_failed() -> None:
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

    controller = StopController(AlwaysFailRobot())
    result = controller.execute_stop()

    assert result.success is False
    assert result.error is not None
    assert result.error.code == STOP_FAILED
    assert result.verified_stopped is False
    assert result.verified_estop is False


def test_no_future_steps_after_safety_stop() -> None:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        auto_connect=True,
        grasp_failures_remaining=5,
    )
    from cloud_edge_robot_arm.contracts import SkillName
    from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
    from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
    from cloud_edge_robot_arm.repositories.memory import InMemoryRepository
    from tests.phase2_helpers import contract, step

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

    result = TaskExecutor(
        robot=robot, shield=SafetyShield(), repository=InMemoryRepository()
    ).submit_contract(task.model_dump(mode="json"))

    assert result.success is False
    assert result.context is not None
    assert result.context.failed_step_id == "step-grasp"
    assert "LIFT" not in [e.action_type for e in robot.history]


def test_task_executor_rejects_disconnected_robot() -> None:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=False)
    from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
    from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
    from tests.phase2_helpers import contract

    result = TaskExecutor(robot=robot, shield=SafetyShield()).submit_contract(
        contract().model_dump(mode="json")
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "ROBOT_DISCONNECTED"
