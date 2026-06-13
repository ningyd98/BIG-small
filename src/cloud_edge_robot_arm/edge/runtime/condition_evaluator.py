from __future__ import annotations

from dataclasses import dataclass

from cloud_edge_robot_arm.contracts import RobotState, TaskContract
from cloud_edge_robot_arm.edge.runtime.errors import PRECONDITION_FAILED, runtime_error
from cloud_edge_robot_arm.edge.runtime.skill_registry import RuntimeSkillRobot
from cloud_edge_robot_arm.errors import StructuredError


@dataclass(frozen=True)
class ConditionEvaluation:
    success: bool
    failed_condition: str | None = None
    error: StructuredError | None = None


class ConditionEvaluator:
    def evaluate_preconditions(
        self,
        *,
        robot: RuntimeSkillRobot,
        contract: TaskContract,
        conditions: list[str],
    ) -> ConditionEvaluation:
        return self._evaluate(
            robot=robot,
            contract=contract,
            conditions=conditions,
            error_code=PRECONDITION_FAILED,
        )

    def evaluate_success_conditions(
        self,
        *,
        robot: RuntimeSkillRobot,
        contract: TaskContract,
        conditions: list[str],
    ) -> ConditionEvaluation:
        return self._evaluate(
            robot=robot,
            contract=contract,
            conditions=conditions,
            error_code="RESULT_NOT_VERIFIED",
        )

    def _evaluate(
        self,
        *,
        robot: RuntimeSkillRobot,
        contract: TaskContract,
        conditions: list[str],
        error_code: str,
    ) -> ConditionEvaluation:
        state = robot.get_state()
        if not isinstance(state, RobotState):
            return ConditionEvaluation(
                success=False,
                failed_condition="robot_state_available",
                error=runtime_error(
                    error_code,
                    "robot adapter did not return a RobotState",
                    details={"condition": "robot_state_available"},
                ),
            )

        for condition in conditions:
            if self._condition_passes(condition, robot=robot, contract=contract, state=state):
                continue
            return ConditionEvaluation(
                success=False,
                failed_condition=condition,
                error=runtime_error(
                    error_code,
                    f"condition {condition!r} was not satisfied",
                    details={"condition": condition},
                ),
            )
        return ConditionEvaluation(success=True)

    def _condition_passes(
        self,
        condition: str,
        *,
        robot: RuntimeSkillRobot,
        contract: TaskContract,
        state: RobotState,
    ) -> bool:
        target = contract.task_target
        if condition == "object_attached":
            return state.holding_object_id == target.object_id
        if condition == "object_inside_target_region":
            return robot.object_region(target.object_id) == target.target_region_id
        if condition == "gripper_open":
            return state.gripper_open
        if condition == "robot_in_safe_pose":
            return state.tcp_pose.z >= contract.safety_constraints.minimum_safe_height
        if condition == "robot_stopped":
            return state.stopped or state.estop_engaged
        if condition in {
            "target_visible",
            "target_reachable",
            "tcp_above_target",
            "tcp_near_target",
            "tcp_above_region",
            "robot_clear_of_object",
        }:
            return state.tcp_pose.z >= contract.safety_constraints.minimum_safe_height
        return False
