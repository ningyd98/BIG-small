"""Replanner adapters — Mock, RuleBased, and OpenAICompatible.

Extends the PlannerAdapter pattern from cloud/planning/adapter.py.
ReplannerAdapter operates on LocalReplanningRequest → LocalReplanningResponse.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from cloud_edge_robot_arm.contracts.models import (
    LocalReplanningRequest,
    LocalReplanningResponse,
    SkillName,
    TaskStep,
)


@runtime_checkable
class ReplannerAdapter(Protocol):
    """Protocol for cloud-side local replanning adapters.

    Follows the same pattern as PlannerAdapter.
    Receives a LocalReplanningRequest and returns a LocalReplanningResponse.
    Must never output joint angles, PWM, servo pulse, or trajectory points.
    """

    def replan(self, request: LocalReplanningRequest) -> LocalReplanningResponse:
        """Generate a local replan from the given request."""
        ...

    @property
    def planner_name(self) -> str:
        """Human-readable adapter name."""
        ...


class MockReplannerAdapter:
    """Deterministic mock replanner for testing.

    Returns a canned response with replacement steps for the failed step.
    """

    def __init__(self, canned_response: LocalReplanningResponse | None = None) -> None:
        self._canned = canned_response

    @property
    def planner_name(self) -> str:
        return "mock_replanner"

    def replan(self, request: LocalReplanningRequest) -> LocalReplanningResponse:
        if self._canned is not None:
            return self._canned

        now = datetime.now(UTC)
        new_steps = [
            TaskStep(
                step_id=f"replan-step-{i}",
                skill=SkillName.GRASP if i == 0 else SkillName.PLACE,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
                preconditions=[],
                success_conditions=[],
            )
            for i in range(3)
        ]
        return LocalReplanningResponse(
            request_id=request.request_id,
            outcome="REPLANNED",
            reason="Mock replan generated",
            new_steps=new_steps,
            new_plan_version=request.current_plan_version + 1,
            new_command_seq=request.current_command_seq + 1,
            planner_name="mock_replanner",
            prompt_version="1.0",
            created_at=now,
        )


class RuleBasedReplannerAdapter:
    """Deterministic rule-based replanner — no LLM.

    Generates replacement steps based on the failure type and remaining steps.
    Supports CURRENT_STEP, FAILED_STEP_AND_REMAINING, REMAINING_STEPS scopes.
    """

    @property
    def planner_name(self) -> str:
        return "rule_based_replanner"

    def replan(self, request: LocalReplanningRequest) -> LocalReplanningResponse:
        now = datetime.now(UTC)
        scope = request.requested_replan_scope

        # MORE_OBSERVATION_REQUIRED — no plan generated
        if scope == "MORE_OBSERVATION_REQUIRED":
            return LocalReplanningResponse(
                request_id=request.request_id,
                outcome="REQUEST_MORE_OBSERVATION",
                reason="Insufficient scene data for replanning",
                new_steps=[],
                new_plan_version=request.current_plan_version,
                new_command_seq=request.current_command_seq,
                planner_name=self.planner_name,
                prompt_version="1.0",
                created_at=now,
            )

        # NO_REPLAN_SAFETY_STOP — no plan generated
        if scope == "NO_REPLAN_SAFETY_STOP":
            return LocalReplanningResponse(
                request_id=request.request_id,
                outcome="REJECTED",
                reason="Safety stop required — no replan possible",
                new_steps=[],
                new_plan_version=request.current_plan_version,
                new_command_seq=request.current_command_seq,
                planner_name=self.planner_name,
                prompt_version="1.0",
                created_at=now,
            )

        # Generate replacement steps
        failed_skill = SkillName.GRASP  # Default, inferred from context
        new_steps = self._generate_replacement_steps(scope, failed_skill)

        return LocalReplanningResponse(
            request_id=request.request_id,
            outcome="REPLANNED",
            reason=f"Rule-based replan for scope={scope}",
            new_steps=new_steps,
            new_plan_version=request.current_plan_version + 1,
            new_command_seq=request.current_command_seq + 1,
            planner_name=self.planner_name,
            prompt_version="1.0",
            created_at=now,
        )

    @staticmethod
    def _generate_replacement_steps(scope: str, failed_skill: SkillName) -> list[TaskStep]:
        steps: list[TaskStep] = []
        if scope == "CURRENT_STEP":
            # Replace only the failed step with adjusted parameters
            steps.append(
                TaskStep(
                    step_id="replan-current-step",
                    skill=failed_skill,
                    parameters={"adjusted": True},
                    expected_duration_ms=3000,
                    timeout_ms=8000,
                    retry_limit=3,
                    preconditions=["target_visible"],
                    success_conditions=["grasp_confirmed"],
                )
            )
        elif scope in ("FAILED_STEP_AND_REMAINING", "REMAINING_STEPS", "FULL_PLAN_REQUIRED"):
            steps.extend(
                [
                    TaskStep(
                        step_id="replan-approach",
                        skill=SkillName.APPROACH,
                        parameters={"speed": "reduced"},
                        expected_duration_ms=2000,
                        timeout_ms=5000,
                        retry_limit=3,
                        preconditions=["target_visible"],
                        success_conditions=["above_target"],
                    ),
                    TaskStep(
                        step_id="replan-grasp",
                        skill=SkillName.GRASP,
                        parameters={},
                        expected_duration_ms=2000,
                        timeout_ms=5000,
                        retry_limit=3,
                        preconditions=["above_target"],
                        success_conditions=["grasp_confirmed"],
                    ),
                    TaskStep(
                        step_id="replan-lift",
                        skill=SkillName.LIFT,
                        parameters={},
                        expected_duration_ms=1500,
                        timeout_ms=4000,
                        retry_limit=3,
                        preconditions=["grasp_confirmed"],
                        success_conditions=["lifted"],
                    ),
                    TaskStep(
                        step_id="replan-place",
                        skill=SkillName.PLACE,
                        parameters={},
                        expected_duration_ms=2000,
                        timeout_ms=5000,
                        retry_limit=3,
                        preconditions=["lifted"],
                        success_conditions=["placed"],
                    ),
                    TaskStep(
                        step_id="replan-verify",
                        skill=SkillName.VERIFY_RESULT,
                        parameters={},
                        expected_duration_ms=1000,
                        timeout_ms=3000,
                        retry_limit=3,
                        preconditions=["placed"],
                        success_conditions=["verified"],
                    ),
                ]
            )
        return steps
