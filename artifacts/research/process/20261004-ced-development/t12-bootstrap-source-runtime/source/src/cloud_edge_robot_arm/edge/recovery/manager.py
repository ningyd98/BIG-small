"""Local recovery manager for event-triggered edge autonomy.

Deterministic recovery decisions — no LLM calls.
Every recovery action must re-pass SafetyShield.
本地恢复决策管理器。

恢复决策是确定性的，不调用 LLM；每个恢复动作都必须重新通过 SafetyShield。

"""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    LocalRecoveryDecision,
    RecoveryAction,
    TaskContract,
)
from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetService
from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
    InMemoryEventAutonomyRepository,
)


def _default_repo() -> InMemoryEventAutonomyRepository:
    return InMemoryEventAutonomyRepository()


# Events that are eligible for local recovery
_LOCALLY_RECOVERABLE: set[EdgeEventType] = {
    EdgeEventType.GRASP_FAILED,
    EdgeEventType.PLACE_FAILED,
    EdgeEventType.VERIFY_FAILED,
    EdgeEventType.SKILL_EXECUTION_FAILED,
    EdgeEventType.STEP_TIMEOUT,
    EdgeEventType.SCENE_CONFIDENCE_LOW,
}

# Events requiring immediate safety stop — never locally recoverable
_IMMEDIATE_STOP_EVENTS: set[EdgeEventType] = {
    EdgeEventType.EMERGENCY_STOP_TRIGGERED,
    EdgeEventType.DEVICE_FAULT,
}


