"""Event-triggered mode controller.

Top-level orchestrator for Phase 6 event-triggered edge autonomy.
Manages detection → recovery evaluation → replanning → resume lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from cloud_edge_robot_arm.contracts.models import (
    CompletionResult,
    CompletionSummary,
    EdgeEvent,
    EventSeverity,
    FailureSummary,
    LocalReplanningRequest,
    LocalReplanningResponse,
    MessageStatus,
    PendingMessage,
    RecoveryAction,
    TaskContract,
)
from cloud_edge_robot_arm.edge.event_mode.state_machine import (
    EventModeState,
    EventModeStateMachine,
)
from cloud_edge_robot_arm.edge.events.composite import CompositeEventDetector
from cloud_edge_robot_arm.edge.events.models import DetectionContext
from cloud_edge_robot_arm.edge.outbox import PendingMessageRepository
from cloud_edge_robot_arm.edge.recovery.manager import LocalRecoveryManager
from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetManager
from cloud_edge_robot_arm.edge.summaries.completion import CompletionSummaryBuilder
from cloud_edge_robot_arm.edge.summaries.failure import FailureSummaryBuilder
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    EventAutonomyRepository,
)


class ControllerAction(StrEnum):
    CONTINUE = "CONTINUE"
    RETRY_STEP = "RETRY_STEP"
    REPLAN_AND_CONTINUE = "REPLAN_AND_CONTINUE"
    PAUSE = "PAUSE"
    FAIL = "FAIL"
    SAFETY_STOP = "SAFETY_STOP"


@dataclass(frozen=True)
class ControllerResult:
    action: ControllerAction
    updated_contract: TaskContract | None = None
    event: EdgeEvent | None = None
    summary: FailureSummary | CompletionSummary | None = None
    error: str = ""


class EventTriggeredModeController:
    """Orchestrator for event-triggered edge autonomy.

    Wires together:
    - CompositeEventDetector (event detection)
    - LocalRecoveryManager (budget + decisions)
    - FailureSummaryBuilder (deterministic summaries)
    - CompletionSummaryBuilder (task completion)
    - PendingMessageRepository (outbox)
    - EventModeStateMachine (lifecycle state)

    Does NOT control the robot directly — delegates to TaskExecutor + SafetyShield.
    """

    def __init__(
        self,
        *,
        detector: CompositeEventDetector | None = None,
        recovery_manager: LocalRecoveryManager | None = None,
        budget_manager: RetryBudgetManager | None = None,
        failure_builder: FailureSummaryBuilder | None = None,
        completion_builder: CompletionSummaryBuilder | None = None,
        outbox: PendingMessageRepository | None = None,
        repository: EventAutonomyRepository | None = None,
        runtime_profile: str = "test",
    ) -> None:
        self._detector = detector or CompositeEventDetector()
        self._budget = budget_manager or RetryBudgetManager()
        self._recovery = recovery_manager or LocalRecoveryManager(budget_manager=self._budget)
        self._failure_builder = failure_builder or FailureSummaryBuilder()
        self._completion_builder = completion_builder or CompletionSummaryBuilder()
        self._outbox = outbox
        self._repo = repository
        self._profile = runtime_profile
        self._state_machines: dict[str, EventModeStateMachine] = {}
        self._completion_summaries: dict[str, CompletionSummary] = {}

    def initialize_task(self, contract: TaskContract) -> None:
        """Initialize event-triggered mode for a task."""
        task_id = contract.task_id
        self._budget.initialize(task_id, contract)
        sm = EventModeStateMachine(task_id)
        sm.transition(EventModeState.EXECUTING_AUTONOMOUSLY, "Task started")
        self._state_machines[task_id] = sm

    def on_step_result(
        self,
        result: object,
        context: DetectionContext,
        contract: TaskContract,
    ) -> ControllerResult:
        """Called after each step execution in event-triggered mode.

        Returns the controller's decision for what to do next.
        """
        task_id = contract.task_id
        sm = self._state_machines.get(task_id)
        if sm is None:
            sm = EventModeStateMachine(task_id)
            sm.transition(EventModeState.EXECUTING_AUTONOMOUSLY, "Auto-initialized")
            self._state_machines[task_id] = sm

        # Run all detectors
        events = self._detector.detect_all(context)

        if not events:
            # No events → check for task completion
            if self._check_task_completed(context, contract):
                return self._handle_completion(context, contract, sm)
            return ControllerResult(action=ControllerAction.CONTINUE)

        # Process events in priority order
        for event in events:
            sm.transition(
                EventModeState.EVENT_DETECTED, f"Event: {event.event_type.value}", event.event_id
            )

            # CRITICAL events → immediate safety stop
            if event.severity == EventSeverity.CRITICAL or event.requires_immediate_stop:
                return self._handle_critical_event(event, contract, sm)

            sm.transition(EventModeState.EVALUATING_LOCAL_RECOVERY, "Evaluating recovery")

            # Evaluate recovery
            decision = self._recovery.evaluate(event, contract)
            sm.transition(
                EventModeState.LOCAL_RECOVERY_RUNNING,
                f"Decision: {decision.action.value}",
                event.event_id,
            )

            # Execute decision
            if decision.action == RecoveryAction.RETRY_SAME_SKILL:
                if decision.allowed:
                    self._budget.consume(task_id)
                    return ControllerResult(
                        action=ControllerAction.RETRY_STEP,
                        event=event,
                    )
                else:
                    # Budget exhausted → build failure summary
                    return self._handle_budget_exhausted(event, contract, sm, context)

            elif decision.action == RecoveryAction.REQUEST_CLOUD_REPLAN:
                return self._handle_need_replan(event, contract, sm, context)

            elif decision.action == RecoveryAction.REQUEST_NEW_OBSERVATION:
                sm.transition(EventModeState.WAITING_FOR_NEW_OBSERVATION, "Need observation")
                return ControllerResult(action=ControllerAction.PAUSE, event=event)

            elif decision.action in (
                RecoveryAction.STOP_AND_REPORT,
                RecoveryAction.MARK_TASK_FAILED,
            ):
                return self._handle_failure(event, contract, sm, context)

            elif decision.action == RecoveryAction.PAUSE_AND_REPORT:
                sm.transition(EventModeState.PAUSED, "Paused by recovery decision")
                return ControllerResult(action=ControllerAction.PAUSE, event=event)

        return ControllerResult(action=ControllerAction.CONTINUE)

    def on_task_completed(
        self,
        contract: TaskContract,
        completed_step_ids: list[str],
        local_retry_count: int = 0,
        cloud_replan_count: int = 0,
    ) -> CompletionSummary:
        """Called when task completes successfully."""
        summary = self._completion_builder.build(
            contract=contract,
            completed_step_ids=completed_step_ids,
            local_retry_count=local_retry_count,
            cloud_replan_count=cloud_replan_count,
            result=(
                CompletionResult.SUCCESS_WITH_RECOVERY
                if local_retry_count > 0
                else CompletionResult.SUCCESS
            ),
        )
        self._completion_summaries[contract.task_id] = summary
        self._enqueue_outbox("COMPLETION_SUMMARY", contract.task_id, summary.model_dump())
        return summary

    def get_state(self, task_id: str) -> EventModeState:
        sm = self._state_machines.get(task_id)
        return sm.current_state if sm else EventModeState.IDLE

    def get_completion_summary(self, task_id: str) -> CompletionSummary | None:
        return self._completion_summaries.get(task_id)

    def flush_messages(self, task_id: str | None = None) -> list[PendingMessage]:
        if self._outbox is None:
            return []
        return self._outbox.list_pending(task_id)

    def pending_message_count(self, task_id: str | None = None) -> int:
        if self._outbox is None:
            return 0
        return self._outbox.count_pending(task_id)

    # --- Repository-backed operations ---

    def handle_replanning_result(
        self,
        response: LocalReplanningResponse,
    ) -> ControllerResult:
        """Process a replanning result, with CAS validation."""
        if self._repo is not None:
            self._repo.save_replan_result(response)
            if response.outcome == "REPLANNED":
                self._repo.save_state(
                    response.request_id.split("-")[2]
                    if len(response.request_id.split("-")) >= 3
                    else "",
                    "RESUMING",
                    "Replan accepted",
                )
        if response.outcome == "REPLANNED":
            return ControllerResult(action=ControllerAction.CONTINUE)
        return ControllerResult(action=ControllerAction.FAIL)

    def resume_from_persisted_state(self, task_id: str) -> str | None:
        """Recover event mode state after process restart."""
        if self._repo is not None:
            return self._repo.get_state(task_id)
        return self._state_machines.get(task_id, EventModeStateMachine(task_id)).current_state

    def handle_network_recovered(self, task_id: str) -> list[PendingMessage]:
        """Re-enqueue pending outbox messages after network recovery."""
        if self._repo is not None:
            return self._repo.list_pending_outbox(task_id)
        if self._outbox is not None:
            return self._outbox.list_pending(task_id)
        return []

    # --- Private helpers ---

    def _handle_completion(
        self,
        context: DetectionContext,
        contract: TaskContract,
        sm: EventModeStateMachine,
    ) -> ControllerResult:
        sm.transition(EventModeState.COMPLETED, "All steps completed")
        summary = self.on_task_completed(
            contract=contract,
            completed_step_ids=context.completed_step_ids,
        )
        return ControllerResult(
            action=ControllerAction.CONTINUE,
            summary=summary,
        )

    def _handle_critical_event(
        self,
        event: EdgeEvent,
        contract: TaskContract,
        sm: EventModeStateMachine,
    ) -> ControllerResult:
        sm.transition(
            EventModeState.SAFETY_STOPPED, f"Critical: {event.reason_code}", event.event_id
        )
        self._recovery.evaluate(event, contract)
        self._enqueue_outbox("EDGE_EVENT", contract.task_id, event.model_dump())
        return ControllerResult(
            action=ControllerAction.SAFETY_STOP,
            event=event,
            summary=None,
        )

    def _handle_budget_exhausted(
        self,
        event: EdgeEvent,
        contract: TaskContract,
        sm: EventModeStateMachine,
        context: DetectionContext,
    ) -> ControllerResult:
        sm.transition(EventModeState.PREPARING_REPLAN_REQUEST, "Budget exhausted")
        budget = self._budget.get_budget(contract.task_id)
        summary = self._failure_builder.build(
            event=event,
            contract=contract,
            completed_step_ids=context.completed_step_ids,
            retry_count=budget.retry_count_used if budget else 0,
            retry_limit=budget.effective_retry_limit if budget else 0,
            context=context,
        )
        self._enqueue_outbox("FAILURE_SUMMARY", contract.task_id, summary.model_dump())
        return ControllerResult(
            action=ControllerAction.PAUSE,
            event=event,
            summary=summary,
        )

    def _handle_need_replan(
        self,
        event: EdgeEvent,
        contract: TaskContract,
        sm: EventModeStateMachine,
        context: DetectionContext,
    ) -> ControllerResult:
        sm.transition(EventModeState.PREPARING_REPLAN_REQUEST, "Need cloud replan")
        summary = self._failure_builder.build(
            event=event,
            contract=contract,
            completed_step_ids=context.completed_step_ids,
            retry_count=0,
            retry_limit=0,
            context=context,
        )
        return ControllerResult(
            action=ControllerAction.REPLAN_AND_CONTINUE,
            event=event,
            summary=summary,
        )

    def _handle_failure(
        self,
        event: EdgeEvent,
        contract: TaskContract,
        sm: EventModeStateMachine,
        context: DetectionContext,
    ) -> ControllerResult:
        sm.transition(EventModeState.FAILED, f"Task failed: {event.reason_code}", event.event_id)
        summary = self._failure_builder.build(
            event=event,
            contract=contract,
            completed_step_ids=context.completed_step_ids,
            context=context,
        )
        self._enqueue_outbox("FAILURE_SUMMARY", contract.task_id, summary.model_dump())
        return ControllerResult(
            action=ControllerAction.FAIL,
            event=event,
            summary=summary,
        )

    def _check_task_completed(self, context: DetectionContext, contract: TaskContract) -> bool:
        all_step_ids = {s.step_id for s in contract.steps}
        completed = set(context.completed_step_ids)
        return all_step_ids.issubset(completed)

    def _enqueue_outbox(self, message_type: str, task_id: str, payload: dict[str, object]) -> None:
        if self._outbox is None:
            return
        now = datetime.now(UTC)
        msg_id = f"msg-{now.strftime('%Y%m%d%H%M%S%f')}"
        message = PendingMessage(
            message_id=msg_id,
            task_id=task_id,
            message_type=message_type,
            payload=payload,
            status=MessageStatus.PENDING,
            created_at=now,
        )
        self._outbox.enqueue(message)
