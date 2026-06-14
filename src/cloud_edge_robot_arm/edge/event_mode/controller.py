"""Event-triggered mode controller.

Top-level orchestrator for Phase 6 event-triggered edge autonomy.
Manages detection -> recovery evaluation -> replanning -> resume lifecycle.
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
    RecoveryBudget,
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
from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetService
from cloud_edge_robot_arm.edge.summaries.completion import CompletionSummaryBuilder
from cloud_edge_robot_arm.edge.summaries.failure import FailureSummaryBuilder
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import EventAutonomyRepository


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

    The repository is the durable source of event-mode state. In-memory state is
    only used inside a method call to enforce legal state transitions.
    """

    def __init__(
        self,
        *,
        detector: CompositeEventDetector | None = None,
        recovery_manager: LocalRecoveryManager | None = None,
        budget_manager: RetryBudgetService | None = None,
        failure_builder: FailureSummaryBuilder | None = None,
        completion_builder: CompletionSummaryBuilder | None = None,
        outbox: PendingMessageRepository | None = None,
        repository: EventAutonomyRepository | None = None,
        runtime_profile: str = "test",
    ) -> None:
        self._detector = detector or CompositeEventDetector()
        self._profile = runtime_profile.strip().lower()
        if repository is None:
            if self._profile == "production":
                raise ValueError(
                    "EventTriggeredModeController requires a persistent repository in production"
                )
            from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
                InMemoryEventAutonomyRepository,
            )

            repository = InMemoryEventAutonomyRepository()
        self._repo = repository
        self._budget = budget_manager or RetryBudgetService(repository=self._repo)
        self._recovery = recovery_manager or LocalRecoveryManager(budget_manager=self._budget)
        self._failure_builder = failure_builder or FailureSummaryBuilder()
        self._completion_builder = completion_builder or CompletionSummaryBuilder()
        self._outbox = outbox

    @property
    def repository(self) -> EventAutonomyRepository:
        return self._repo

    def retry_budget(self, task_id: str) -> RecoveryBudget | None:
        return self._budget.get_budget(task_id)

    def initialize_task(self, contract: TaskContract) -> None:
        """Initialize event-triggered mode for a task."""
        self._repo.save_active_contract(
            contract,
            plan_id=f"plan-{contract.task_id}",
            robot_id="robot-unknown",
            status="ACTIVE",
            based_on_plan_version=None,
            correlation_id=getattr(contract, "correlation_id", ""),
        )
        self._budget.initialize(contract.task_id, contract)
        sm = self._state_machine_for_task(contract.task_id)
        if sm.current_state == EventModeState.IDLE:
            self._transition(
                sm,
                EventModeState.EXECUTING_AUTONOMOUSLY,
                "Task started",
            )

    def on_step_result(
        self,
        result: object,
        context: DetectionContext,
        contract: TaskContract,
    ) -> ControllerResult:
        """Called after each step execution in event-triggered mode."""
        task_id = contract.task_id
        sm = self._state_machine_for_task(task_id)
        if sm.current_state == EventModeState.IDLE:
            self._transition(
                sm,
                EventModeState.EXECUTING_AUTONOMOUSLY,
                "Auto-initialized",
            )

        events = self._detector.detect_all(context)
        if not events:
            if self._check_task_completed(context, contract):
                return self._handle_completion(context, contract, sm)
            return ControllerResult(action=ControllerAction.CONTINUE)

        for event in events:
            saved_event = self._repo.save_event(event)
            self._transition(
                sm,
                EventModeState.EVENT_DETECTED,
                f"Event: {saved_event.event_type.value}",
                saved_event.event_id,
            )

            if (
                saved_event.severity == EventSeverity.CRITICAL
                or saved_event.requires_immediate_stop
            ):
                return self._handle_critical_event(saved_event, contract, sm)

            self._transition(sm, EventModeState.EVALUATING_LOCAL_RECOVERY, "Evaluating recovery")
            decision = self._recovery.evaluate(saved_event, contract)
            self._transition(
                sm,
                EventModeState.LOCAL_RECOVERY_RUNNING,
                f"Decision: {decision.action.value}",
                saved_event.event_id,
            )

            if decision.action == RecoveryAction.RETRY_SAME_SKILL:
                if not decision.allowed:
                    return self._handle_budget_exhausted(saved_event, contract, sm, context)
                step_id = context.step.step_id if context.step is not None else ""
                skill = context.step.skill.value if context.step is not None else ""
                consumed, _ = self._budget.consume_if_available(
                    task_id,
                    step_id,
                    skill,
                    saved_event.event_id,
                )
                if not consumed:
                    return self._handle_budget_exhausted(saved_event, contract, sm, context)
                self._repo.mark_event_handled(saved_event.event_id)
                self._transition(
                    sm,
                    EventModeState.EXECUTING_AUTONOMOUSLY,
                    "Local retry approved",
                    saved_event.event_id,
                )
                return ControllerResult(action=ControllerAction.RETRY_STEP, event=saved_event)

            if decision.action == RecoveryAction.REQUEST_CLOUD_REPLAN:
                return self._handle_need_replan(saved_event, contract, sm, context)

            if decision.action == RecoveryAction.REQUEST_NEW_OBSERVATION:
                self._transition(
                    sm,
                    EventModeState.WAITING_FOR_NEW_OBSERVATION,
                    "Need observation",
                    saved_event.event_id,
                )
                return ControllerResult(action=ControllerAction.PAUSE, event=saved_event)

            if decision.action in (
                RecoveryAction.STOP_AND_REPORT,
                RecoveryAction.MARK_TASK_FAILED,
            ):
                return self._handle_failure(saved_event, contract, sm, context)

            if decision.action == RecoveryAction.PAUSE_AND_REPORT:
                self._transition(
                    sm,
                    EventModeState.PAUSED,
                    "Paused by recovery decision",
                    saved_event.event_id,
                )
                return ControllerResult(action=ControllerAction.PAUSE, event=saved_event)

        return ControllerResult(action=ControllerAction.CONTINUE)

    def on_task_completed(
        self,
        contract: TaskContract,
        completed_step_ids: list[str],
        local_retry_count: int = 0,
        cloud_replan_count: int = 0,
        completion_criteria_results: dict[str, bool] | None = None,
        final_robot_state: dict[str, object] | None = None,
        final_target_state: dict[str, object] | None = None,
        final_safety_decision: str = "ALLOW",
    ) -> CompletionSummary:
        """Persist a completion summary after verified task completion."""
        summary = self._completion_builder.build(
            contract=contract,
            completed_step_ids=completed_step_ids,
            completion_criteria_results=completion_criteria_results,
            local_retry_count=local_retry_count,
            cloud_replan_count=cloud_replan_count,
            final_robot_state=final_robot_state,
            final_target_state=final_target_state,
            final_safety_decision=final_safety_decision,
            result=(
                CompletionResult.SUCCESS_WITH_RECOVERY
                if local_retry_count > 0
                else CompletionResult.SUCCESS
            ),
        )
        persisted = self._repo.save_completion_summary(summary)
        self._enqueue_outbox(
            "COMPLETION_SUMMARY",
            contract.task_id,
            persisted.model_dump(mode="json"),
            summary_id=persisted.summary_id,
        )
        return persisted

    def get_state(self, task_id: str) -> EventModeState:
        state = self._repo.get_state(task_id)
        if state is None:
            return EventModeState.IDLE
        return EventModeState(state)

    def get_completion_summary(self, task_id: str) -> CompletionSummary | None:
        summary_id = f"cs-{task_id}"
        summary = self._repo.get_completion_summary(summary_id)
        if summary is not None:
            return summary
        return None

    def flush_messages(self, task_id: str | None = None) -> list[PendingMessage]:
        if self._outbox is not None:
            return self._outbox.list_pending(task_id)
        return self._repo.list_pending_outbox(task_id)

    def pending_message_count(self, task_id: str | None = None) -> int:
        return len(self.flush_messages(task_id))

    def handle_replanning_result(self, response: LocalReplanningResponse) -> ControllerResult:
        """Persist and apply a replanning result."""
        persisted = self._repo.save_replan_result(response)
        request = self._repo.get_replan_request(response.request_id)
        if request is None:
            return ControllerResult(action=ControllerAction.FAIL)
        if persisted.outcome == "REPLANNED":
            sm = self._state_machine_for_task(request.task_id)
            self._transition(sm, EventModeState.VALIDATING_REPLAN, "Replan received")
            self._transition(sm, EventModeState.RESUMING, "Replan accepted")
            return ControllerResult(action=ControllerAction.CONTINUE)
        return ControllerResult(action=ControllerAction.FAIL)

    def resume_from_persisted_state(self, task_id: str) -> str | None:
        """Recover event mode state after process restart."""
        return self._repo.get_state(task_id)

    def handle_network_recovered(self, task_id: str) -> list[PendingMessage]:
        """Return pending messages that should be dispatched after recovery."""
        return self._repo.list_pending_outbox(task_id)

    def _handle_completion(
        self,
        context: DetectionContext,
        contract: TaskContract,
        sm: EventModeStateMachine,
    ) -> ControllerResult:
        self._transition(sm, EventModeState.COMPLETED, "All steps completed")
        summary = self.on_task_completed(
            contract=contract,
            completed_step_ids=context.completed_step_ids,
        )
        return ControllerResult(action=ControllerAction.CONTINUE, summary=summary)

    def _handle_critical_event(
        self,
        event: EdgeEvent,
        contract: TaskContract,
        sm: EventModeStateMachine,
    ) -> ControllerResult:
        self._transition(
            sm, EventModeState.SAFETY_STOPPED, f"Critical: {event.reason_code}", event.event_id
        )
        self._recovery.evaluate(event, contract)
        self._enqueue_outbox(
            "EDGE_EVENT",
            contract.task_id,
            event.model_dump(mode="json"),
            event_id=event.event_id,
        )
        return ControllerResult(action=ControllerAction.SAFETY_STOP, event=event)

    def _handle_budget_exhausted(
        self,
        event: EdgeEvent,
        contract: TaskContract,
        sm: EventModeStateMachine,
        context: DetectionContext,
    ) -> ControllerResult:
        self._transition(sm, EventModeState.PREPARING_REPLAN_REQUEST, "Budget exhausted")
        summary = self._build_and_persist_failure_summary(event, contract, context)
        request = self._build_replan_request(event, summary, contract, context)
        self._repo.save_replan_request(request)
        self._enqueue_outbox(
            "LOCAL_REPLAN_REQUEST",
            contract.task_id,
            request.model_dump(mode="json"),
            event_id=event.event_id,
            summary_id=summary.summary_id,
            request_id=request.request_id,
        )
        self._transition(
            sm,
            EventModeState.WAITING_CLOUD_REPLAN,
            "Waiting for cloud replan",
            event.event_id,
        )
        return ControllerResult(
            action=ControllerAction.REPLAN_AND_CONTINUE,
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
        self._transition(sm, EventModeState.PREPARING_REPLAN_REQUEST, "Need cloud replan")
        summary = self._build_and_persist_failure_summary(event, contract, context)
        request = self._build_replan_request(event, summary, contract, context)
        self._repo.save_replan_request(request)
        self._enqueue_outbox(
            "LOCAL_REPLAN_REQUEST",
            contract.task_id,
            request.model_dump(mode="json"),
            event_id=event.event_id,
            summary_id=summary.summary_id,
            request_id=request.request_id,
        )
        self._transition(
            sm,
            EventModeState.WAITING_CLOUD_REPLAN,
            "Waiting for cloud replan",
            event.event_id,
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
        self._transition(
            sm, EventModeState.FAILED, f"Task failed: {event.reason_code}", event.event_id
        )
        summary = self._build_and_persist_failure_summary(event, contract, context)
        self._enqueue_outbox(
            "FAILURE_SUMMARY",
            contract.task_id,
            summary.model_dump(mode="json"),
            event_id=event.event_id,
            summary_id=summary.summary_id,
        )
        return ControllerResult(action=ControllerAction.FAIL, event=event, summary=summary)

    def _build_and_persist_failure_summary(
        self,
        event: EdgeEvent,
        contract: TaskContract,
        context: DetectionContext,
    ) -> FailureSummary:
        budget = self._budget.get_budget(contract.task_id)
        summary = self._failure_builder.build(
            event=event,
            contract=contract,
            completed_step_ids=context.completed_step_ids,
            retry_count=budget.retry_count_used if budget else 0,
            retry_limit=budget.effective_retry_limit if budget else 0,
            context=context,
        )
        persisted = self._repo.save_failure_summary(summary)
        self._enqueue_outbox(
            "FAILURE_SUMMARY",
            contract.task_id,
            persisted.model_dump(mode="json"),
            event_id=event.event_id,
            summary_id=persisted.summary_id,
        )
        return persisted

    def _build_replan_request(
        self,
        event: EdgeEvent,
        summary: FailureSummary,
        contract: TaskContract,
        context: DetectionContext,
    ) -> LocalReplanningRequest:
        now = datetime.now(UTC)
        request_id = f"replan-req-{contract.task_id}-{event.event_id}"
        step_id = context.step.step_id if context.step is not None else summary.failed_step_id
        return LocalReplanningRequest(
            request_id=request_id,
            trigger_event_id=event.event_id,
            failure_summary_id=summary.summary_id,
            robot_id=context.robot_id or event.robot_id or "robot-unknown",
            task_id=contract.task_id,
            plan_id=event.plan_id or f"plan-{contract.task_id}",
            current_plan_version=contract.plan_version,
            current_command_seq=contract.command_seq,
            requested_replan_scope=summary.requested_replan_scope,
            completed_step_ids=list(context.completed_step_ids),
            failed_step_id=step_id,
            last_successful_step_id=summary.last_successful_step_id,
            current_robot_state=(
                context.robot_state.model_dump(mode="json")
                if context.robot_state is not None
                else {}
            ),
            current_target_state=summary.target_state,
            current_obstacle_state=summary.obstacle_state,
            current_scene_version=context.scene_version,
            scene_confidence=context.scene_confidence,
            safe_resume_state=summary.safe_resume_state,
            requested_at=now,
            correlation_id=event.correlation_id,
            idempotency_key=f"{contract.task_id}:{event.event_id}:replan",
        )

    def _check_task_completed(self, context: DetectionContext, contract: TaskContract) -> bool:
        all_step_ids = {step.step_id for step in contract.steps}
        completed = set(context.completed_step_ids)
        return all_step_ids.issubset(completed)

    def _enqueue_outbox(
        self,
        message_type: str,
        task_id: str,
        payload: dict[str, object],
        *,
        event_id: str | None = None,
        summary_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        reference = request_id or summary_id or event_id or now.strftime("%Y%m%d%H%M%S%f")
        message_id = f"msg-{message_type.lower()}-{reference}"
        message = PendingMessage(
            message_id=message_id,
            task_id=task_id,
            event_id=event_id,
            summary_id=summary_id,
            request_id=request_id,
            idempotency_key=message_id,
            message_type=message_type,
            payload=payload,
            status=MessageStatus.PENDING,
            created_at=now,
        )
        self._repo.enqueue_outbox(message)
        if self._outbox is not None:
            self._outbox.enqueue(message)

    def _state_machine_for_task(self, task_id: str) -> EventModeStateMachine:
        sm = EventModeStateMachine(task_id)
        state = self._repo.get_state(task_id)
        if state is None:
            return sm
        for next_state in self._path_from_idle(EventModeState(state)):
            sm.transition(next_state, "Persisted resume")
        return sm

    def _transition(
        self,
        sm: EventModeStateMachine,
        to_state: EventModeState,
        reason: str,
        event_id: str = "",
    ) -> bool:
        from_state = sm.current_state
        if not sm.transition(to_state, reason, event_id):
            return False
        self._repo.save_state_transition(
            sm.history[-1].task_id,
            from_state.value,
            to_state.value,
            reason,
            event_id,
        )
        return True

    @staticmethod
    def _path_from_idle(state: EventModeState) -> list[EventModeState]:
        paths: dict[EventModeState, list[EventModeState]] = {
            EventModeState.IDLE: [],
            EventModeState.EXECUTING_AUTONOMOUSLY: [EventModeState.EXECUTING_AUTONOMOUSLY],
            EventModeState.EVENT_DETECTED: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
            ],
            EventModeState.EVALUATING_LOCAL_RECOVERY: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
            ],
            EventModeState.LOCAL_RECOVERY_RUNNING: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
                EventModeState.LOCAL_RECOVERY_RUNNING,
            ],
            EventModeState.PREPARING_REPLAN_REQUEST: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
                EventModeState.PREPARING_REPLAN_REQUEST,
            ],
            EventModeState.WAITING_CLOUD_REPLAN: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
                EventModeState.PREPARING_REPLAN_REQUEST,
                EventModeState.WAITING_CLOUD_REPLAN,
            ],
            EventModeState.PAUSED: [EventModeState.EXECUTING_AUTONOMOUSLY, EventModeState.PAUSED],
            EventModeState.SAFETY_STOPPED: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.SAFETY_STOPPED,
            ],
            EventModeState.FAILED: [EventModeState.EXECUTING_AUTONOMOUSLY, EventModeState.FAILED],
            EventModeState.COMPLETED: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.COMPLETED,
            ],
            EventModeState.WAITING_FOR_NEW_OBSERVATION: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
                EventModeState.WAITING_FOR_NEW_OBSERVATION,
            ],
            EventModeState.REPLAN_RECEIVED: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
                EventModeState.PREPARING_REPLAN_REQUEST,
                EventModeState.WAITING_CLOUD_REPLAN,
                EventModeState.REPLAN_RECEIVED,
            ],
            EventModeState.VALIDATING_REPLAN: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
                EventModeState.PREPARING_REPLAN_REQUEST,
                EventModeState.WAITING_CLOUD_REPLAN,
                EventModeState.REPLAN_RECEIVED,
                EventModeState.VALIDATING_REPLAN,
            ],
            EventModeState.APPLYING_REPLAN: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
                EventModeState.PREPARING_REPLAN_REQUEST,
                EventModeState.WAITING_CLOUD_REPLAN,
                EventModeState.REPLAN_RECEIVED,
                EventModeState.VALIDATING_REPLAN,
                EventModeState.APPLYING_REPLAN,
            ],
            EventModeState.WAITING_EDGE_ACK: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
                EventModeState.PREPARING_REPLAN_REQUEST,
                EventModeState.WAITING_CLOUD_REPLAN,
                EventModeState.REPLAN_RECEIVED,
                EventModeState.VALIDATING_REPLAN,
                EventModeState.APPLYING_REPLAN,
                EventModeState.WAITING_EDGE_ACK,
            ],
            EventModeState.READY_TO_RESUME: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
                EventModeState.PREPARING_REPLAN_REQUEST,
                EventModeState.WAITING_CLOUD_REPLAN,
                EventModeState.REPLAN_RECEIVED,
                EventModeState.VALIDATING_REPLAN,
                EventModeState.APPLYING_REPLAN,
                EventModeState.WAITING_EDGE_ACK,
                EventModeState.READY_TO_RESUME,
            ],
            EventModeState.RESUMING: [
                EventModeState.EXECUTING_AUTONOMOUSLY,
                EventModeState.EVENT_DETECTED,
                EventModeState.EVALUATING_LOCAL_RECOVERY,
                EventModeState.PREPARING_REPLAN_REQUEST,
                EventModeState.WAITING_CLOUD_REPLAN,
                EventModeState.REPLAN_RECEIVED,
                EventModeState.VALIDATING_REPLAN,
                EventModeState.APPLYING_REPLAN,
                EventModeState.WAITING_EDGE_ACK,
                EventModeState.READY_TO_RESUME,
                EventModeState.RESUMING,
            ],
        }
        return paths[state]
