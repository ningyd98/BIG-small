from __future__ import annotations

from typing import Protocol

from cloud_edge_robot_arm.contracts import ActionResult, RobotState
from cloud_edge_robot_arm.edge.safety.errors import STOP_FAILED, safety_error
from cloud_edge_robot_arm.edge.safety.models import StopExecutionResult


class StopCapableRobot(Protocol):
    def stop(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def emergency_stop(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def get_state(self) -> RobotState: ...


class StopController:
    def __init__(self, robot: StopCapableRobot) -> None:
        self._robot = robot

    def execute_stop(self, *, timeout_ms: int = 1_000) -> StopExecutionResult:
        stop_result = self._robot.stop(timeout_ms=timeout_ms)
        state = self._robot.get_state()

        if stop_result.success and state.stopped:
            return StopExecutionResult(
                success=True,
                method_used="stop",
                stop_action_result=stop_result,
                verified_stopped=True,
            )

        estop_result = self._robot.emergency_stop(timeout_ms=timeout_ms)
        state_after_estop = self._robot.get_state()

        verified = state_after_estop.stopped or state_after_estop.estop_engaged

        if not verified:
            return StopExecutionResult(
                success=False,
                method_used="emergency_stop",
                stop_action_result=stop_result,
                estop_action_result=estop_result,
                verified_stopped=False,
                verified_estop=False,
                error=safety_error(
                    STOP_FAILED,
                    "both stop() and emergency_stop() failed to halt the robot",
                    details={
                        "stop_success": stop_result.success,
                        "estop_success": estop_result.success,
                        "robot_stopped": state_after_estop.stopped,
                        "robot_estop": state_after_estop.estop_engaged,
                    },
                ),
            )

        return StopExecutionResult(
            success=True,
            method_used="emergency_stop",
            stop_action_result=stop_result,
            estop_action_result=estop_result,
            verified_stopped=state_after_estop.stopped,
            verified_estop=state_after_estop.estop_engaged,
        )
