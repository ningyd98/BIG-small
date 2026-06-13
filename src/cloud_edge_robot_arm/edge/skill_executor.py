from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from cloud_edge_robot_arm.contracts import SkillExecutionResult, TaskStep
from cloud_edge_robot_arm.edge.skill_registry import SkillRegistry, SkillRobot
from cloud_edge_robot_arm.errors import StructuredError


class SkillExecutor:
    def __init__(self, *, robot: SkillRobot, registry: SkillRegistry) -> None:
        self._robot = robot
        self._registry = registry

    def execute_step(
        self,
        step: TaskStep,
        *,
        task_id: str,
        plan_version: int,
        command_seq: int,
        scene_version: int,
    ) -> SkillExecutionResult:
        started = perf_counter()
        handler = self._registry.handler_for(step.skill)
        if handler is None:
            return self._result(
                step=step,
                task_id=task_id,
                plan_version=plan_version,
                command_seq=command_seq,
                scene_version=scene_version,
                success=False,
                error=StructuredError(
                    code="UNREGISTERED_SKILL",
                    message=f"skill {step.skill.value} is not registered",
                    category="SKILL_EXECUTION",
                ),
                details={},
                started=started,
            )

        try:
            action_result = handler(self._robot, step.parameters)
        except (KeyError, TypeError, ValueError) as exc:
            return self._result(
                step=step,
                task_id=task_id,
                plan_version=plan_version,
                command_seq=command_seq,
                scene_version=scene_version,
                success=False,
                error=StructuredError(
                    code="INVALID_SKILL_PARAMETERS",
                    message=str(exc),
                    category="SKILL_EXECUTION",
                    details={"step_id": step.step_id, "skill": step.skill.value},
                ),
                details={},
                started=started,
            )

        return self._result(
            step=step,
            task_id=task_id,
            plan_version=plan_version,
            command_seq=command_seq,
            scene_version=scene_version,
            success=action_result.success,
            error=action_result.error,
            details=action_result.details,
            started=started,
        )

    def _result(
        self,
        *,
        step: TaskStep,
        task_id: str,
        plan_version: int,
        command_seq: int,
        scene_version: int,
        success: bool,
        error: StructuredError | None,
        details: dict[str, object],
        started: float,
    ) -> SkillExecutionResult:
        duration_ms = int((perf_counter() - started) * 1_000)
        return SkillExecutionResult(
            task_id=task_id,
            plan_version=plan_version,
            command_seq=command_seq,
            timestamp=datetime.now(UTC),
            step_id=step.step_id,
            skill=step.skill,
            scene_version=scene_version,
            success=success,
            error=error,
            details=details,
            duration_ms=duration_ms,
        )