class LocalRecoveryManager:
    """Deterministic local recovery decision engine.

    Responsibilities:
    - Evaluate if an event is eligible for local recovery
    - Check retry budget
    - Select recovery action deterministically
    - Record recovery results
    - Never calls LLM or external service
    """

    def __init__(
        self,
        *,
        budget_manager: RetryBudgetService | None = None,
    ) -> None:
        self._budget_manager = budget_manager or RetryBudgetService(
            repository=_default_repo(),
        )

    def evaluate(
        self,
        event: EdgeEvent,
        contract: TaskContract | None = None,
    ) -> LocalRecoveryDecision:
        """Evaluate whether local recovery is allowed for an event.

        Returns a LocalRecoveryDecision with the selected action.
        Does NOT execute the action.
        """
        now = datetime.now(UTC)
        task_id = event.task_id
        budget = self._budget_manager.get_budget(task_id)

        retry_before = budget.retry_count_used if budget else 0
        retry_limit = budget.effective_retry_limit if budget else 0

        # CRITICAL / immediate-stop events → STOP_AND_REPORT
        if event.event_type in _IMMEDIATE_STOP_EVENTS:
            return LocalRecoveryDecision(
                decision_id=f"dec-{now.strftime('%Y%m%d%H%M%S%f')}",
                event_id=event.event_id,
                action=RecoveryAction.STOP_AND_REPORT,
                allowed=False,
                reason_code="IMMEDIATE_STOP_EVENT",
                retry_count_before=retry_before,
                retry_count_after=retry_before,
                retry_limit=retry_limit,
            )

        # SAFETY_PAUSED or SAFETY_REJECTED → PAUSE_AND_REPORT
        if event.event_type in (EdgeEventType.SAFETY_REJECTED, EdgeEventType.SAFETY_PAUSED):
            return LocalRecoveryDecision(
                decision_id=f"dec-{now.strftime('%Y%m%d%H%M%S%f')}",
                event_id=event.event_id,
                action=RecoveryAction.PAUSE_AND_REPORT,
                allowed=False,
                reason_code="SAFETY_EVENT_REQUIRES_REPORT",
                retry_count_before=retry_before,
                retry_count_after=retry_before,
                retry_limit=retry_limit,
            )

        # TARGET_LOST → REQUEST_NEW_OBSERVATION
        if event.event_type == EdgeEventType.TARGET_LOST:
            return LocalRecoveryDecision(
                decision_id=f"dec-{now.strftime('%Y%m%d%H%M%S%f')}",
                event_id=event.event_id,
                action=RecoveryAction.REQUEST_NEW_OBSERVATION,
                allowed=True,
                reason_code="TARGET_LOST_NEED_OBSERVATION",
                retry_count_before=retry_before,
                retry_count_after=retry_before,
                retry_limit=retry_limit,
                requires_new_observation=True,
            )

        # TARGET_MOVED or PATH_BLOCKED or PLAN_INVALIDATED → REQUEST_CLOUD_REPLAN
        if event.event_type in (
            EdgeEventType.TARGET_MOVED,
            EdgeEventType.PATH_BLOCKED,
            EdgeEventType.PLAN_INVALIDATED,
            EdgeEventType.SCENE_CHANGED,
        ):
            return LocalRecoveryDecision(
                decision_id=f"dec-{now.strftime('%Y%m%d%H%M%S%f')}",
                event_id=event.event_id,
                action=RecoveryAction.REQUEST_CLOUD_REPLAN,
                allowed=True,
                reason_code="SCENE_CHANGE_REQUIRES_REPLAN",
                retry_count_before=retry_before,
                retry_count_after=retry_before,
                retry_limit=retry_limit,
            )

        # Locally recoverable events — check budget
        if event.event_type in _LOCALLY_RECOVERABLE:
            step_id = event.step_id or ""
            skill = ""
            if contract is not None and step_id:
                for step in contract.steps:
                    if step.step_id == step_id:
                        skill = step.skill.value
                        break
            can_retry, reason = self._budget_manager.can_attempt(
                task_id, step_id, skill, event.event_id
            )
            if can_retry:
                return LocalRecoveryDecision(
                    decision_id=f"dec-{now.strftime('%Y%m%d%H%M%S%f')}",
                    event_id=event.event_id,
                    action=RecoveryAction.RETRY_SAME_SKILL,
                    allowed=True,
                    reason_code="LOCAL_RETRY_ALLOWED",
                    retry_count_before=retry_before,
                    retry_count_after=retry_before + 1,
                    retry_limit=retry_limit,
                    delay_ms=500,
                    requires_safety_recheck=True,
                )
            else:
                return LocalRecoveryDecision(
                    decision_id=f"dec-{now.strftime('%Y%m%d%H%M%S%f')}",
                    event_id=event.event_id,
                    action=RecoveryAction.REQUEST_CLOUD_REPLAN,
                    allowed=True,
                    reason_code=reason,
                    retry_count_before=retry_before,
                    retry_count_after=retry_before,
                    retry_limit=retry_limit,
                )

        # TASK_TIMEOUT or TASK_FAILED → MARK_TASK_FAILED
        if event.event_type in (EdgeEventType.TASK_TIMEOUT, EdgeEventType.TASK_FAILED):
            return LocalRecoveryDecision(
                decision_id=f"dec-{now.strftime('%Y%m%d%H%M%S%f')}",
                event_id=event.event_id,
                action=RecoveryAction.MARK_TASK_FAILED,
                allowed=False,
                reason_code="TASK_FAILURE_TERMINAL",
                retry_count_before=retry_before,
                retry_count_after=retry_before,
                retry_limit=retry_limit,
            )

        # Default: PAUSE_AND_REPORT for unknown events
        return LocalRecoveryDecision(
            decision_id=f"dec-{now.strftime('%Y%m%d%H%M%S%f')}",
            event_id=event.event_id,
            action=RecoveryAction.PAUSE_AND_REPORT,
            allowed=False,
            reason_code="UNKNOWN_EVENT_TYPE",
            retry_count_before=retry_before,
            retry_count_after=retry_before,
            retry_limit=retry_limit,
        )

    def reset(self) -> None:
        """Clear all budgets (for testing)."""
        self._budget_manager.reset()
