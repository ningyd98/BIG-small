"""Deterministic FailureSummary builder — no LLM, no guesswork.

Same input → same output (stable hash).
Separates confirmed_facts from diagnostic_findings from suspected_causes.
Marks missing information as "unknown".
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    FailureSummary,
    TaskContract,
)
from cloud_edge_robot_arm.edge.events.models import DetectionContext

# Mapping from event type → failure_type string
_EVENT_TO_FAILURE_TYPE: dict[EdgeEventType, str] = {
    EdgeEventType.GRASP_FAILED: "grasp_failure",
    EdgeEventType.PLACE_FAILED: "place_failure",
    EdgeEventType.VERIFY_FAILED: "verify_failure",
    EdgeEventType.SKILL_EXECUTION_FAILED: "skill_execution_failure",
    EdgeEventType.STEP_TIMEOUT: "step_timeout",
    EdgeEventType.TASK_TIMEOUT: "task_timeout",
    EdgeEventType.TARGET_MOVED: "target_moved",
    EdgeEventType.TARGET_LOST: "target_lost",
    EdgeEventType.PATH_BLOCKED: "path_blocked",
    EdgeEventType.SCENE_CHANGED: "scene_changed",
    EdgeEventType.SAFETY_REJECTED: "safety_rejected",
    EdgeEventType.SAFETY_PAUSED: "safety_paused",
    EdgeEventType.EMERGENCY_STOP_TRIGGERED: "emergency_stop",
    EdgeEventType.DEVICE_FAULT: "device_fault",
    EdgeEventType.PLAN_INVALIDATED: "plan_invalidated",
}

# Mapping from event type → recommended replan scope
_EVENT_TO_REPLAN_SCOPE: dict[EdgeEventType, str] = {
    EdgeEventType.GRASP_FAILED: "CURRENT_STEP",
    EdgeEventType.PLACE_FAILED: "CURRENT_STEP",
    EdgeEventType.VERIFY_FAILED: "CURRENT_STEP",
    EdgeEventType.SKILL_EXECUTION_FAILED: "CURRENT_STEP",
    EdgeEventType.STEP_TIMEOUT: "CURRENT_STEP",
    EdgeEventType.TARGET_MOVED: "FAILED_STEP_AND_REMAINING",
    EdgeEventType.TARGET_LOST: "MORE_OBSERVATION_REQUIRED",
    EdgeEventType.PATH_BLOCKED: "FAILED_STEP_AND_REMAINING",
    EdgeEventType.SCENE_CHANGED: "REMAINING_STEPS",
    EdgeEventType.SAFETY_REJECTED: "FAILED_STEP_AND_REMAINING",
    EdgeEventType.EMERGENCY_STOP_TRIGGERED: "NO_REPLAN_SAFETY_STOP",
    EdgeEventType.DEVICE_FAULT: "NO_REPLAN_SAFETY_STOP",
    EdgeEventType.PLAN_INVALIDATED: "FULL_PLAN_REQUIRED",
    EdgeEventType.TASK_TIMEOUT: "FAILED_STEP_AND_REMAINING",
}

# Mapping from event type → recovery hints
_EVENT_TO_HINT: dict[EdgeEventType, str] = {
    EdgeEventType.GRASP_FAILED: "adjust_grasp_pose_or_verify_gripper_state_and_retry",
    EdgeEventType.PLACE_FAILED: "verify_placement_region_and_adjust_release_height",
    EdgeEventType.VERIFY_FAILED: "re_observe_verification_condition_and_retry",
    EdgeEventType.STEP_TIMEOUT: "reduce_step_complexity_or_increase_timeout_parameter",
    EdgeEventType.TARGET_MOVED: "replan_current_step_with_updated_target_pose",
    EdgeEventType.TARGET_LOST: "request_additional_scene_observation_and_relocate",
    EdgeEventType.PATH_BLOCKED: "compute_alternative_path_around_new_obstacle",
    EdgeEventType.SAFETY_REJECTED: "review_safety_constraints_and_adjust_step_parameters",
    EdgeEventType.PLAN_INVALIDATED: "request_full_replan_due_to_plan_invalidation",
}


class FailureSummaryBuilder:
    """Deterministic builder for FailureSummary.

    Constraints:
    - No LLM calls
    - No guessing facts not present in inputs
    - Missing inputs → explicitly marked "unknown"
    - Same inputs → same output (stable hash)
    - confirmed_facts only records programmatically verified facts
    - suspected_causes must not be presented as facts
    """

    def __init__(self, *, generator_version: str = "1.0") -> None:
        self._generator_version = generator_version

    def build(
        self,
        *,
        event: EdgeEvent,
        contract: TaskContract,
        completed_step_ids: list[str] | None = None,
        retry_count: int = 0,
        retry_limit: int = 0,
        retry_history: list[dict[str, object]] | None = None,
        last_successful_step_id: str = "",
        context: DetectionContext | None = None,
    ) -> FailureSummary:
        """Build a FailureSummary from an event and execution context.

        All optional parameters default to safe values.
        """
        now = datetime.now(UTC)
        summary_id = f"fs-{now.strftime('%Y%m%d%H%M%S%f')}"

        # Compute fields from event type
        failure_type = _EVENT_TO_FAILURE_TYPE.get(event.event_type, "unknown_failure")
        replan_scope = _EVENT_TO_REPLAN_SCOPE.get(event.event_type, "FAILED_STEP_AND_REMAINING")
        hint = _EVENT_TO_HINT.get(event.event_type, "report_to_cloud_for_analysis")

        # Build confirmed_facts from what we actually know
        confirmed: dict[str, object] = {
            "event_type": event.event_type.value,
            "event_severity": str(event.severity),
            "step_id": event.step_id if event.step_id else "unknown",
            "retry_count": retry_count,
            "retry_limit": retry_limit,
        }

        if event.details:
            for key, val in event.details.items():
                confirmed[f"event_detail_{key}"] = val

        # Build diagnostic findings from deterministic rules
        diagnostics: dict[str, object] = {
            "failure_type": failure_type,
            "replan_scope_recommendation": replan_scope,
        }

        # Build suspected causes — only what's reasonable, no guesses
        suspected: list[str] = []
        if event.event_type == EdgeEventType.GRASP_FAILED:
            suspected.append("possible_grasp_offset")
            suspected.append("possible_object_slippage")
        elif event.event_type == EdgeEventType.TARGET_MOVED:
            suspected.append("external_object_displacement")
        elif event.event_type == EdgeEventType.TARGET_LOST:
            suspected.append("possible_occlusion")
            suspected.append("possible_object_removed_from_scene")

        # Build failure summary
        summary = FailureSummary(
            task_id=event.task_id,
            plan_version=event.plan_version,
            command_seq=event.command_seq,
            timestamp=now,
            failure_event_id=event.event_id,
            failed_step_id=event.step_id or "unknown",
            completed_step_ids=completed_step_ids or [],
            reason=hint,
            local_retry_count=retry_count,
            current_scene_version=event.scene_version,
            recovery_hint=hint,
            summary_id=summary_id,
            robot_id=event.robot_id,
            plan_id=event.plan_id,
            failed_skill=contract.steps[0].skill if contract.steps else None,
            last_successful_step_id=last_successful_step_id,
            pending_step_ids=self._compute_pending(
                contract, completed_step_ids or [], event.step_id
            ),
            failure_type=failure_type,
            severity=str(event.severity),
            confirmed_facts=confirmed,
            diagnostic_findings=diagnostics,
            suspected_causes=suspected,
            retry_history=retry_history or [],
            retry_limit=retry_limit,
            execution_timeline=[],
            robot_state={},
            target_state={},
            obstacle_state={},
            telemetry={},
            safety_decision="",
            scene_confidence=context.scene_confidence if context else 0.0,
            network_state={},
            requested_replan_scope=replan_scope,
            safe_resume_state={},
            generated_at=now,
            generator_version=self._generator_version,
            summary_hash="",  # Computed below
            correlation_id=event.correlation_id,
        )

        # Compute stable hash
        summary.summary_hash = self._compute_hash(summary)
        return summary

    @staticmethod
    def _compute_pending(
        contract: TaskContract,
        completed: list[str],
        failed_step_id: str | None,
    ) -> list[str]:
        all_steps = [s.step_id for s in contract.steps]
        done = set(completed)
        if failed_step_id:
            done.add(failed_step_id)
        return [s for s in all_steps if s not in done]

    @staticmethod
    def _compute_hash(summary: FailureSummary) -> str:
        """Compute a stable hash of the summary for idempotency."""
        # Use fields that are deterministic for the same inputs
        fields = {
            "task_id": summary.task_id,
            "plan_version": summary.plan_version,
            "command_seq": summary.command_seq,
            "failure_event_id": summary.failure_event_id,
            "failed_step_id": summary.failed_step_id,
            "completed_step_ids": sorted(summary.completed_step_ids),
            "failure_type": summary.failure_type,
            "severity": summary.severity,
            "local_retry_count": summary.local_retry_count,
            "generator_version": summary.generator_version,
        }
        canonical = json.dumps(fields, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
