from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from cloud_edge_robot_arm.contracts import RobotState, SafetyDecision, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.runtime.errors import runtime_error
from cloud_edge_robot_arm.edge.runtime.skill_executor import (
    SkillExecutor,
    StepExecutionResult,
)
from cloud_edge_robot_arm.edge.runtime.skill_registry import RuntimeSkillRobot, SkillRegistry
from cloud_edge_robot_arm.edge.safety.context_builder import SafetyContextBuilder
from cloud_edge_robot_arm.edge.safety.errors import (
    safety_error,
)
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.errors import StructuredError

SAFETY_DECISION_ERROR_CODES: dict[str, str] = {
    "PAUSE": "SAFETY_PAUSE_REQUESTED",
    "REJECT": "SAFETY_ACTION_REJECTED",
    "REQUEST_CORRECTION": "SAFETY_REQUEST_CORRECTION",
    "EMERGENCY_STOP": "SAFETY_EMERGENCY_STOP",
}


class SafetySkillExecutor:
    def __init__(
        self,
        *,
        robot: RuntimeSkillRobot,
        registry: SkillRegistry,
        shield: SafetyShield,
        context_builder: SafetyContextBuilder,
        scene_version: int = 1,
        scene_updated_at: datetime | None = None,
        telemetry_timestamp: datetime | None = None,
    ) -> None:
        self._robot = robot
        self._registry = registry
        self._shield = shield
        self._context_builder = context_builder
        self._scene_version = scene_version
        now = datetime.now(UTC)
        self._scene_updated_at = scene_updated_at or now
        self._telemetry_timestamp = telemetry_timestamp or now
        self._task_started_at_mono: float | None = None
        self._step_started_at_mono: float | None = None
        self._skill_executor = SkillExecutor(robot=robot, registry=registry)

    def start_task(self) -> None:
        self._task_started_at_mono = time.monotonic()

    def start_step(self) -> None:
        self._step_started_at_mono = time.monotonic()

    def execute_attempt(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        attempt: int,
    ) -> StepExecutionResult:
        robot_state = self._robot.get_state()
        if not isinstance(robot_state, RobotState):
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=runtime_error(
                    "ROBOT_STATE_INVALID",
                    "robot adapter did not return a RobotState",
                ),
                action_result=None,
                duration_ms=0,
            )

        ctx = self._context_builder.build(
            contract=contract,
            step=step,
            robot_state=robot_state,
            scene_version=self._scene_version,
            scene_updated_at=self._scene_updated_at,
            telemetry_timestamp=self._telemetry_timestamp,
            step_started_at_mono=self._step_started_at_mono,
            task_started_at_mono=self._task_started_at_mono,
        )

        try:
            pre_result = self._shield.pre_check(ctx)
        except ValueError as exc:
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=safety_error(
                    "SAFETY_BYPASS_REJECTED",
                    str(exc),
                ),
                action_result=None,
                duration_ms=0,
            )

        if pre_result.decision == SafetyDecision.ALLOW:
            return self._execute_with_robot(
                contract=contract,
                step=step,
                attempt=attempt,
                parameters=step.parameters,
            )

        if pre_result.decision == SafetyDecision.ALLOW_WITH_LIMITS:
            limited = pre_result.limited_parameters or step.parameters
            return self._execute_with_robot(
                contract=contract,
                step=step,
                attempt=attempt,
                parameters=limited,
            )

        if pre_result.decision == SafetyDecision.REQUEST_CORRECTION:
            error_code = SAFETY_DECISION_ERROR_CODES.get(
                pre_result.decision.value, "SAFETY_REQUEST_CORRECTION"
            )
            limiting = pre_result.limiting_rule
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=safety_error(
                    error_code,
                    limiting.message if limiting else "safety request correction",
                    details={
                        "rule_id": limiting.rule_id if limiting else "UNKNOWN",
                        "reason_code": limiting.reason_code if limiting else "UNKNOWN",
                    },
                ),
                action_result=None,
                duration_ms=0,
            )

        if pre_result.decision == SafetyDecision.PAUSE:
            error_code = "SAFETY_PAUSE_REQUESTED"
            limiting = pre_result.limiting_rule
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=safety_error(
                    error_code,
                    limiting.message if limiting else "safety pause requested",
                    details={
                        "rule_id": limiting.rule_id if limiting else "UNKNOWN",
                        "reason_code": limiting.reason_code if limiting else "UNKNOWN",
                        "safety_decision": "PAUSE",
                    },
                ),
                action_result=None,
                duration_ms=0,
            )

        if pre_result.decision == SafetyDecision.REJECT:
            error_code = "SAFETY_ACTION_REJECTED"
            limiting = pre_result.limiting_rule
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=safety_error(
                    error_code,
                    limiting.message if limiting else "safety action rejected",
                    details={
                        "rule_id": limiting.rule_id if limiting else "UNKNOWN",
                        "reason_code": limiting.reason_code if limiting else "UNKNOWN",
                        "safety_decision": "REJECT",
                    },
                ),
                action_result=None,
                duration_ms=0,
            )

        if pre_result.decision == SafetyDecision.EMERGENCY_STOP:
            error_code = "SAFETY_EMERGENCY_STOP"
            limiting = pre_result.limiting_rule
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=safety_error(
                    error_code,
                    limiting.message if limiting else "safety emergency stop",
                    details={
                        "rule_id": limiting.rule_id if limiting else "UNKNOWN",
                        "reason_code": limiting.reason_code if limiting else "UNKNOWN",
                        "safety_decision": "EMERGENCY_STOP",
                    },
                ),
                action_result=None,
                duration_ms=0,
            )

        error_code = "SAFETY_UNKNOWN_DECISION"
        return self._result(
            contract=contract,
            step=step,
            attempt=attempt,
            success=False,
            error=safety_error(
                error_code,
                f"unknown safety decision: {pre_result.decision}",
            ),
            action_result=None,
            duration_ms=0,
        )

    def _execute_with_robot(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        attempt: int,
        parameters: dict[str, Any],
    ) -> StepExecutionResult:
        step_with_params = step.model_copy(update={"parameters": parameters})

        result = self._skill_executor.execute_attempt(
            contract=contract,
            step=step_with_params,
            attempt=attempt,
        )

        if result.success:
            robot_state = self._robot.get_state()
            if isinstance(robot_state, RobotState):
                post_ctx = self._context_builder.build(
                    contract=contract,
                    step=step,
                    robot_state=robot_state,
                    scene_version=self._scene_version,
                    scene_updated_at=self._scene_updated_at,
                    telemetry_timestamp=self._telemetry_timestamp,
                    step_started_at_mono=self._step_started_at_mono,
                    task_started_at_mono=self._task_started_at_mono,
                )
                post_result = self._shield.post_check(post_ctx)
                if post_result.decision not in {
                    SafetyDecision.ALLOW,
                    SafetyDecision.ALLOW_WITH_LIMITS,
                }:
                    limiting = post_result.limiting_rule
                    post_error_code = SAFETY_DECISION_ERROR_CODES.get(
                        post_result.decision.value, "SAFETY_POST_CHECK_FAILED"
                    )
                    return StepExecutionResult(
                        task_id=contract.task_id,
                        step_id=step.step_id,
                        skill=step.skill.value,
                        attempt=attempt,
                        success=False,
                        error=safety_error(
                            post_error_code,
                            limiting.message if limiting else "post-check failed",
                            details={
                                "rule_id": limiting.rule_id if limiting else "UNKNOWN",
                                "reason_code": limiting.reason_code if limiting else "UNKNOWN",
                            },
                        ),
                        action_result=result.action_result,
                        duration_ms=result.duration_ms,
                        timestamp=datetime.now(UTC),
                    )

        return result

    def _result(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        attempt: int,
        success: bool,
        error: StructuredError | None,
        action_result: Any,
        duration_ms: int,
    ) -> StepExecutionResult:
        return StepExecutionResult(
            task_id=contract.task_id,
            step_id=step.step_id,
            skill=step.skill.value,
            attempt=attempt,
            success=success,
            error=error,
            action_result=action_result,
            duration_ms=duration_ms,
            timestamp=datetime.now(UTC),
        )
