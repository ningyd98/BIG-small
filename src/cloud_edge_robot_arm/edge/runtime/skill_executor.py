from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError

from cloud_edge_robot_arm.contracts import ActionResult, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.runtime.condition_evaluator import ConditionEvaluator
from cloud_edge_robot_arm.edge.runtime.errors import (
    INVALID_SKILL_PARAMETERS,
    runtime_error,
)
from cloud_edge_robot_arm.edge.runtime.skill_registry import (
    RuntimeSkillRobot,
    SkillRegistry,
)
from cloud_edge_robot_arm.errors import StructuredError


@dataclass(frozen=True)
class StepExecutionResult:
    task_id: str
    step_id: str
    skill: str
    attempt: int
    success: bool
    error: StructuredError | None
    action_result: ActionResult | None
    duration_ms: int
    timestamp: datetime

    @property
    def error_code(self) -> str | None:
        return None if self.error is None else self.error.code


class SkillExecutor:
    def __init__(
        self,
        *,
        robot: RuntimeSkillRobot,
        registry: SkillRegistry,
        condition_evaluator: ConditionEvaluator | None = None,
    ) -> None:
        self._robot = robot
        self._registry = registry
        self._conditions = condition_evaluator or ConditionEvaluator()

    def execute_attempt(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        attempt: int,
    ) -> StepExecutionResult:
        definition = self._registry.definition_for(step.skill)
        if definition is None:
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=runtime_error(
                    "UNREGISTERED_SKILL",
                    f"skill {step.skill.value} is not registered",
                    details={"skill": step.skill.value},
                ),
                action_result=None,
                duration_ms=0,
            )

        try:
            parameters = definition.validate(step.parameters)
        except ValidationError as exc:
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=runtime_error(
                    INVALID_SKILL_PARAMETERS,
                    "skill parameters failed validation",
                    details={"step_id": step.step_id, "errors": exc.errors(include_url=False)},
                ),
                action_result=None,
                duration_ms=0,
            )

        preconditions = self._conditions.evaluate_preconditions(
            robot=self._robot,
            contract=contract,
            conditions=step.preconditions,
        )
        if not preconditions.success:
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=preconditions.error,
                action_result=None,
                duration_ms=0,
            )

        action_result = definition.handler(self._robot, parameters, step.timeout_ms)
        if not action_result.success:
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=action_result.error,
                action_result=action_result,
                duration_ms=action_result.duration_ms,
            )

        success_conditions = self._conditions.evaluate_success_conditions(
            robot=self._robot,
            contract=contract,
            conditions=step.success_conditions,
        )
        if not success_conditions.success:
            return self._result(
                contract=contract,
                step=step,
                attempt=attempt,
                success=False,
                error=success_conditions.error,
                action_result=action_result,
                duration_ms=action_result.duration_ms,
            )

        return self._result(
            contract=contract,
            step=step,
            attempt=attempt,
            success=True,
            error=None,
            action_result=action_result,
            duration_ms=action_result.duration_ms,
        )

    def _result(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        attempt: int,
        success: bool,
        error: StructuredError | None,
        action_result: ActionResult | None,
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
