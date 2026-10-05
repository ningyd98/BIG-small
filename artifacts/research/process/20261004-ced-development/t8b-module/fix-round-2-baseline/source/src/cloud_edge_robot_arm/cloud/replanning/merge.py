"""重规划合并逻辑，决定保留、替换或追加任务步骤。

Merge and assemble locally replanned TaskContracts.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.contracts.models import (
    ExecutionCheckpoint,
    LocalReplanningRequest,
    LocalReplanningResponse,
    ReplanScope,
    TaskContract,
    TaskStep,
)

_NON_REPEATABLE_SKILLS = {"GRASP", "PLACE", "RELEASE"}
_LOW_LEVEL_PARAMETER_KEYS = {
    "joint_angles",
    "joint_positions",
    "trajectory",
    "trajectory_points",
    "pwm",
    "servo_pulse",
    "motor_current",
    "disable_safety",
    "bypass_safety",
    "ignore_collision",
    "force_execute",
}


class ReplanMergeValidator:
    """Validates candidate replacement steps before contract assembly."""

    def validate_candidate(
        self,
        *,
        request: LocalReplanningRequest,
        response: LocalReplanningResponse,
        active_contract: TaskContract,
        checkpoint: ExecutionCheckpoint,
    ) -> tuple[bool, list[str]]:
        errors: list[str] = []
        step_ids = [step.step_id for step in active_contract.steps]
        completed = list(checkpoint.completed_step_ids)
        completed_set = set(completed)
        if request.completed_step_ids != completed:
            errors.append("completed_step_ids do not match checkpoint")
        if request.failed_step_id and request.failed_step_id not in step_ids:
            errors.append("failed_step_id is not in active contract")
        if response.outcome == "REPLANNED" and not response.new_steps:
            errors.append("REPLANNED response must include executable new_steps")
        if response.new_plan_version != request.current_plan_version + 1:
            errors.append("new_plan_version must be current_plan_version + 1")
        if response.new_command_seq <= request.current_command_seq:
            errors.append("new_command_seq must increase")
        if response.created_at >= active_contract.valid_until:
            errors.append("replan result arrived after active contract expiry")
        replacement_ids = [step.step_id for step in response.new_steps]
        for step_id in replacement_ids:
            if step_id in completed_set:
                errors.append(f"completed step {step_id} cannot appear in replacement steps")
        for step in response.new_steps:
            low_level = _LOW_LEVEL_PARAMETER_KEYS.intersection(step.parameters)
            if low_level:
                errors.append(f"step {step.step_id} contains low-level fields: {sorted(low_level)}")
        original_by_id = {step.step_id: step for step in active_contract.steps}
        for step_id in completed:
            if step_id not in original_by_id:
                errors.append(f"completed step {step_id} is not in active contract")
        candidate = self.merge_steps(
            scope=request.requested_replan_scope,
            active_steps=active_contract.steps,
            replacement_steps=response.new_steps,
            failed_step_id=request.failed_step_id or checkpoint.failed_step_id,
            completed_step_ids=completed,
        )
        candidate_ids = [step.step_id for step in candidate]
        if len(candidate_ids) != len(set(candidate_ids)):
            errors.append("merged contract contains duplicate step_id values")
        for step_id in completed:
            if step_id not in candidate_ids:
                errors.append(f"completed step {step_id} missing after merge")
        for step_id in completed:
            original = original_by_id[step_id]
            merged = next((step for step in candidate if step.step_id == step_id), None)
            if merged is None:
                continue
            if merged.model_dump(mode="json") != original.model_dump(mode="json"):
                errors.append(f"completed step {step_id} was modified")
        original_completed_order = [
            step.step_id for step in active_contract.steps if step.step_id in completed_set
        ]
        merged_completed_order = [
            step.step_id for step in candidate if step.step_id in completed_set
        ]
        if merged_completed_order != original_completed_order:
            errors.append("completed step order changed")
        completed_non_repeatable = {
            original_by_id[step_id].skill.value
            for step_id in completed
            if original_by_id[step_id].skill.value in _NON_REPEATABLE_SKILLS
        }
        for skill in completed_non_repeatable:
            repeats = [step.step_id for step in candidate if step.skill.value == skill]
            if len(repeats) > 1:
                errors.append(f"non-repeatable completed skill {skill} appears again: {repeats}")
        return not errors, errors

    def merge_steps(
        self,
        *,
        scope: str,
        active_steps: list[TaskStep],
        replacement_steps: list[TaskStep],
        failed_step_id: str,
        completed_step_ids: list[str],
    ) -> list[TaskStep]:
        completed = set(completed_step_ids)
        if not failed_step_id:
            failed_index = len(completed_step_ids)
        else:
            failed_index = next(
                (idx for idx, step in enumerate(active_steps) if step.step_id == failed_step_id),
                len(completed_step_ids),
            )
        scope_value = scope.value if hasattr(scope, "value") else str(scope)
        if scope_value == ReplanScope.CURRENT_STEP.value:
            merged = list(active_steps)
            if replacement_steps:
                merged[failed_index] = replacement_steps[0]
            return [step for step in merged if step.step_id in completed] + [
                step for step in merged if step.step_id not in completed
            ]
        if scope_value == ReplanScope.REMAINING_STEPS.value:
            prefix = [step for step in active_steps if step.step_id in completed]
            return prefix + list(replacement_steps)
        if scope_value in {
            ReplanScope.FAILED_STEP_AND_REMAINING.value,
            ReplanScope.FULL_PLAN_REQUIRED.value,
        }:
            prefix = [step for step in active_steps[:failed_index] if step.step_id in completed]
            return prefix + list(replacement_steps)
        return list(active_steps)


class ReplanContractAssembler:
    """Builds a new trusted TaskContract from a validated partial replan."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 300,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock if clock is not None else lambda: datetime.now(UTC)

    def assemble(
        self,
        *,
        active_contract: TaskContract,
        request: LocalReplanningRequest,
        response: LocalReplanningResponse,
        checkpoint: ExecutionCheckpoint,
    ) -> TaskContract:
        merged_steps = ReplanMergeValidator().merge_steps(
            scope=request.requested_replan_scope,
            active_steps=active_contract.steps,
            replacement_steps=response.new_steps,
            failed_step_id=request.failed_step_id or checkpoint.failed_step_id,
            completed_step_ids=checkpoint.completed_step_ids,
        )
        now = self._clock()
        valid_until = max(active_contract.valid_until, now + timedelta(seconds=self._ttl_seconds))
        pending = [
            step for step in merged_steps if step.step_id not in set(checkpoint.completed_step_ids)
        ]
        current_step_id = pending[0].step_id if pending else None
        return active_contract.model_copy(
            update={
                "plan_version": response.new_plan_version,
                "command_seq": response.new_command_seq,
                "timestamp": now,
                "issued_at": now,
                "valid_until": valid_until,
                "scene_version": max(active_contract.scene_version, request.current_scene_version),
                "expected_scene_version": max(
                    active_contract.expected_scene_version,
                    request.current_scene_version,
                    checkpoint.scene_version,
                ),
                "current_step_id": current_step_id,
                "steps": merged_steps,
                "previous_command_seq": active_contract.command_seq,
            },
            deep=True,
        )
