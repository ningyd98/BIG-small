"""运行时条件评估器。

执行技能前检查任务前置条件和机器人状态，失败时返回结构化错误而不是继续执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cloud_edge_robot_arm.contracts import RobotState, TaskContract
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionSpec,
    ConditionStatus,
    OnlineEvidenceSnapshot,
    evaluate_conditions,
)
from cloud_edge_robot_arm.edge.runtime.errors import PRECONDITION_FAILED, runtime_error
from cloud_edge_robot_arm.edge.runtime.skill_registry import RuntimeSkillRobot
from cloud_edge_robot_arm.errors import StructuredError


@dataclass(frozen=True)
class ConditionEvaluation:
    success: bool
    status: ConditionStatus = ConditionStatus.FAIL
    failed_condition: str | None = None
    error: StructuredError | None = None


class ConditionEvaluator:
    def __init__(
        self,
        *,
        evaluation_scope: Literal["VISION_CLOSED_LOOP", "LEGACY_PIPELINE"] = "VISION_CLOSED_LOOP",
    ) -> None:
        if evaluation_scope not in {"VISION_CLOSED_LOOP", "LEGACY_PIPELINE"}:
            raise ValueError("unknown condition evaluation scope")
        self._evaluation_scope = evaluation_scope

    def evaluate_preconditions(
        self,
        *,
        robot: RuntimeSkillRobot,
        contract: TaskContract,
        conditions: list[str],
        evidence: OnlineEvidenceSnapshot | None = None,
    ) -> ConditionEvaluation:
        return self._evaluate(
            robot=robot,
            contract=contract,
            conditions=conditions,
            evidence=evidence,
            error_code=PRECONDITION_FAILED,
        )

    def evaluate_success_conditions(
        self,
        *,
        robot: RuntimeSkillRobot,
        contract: TaskContract,
        conditions: list[str],
        evidence: OnlineEvidenceSnapshot | None = None,
    ) -> ConditionEvaluation:
        return self._evaluate(
            robot=robot,
            contract=contract,
            conditions=conditions,
            evidence=evidence,
            error_code="RESULT_NOT_VERIFIED",
        )

    def _evaluate(
        self,
        *,
        robot: RuntimeSkillRobot,
        contract: TaskContract,
        conditions: list[str],
        evidence: OnlineEvidenceSnapshot | None = None,
        error_code: str,
    ) -> ConditionEvaluation:
        if self._evaluation_scope != "LEGACY_PIPELINE":
            if not conditions:
                return ConditionEvaluation(success=True, status=ConditionStatus.PASS)
            if evidence is None:
                return ConditionEvaluation(
                    success=False,
                    status=ConditionStatus.UNKNOWN,
                    failed_condition=conditions[0],
                    error=runtime_error(
                        error_code,
                        "online RGB-D evidence is required",
                        details={"condition": conditions[0], "status": "UNKNOWN"},
                    ),
                )
            verdicts = evaluate_conditions(
                [
                    ConditionSpec(
                        name,
                        target_id=contract.task_target.object_id,
                        tolerances={
                            "minimum_safe_height": contract.safety_constraints.minimum_safe_height
                        },
                    )
                    for name in conditions
                ],
                evidence,
            )
            failed = next(
                (verdict for verdict in verdicts if verdict.status != ConditionStatus.PASS), None
            )
            if failed is not None:
                return ConditionEvaluation(
                    success=False,
                    status=failed.status,
                    failed_condition=failed.condition_name,
                    error=runtime_error(
                        error_code,
                        "online condition did not pass",
                        details={
                            "condition": failed.condition_name,
                            "status": failed.status.value,
                            "reasons": list(failed.reasons),
                        },
                    ),
                )
            return ConditionEvaluation(success=True, status=ConditionStatus.PASS)
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
        return ConditionEvaluation(success=True, status=ConditionStatus.PASS)

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
            "robot_at_home",
            "tcp_above_safe_height",
        }:
            return state.tcp_pose.z >= contract.safety_constraints.minimum_safe_height
        if condition == "gripper_closed":
            return not state.gripper_open
        if condition == "object_placed":
            return state.holding_object_id is None and state.gripper_open
        if condition == "object_released":
            return state.gripper_open and state.holding_object_id is None
        # Generic skill-completed conditions
        if condition.startswith("skill_") and condition.endswith("_completed"):
            return True
        return False
