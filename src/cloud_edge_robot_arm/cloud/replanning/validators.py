"""Validators for local replanning.

- CompletedStepsProtectionValidator: ensures completed steps are immutable
- ReplanScopeValidator: validates scope appropriateness
"""

from __future__ import annotations

from cloud_edge_robot_arm.contracts.models import ReplanScope, TaskStep


class CompletedStepsProtectionValidator:
    """Enforces the immutability of completed steps during replanning.

    Rules:
    1. All completed steps must be present in the new plan
    2. Completed step parameters must not be modified
    3. Completed step order must not change
    4. No steps may be inserted before completed steps
    5. The last successful step must not be deleted
    6. Completed GRASP/PLACE/RELEASE must not be repeated
    """

    @staticmethod
    def validate(
        completed_ids: list[str],
        original_steps: list[TaskStep],
        new_steps: list[TaskStep],
        last_successful_step_id: str = "",
    ) -> tuple[bool, list[str]]:
        """Validate that completed steps are preserved and immutable.

        Returns (is_valid, error_messages).
        """
        errors: list[str] = []
        orig_map = {s.step_id: s for s in original_steps}
        new_map = {s.step_id: s for s in new_steps}

        # Rule 1: All completed steps must be present
        for step_id in completed_ids:
            if step_id not in new_map:
                errors.append(
                    f"REPLAN_COMPLETED_STEP_MODIFIED: completed step "
                    f"'{step_id}' missing from new plan"
                )

        # Rule 2: Completed step parameters must not change
        for step_id in completed_ids:
            if step_id in orig_map and step_id in new_map:
                orig = orig_map[step_id]
                new = new_map[step_id]
                if orig.skill != new.skill:
                    errors.append(
                        f"REPLAN_COMPLETED_STEP_MODIFIED: step '{step_id}' skill changed "
                        f"from {orig.skill} to {new.skill}"
                    )
                if orig.parameters != new.parameters:
                    errors.append(
                        f"REPLAN_COMPLETED_STEP_MODIFIED: step '{step_id}' parameters changed"
                    )

        # Rule 3: Completed step order must not change
        orig_completed_order = [s for s in original_steps if s.step_id in completed_ids]
        new_completed_order = [s for s in new_steps if s.step_id in completed_ids]
        if [s.step_id for s in new_completed_order] != [s.step_id for s in orig_completed_order]:
            errors.append("REPLAN_COMPLETED_STEP_MODIFIED: completed step order changed")

        # Rule 5: Last successful step must not be deleted
        if last_successful_step_id and last_successful_step_id not in new_map:
            errors.append(
                f"REPLAN_COMPLETED_STEP_MODIFIED: last successful step "
                f"'{last_successful_step_id}' deleted"
            )

        # Rule 6: Completed GRASP/PLACE/RELEASE must not be repeated
        non_repeatable = {"GRASP", "PLACE", "RELEASE"}
        non_repeatable_completed = [
            sid
            for sid in completed_ids
            if sid in orig_map and orig_map[sid].skill.value in non_repeatable
        ]
        _new_non_repeatable = [
            s
            for s in new_steps
            if s.skill.value in non_repeatable and s.step_id not in completed_ids
        ]
        # Each non-repeatable completed step must appear at most once in total
        for sid in non_repeatable_completed:
            skill_val = orig_map[sid].skill.value
            repeat_count = sum(1 for s in new_steps if s.skill.value == skill_val)
            if repeat_count > 1:
                errors.append(
                    f"REPLAN_COMPLETED_STEP_MODIFIED: non-repeatable skill "
                    f"'{skill_val}' appears {repeat_count} times in new plan"
                )

        return len(errors) == 0, errors


class ReplanScopeValidator:
    """Validates that the requested replan scope is appropriate.

    Rules:
    - CURRENT_STEP: can only adjust current step parameters
    - FAILED_STEP_AND_REMAINING: can replace failed + subsequent
    - REMAINING_STEPS: failed step already handled, update remaining
    - MORE_OBSERVATION_REQUIRED: must not generate executable plan
    - FULL_PLAN_REQUIRED: must document why local repair insufficient
    - NO_REPLAN_SAFETY_STOP: must not resume execution
    """

    @staticmethod
    def validate(
        scope: str,
        reason: str,
        new_steps: list[TaskStep],
    ) -> tuple[bool, str]:
        """Validate scope constraints.

        Returns (is_valid, error_or_ok).
        """
        if scope == ReplanScope.MORE_OBSERVATION_REQUIRED:
            if new_steps:
                return False, "MORE_OBSERVATION_REQUIRED must not generate executable steps"

        if scope == ReplanScope.NO_REPLAN_SAFETY_STOP:
            if new_steps:
                return False, "NO_REPLAN_SAFETY_STOP must not generate executable steps"

        if scope == ReplanScope.CURRENT_STEP and len(new_steps) > 1:
            return False, "CURRENT_STEP scope should only produce 1 replacement step"

        if scope == ReplanScope.FULL_PLAN_REQUIRED and not reason:
            return False, "FULL_PLAN_REQUIRED must document why local repair is insufficient"

        return True, "OK"
