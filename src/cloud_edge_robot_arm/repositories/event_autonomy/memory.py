"""In-memory EventAutonomyRepository — thread-safe, test/CI only.

Follows the InMemorySupervisionRepository pattern from
cloud/supervision/repository.py. Uses threading.Lock for CAS semantics.
Must NOT be used in production — no restart recovery.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.contracts.models import (
    CompletionSummary,
    EdgeEvent,
    FailureSummary,
    LocalReplanningRequest,
    LocalReplanningResponse,
    MessageStatus,
    PendingMessage,
    RecoveryBudget,
)


class InMemoryEventAutonomyRepository:
    """Thread-safe in-memory implementation for testing and CI.

    All CAS operations are protected by a single reentrant lock.
    No data survives process restart.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, EdgeEvent] = {}
        self._events_by_task: dict[str, list[str]] = {}
        self._budgets: dict[str, RecoveryBudget] = {}
        self._states: dict[str, str] = {}
        self._transitions: dict[str, list[dict[str, object]]] = {}
        self._failure_summaries: dict[str, FailureSummary] = {}
        self._completion_summaries: dict[str, CompletionSummary] = {}
        self._replan_requests: dict[str, LocalReplanningRequest] = {}
        self._replan_results: dict[str, LocalReplanningResponse] = {}
        self._outbox: dict[str, PendingMessage] = {}
        self._plan_versions: dict[str, tuple[int, int]] = {}
        self._audit: dict[str, list[dict[str, object]]] = {}

    # ── Events ──────────────────────────────────────────────────────────

    def save_event(self, event: EdgeEvent) -> EdgeEvent:
        with self._lock:
            if event.event_id in self._events:
                return self._events[event.event_id]
            self._events[event.event_id] = event
            self._events_by_task.setdefault(event.task_id, []).append(event.event_id)
            return event

    def get_event(self, event_id: str) -> EdgeEvent | None:
        return self._events.get(event_id)

    def list_events(self, task_id: str) -> list[EdgeEvent]:
        ids = self._events_by_task.get(task_id, [])
        return [self._events[eid] for eid in ids if eid in self._events]

    def mark_event_handled(self, event_id: str, handled_at: datetime | None = None) -> bool:
        if event_id not in self._events:
            return False
        return True

    # ── Retry Budget ────────────────────────────────────────────────────

    def save_retry_budget(self, budget: RecoveryBudget) -> RecoveryBudget:
        with self._lock:
            self._budgets[budget.task_id] = budget
            return budget

    def get_retry_budget(self, task_id: str) -> RecoveryBudget | None:
        return self._budgets.get(task_id)

    def consume_retry_if_available(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        expected_count: int,
    ) -> tuple[bool, RecoveryBudget | None]:
        with self._lock:
            budget = self._budgets.get(task_id)
            if budget is None:
                return False, None
            if budget.retry_count_used != expected_count:
                return False, budget
            if budget.remaining_retries <= 0:
                return False, budget
            now = datetime.now(UTC)
            updated = RecoveryBudget(
                budget_id=budget.budget_id,
                task_id=budget.task_id,
                per_step_retry_limit=budget.per_step_retry_limit,
                per_skill_retry_limit=budget.per_skill_retry_limit,
                task_total_retry_limit=budget.task_total_retry_limit,
                retry_count_used=budget.retry_count_used + 1,
                retry_cooldown_ms=budget.retry_cooldown_ms,
                retry_deadline=budget.retry_deadline,
                retry_backoff_policy=budget.retry_backoff_policy,
                effective_retry_limit=budget.effective_retry_limit,
                remaining_retries=budget.remaining_retries - 1,
                scene_version=budget.scene_version,
                created_at=budget.created_at,
                updated_at=now,
            )
            self._budgets[task_id] = updated
            return True, updated

    # ── State Machine ───────────────────────────────────────────────────

    def save_state(
        self,
        task_id: str,
        state: str,
        reason: str,
        event_id: str = "",
    ) -> None:
        with self._lock:
            self._states[task_id] = state

    def get_state(self, task_id: str) -> str | None:
        return self._states.get(task_id)

    def save_state_transition(
        self,
        task_id: str,
        from_state: str,
        to_state: str,
        reason: str,
        event_id: str = "",
    ) -> None:
        with self._lock:
            entry: dict[str, object] = {
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "event_id": event_id,
                "timestamp": datetime.now(UTC).isoformat(),
            }
            self._transitions.setdefault(task_id, []).append(entry)
            self._states[task_id] = to_state

    def list_state_transitions(self, task_id: str) -> list[dict[str, object]]:
        return list(self._transitions.get(task_id, []))

    # ── Failure Summary ─────────────────────────────────────────────────

    def save_failure_summary(self, summary: FailureSummary) -> FailureSummary:
        with self._lock:
            if summary.summary_id not in self._failure_summaries:
                self._failure_summaries[summary.summary_id] = summary
            return self._failure_summaries[summary.summary_id]

    def get_failure_summary(self, summary_id: str) -> FailureSummary | None:
        return self._failure_summaries.get(summary_id)

    # ── Completion Summary ──────────────────────────────────────────────

    def save_completion_summary(self, summary: CompletionSummary) -> CompletionSummary:
        with self._lock:
            if summary.summary_id not in self._completion_summaries:
                self._completion_summaries[summary.summary_id] = summary
            return self._completion_summaries[summary.summary_id]

    def get_completion_summary(self, summary_id: str) -> CompletionSummary | None:
        return self._completion_summaries.get(summary_id)

    def get_completion_summary_for_task(self, task_id: str) -> CompletionSummary | None:
        matches = [
            summary for summary in self._completion_summaries.values() if summary.task_id == task_id
        ]
        return matches[-1] if matches else None

    # ── Replan ──────────────────────────────────────────────────────────

    def save_replan_request(self, request: LocalReplanningRequest) -> LocalReplanningRequest:
        with self._lock:
            if request.request_id not in self._replan_requests:
                self._replan_requests[request.request_id] = request
            return self._replan_requests[request.request_id]

    def get_replan_request(self, request_id: str) -> LocalReplanningRequest | None:
        return self._replan_requests.get(request_id)

    def save_replan_result(self, result: LocalReplanningResponse) -> LocalReplanningResponse:
        with self._lock:
            if result.request_id not in self._replan_results:
                self._replan_results[result.request_id] = result
            return self._replan_results[result.request_id]

    def get_replan_result(self, request_id: str) -> LocalReplanningResponse | None:
        return self._replan_results.get(request_id)

    # ── Outbox ──────────────────────────────────────────────────────────

    def enqueue_outbox(self, message: PendingMessage) -> PendingMessage:
        with self._lock:
            if message.message_id in self._outbox:
                return self._outbox[message.message_id]
            self._outbox[message.message_id] = message
            return message

    def claim_outbox_message(self) -> PendingMessage | None:
        with self._lock:
            for msg in self._outbox.values():
                now = datetime.now(UTC)
                if msg.status not in {MessageStatus.PENDING, MessageStatus.RETRY_WAIT}:
                    continue
                if msg.next_retry_at is not None and msg.next_retry_at > now:
                    continue
                updated = PendingMessage(
                    message_id=msg.message_id,
                    task_id=msg.task_id,
                    event_id=msg.event_id,
                    summary_id=msg.summary_id,
                    request_id=msg.request_id,
                    idempotency_key=msg.idempotency_key,
                    message_type=msg.message_type,
                    payload=deepcopy(msg.payload),
                    status=MessageStatus.SENDING,
                    created_at=msg.created_at,
                    retry_count=msg.retry_count,
                    max_retries=msg.max_retries,
                    last_error=msg.last_error,
                    next_retry_at=msg.next_retry_at,
                    backoff_base_ms=msg.backoff_base_ms,
                )
                self._outbox[msg.message_id] = updated
                return updated
            return None

    def mark_outbox_sent(self, message_id: str) -> bool:
        with self._lock:
            if message_id not in self._outbox:
                return False
            msg = self._outbox[message_id]
            updated = PendingMessage(
                message_id=msg.message_id,
                task_id=msg.task_id,
                event_id=msg.event_id,
                summary_id=msg.summary_id,
                request_id=msg.request_id,
                message_type=msg.message_type,
                payload=deepcopy(msg.payload),
                status=MessageStatus.SENT,
                created_at=msg.created_at,
                retry_count=msg.retry_count,
                max_retries=msg.max_retries,
                last_error=msg.last_error,
                next_retry_at=msg.next_retry_at,
                backoff_base_ms=msg.backoff_base_ms,
            )
            self._outbox[message_id] = updated
            return True

    def mark_outbox_failed(self, message_id: str, error: str) -> bool:
        with self._lock:
            if message_id not in self._outbox:
                return False
            msg = self._outbox[message_id]
            new_count = msg.retry_count + 1
            if new_count >= msg.max_retries:
                new_status = MessageStatus.DEAD_LETTER
                next_attempt = None
            else:
                new_status = MessageStatus.RETRY_WAIT
                backoff_ms = msg.backoff_base_ms * (2 ** (new_count - 1))
                next_attempt = datetime.now(UTC) + timedelta(milliseconds=backoff_ms)
            updated = PendingMessage(
                message_id=msg.message_id,
                task_id=msg.task_id,
                event_id=msg.event_id,
                summary_id=msg.summary_id,
                request_id=msg.request_id,
                message_type=msg.message_type,
                payload=deepcopy(msg.payload),
                status=new_status,
                created_at=msg.created_at,
                retry_count=new_count,
                max_retries=msg.max_retries,
                last_error=error,
                next_retry_at=next_attempt,
                backoff_base_ms=msg.backoff_base_ms,
            )
            self._outbox[message_id] = updated
            return True

    def list_pending_outbox(self, task_id: str | None = None) -> list[PendingMessage]:
        with self._lock:
            result: list[PendingMessage] = []
            for msg in self._outbox.values():
                if msg.status not in {MessageStatus.PENDING, MessageStatus.RETRY_WAIT}:
                    continue
                if task_id is not None and msg.task_id != task_id:
                    continue
                result.append(deepcopy(msg))
            return result

    # ── Version Management ──────────────────────────────────────────────

    def advance_plan_version_if_current(
        self,
        task_id: str,
        expected_plan_version: int,
        expected_command_seq: int,
        new_plan_version: int,
        new_command_seq: int,
    ) -> bool:
        with self._lock:
            if new_plan_version <= expected_plan_version or new_command_seq <= expected_command_seq:
                return False
            current = self._plan_versions.get(task_id)
            if current is None:
                current = (expected_plan_version, expected_command_seq)
                self._plan_versions[task_id] = current
            if current[0] != expected_plan_version or current[1] != expected_command_seq:
                return False
            self._plan_versions[task_id] = (new_plan_version, new_command_seq)
            return True

    # ── Audit ───────────────────────────────────────────────────────────

    def record_audit_event(
        self,
        task_id: str,
        event_type: str,
        details: dict[str, object],
    ) -> None:
        with self._lock:
            entry: dict[str, object] = {
                "event_type": event_type,
                "details": deepcopy(details),
                "created_at": datetime.now(UTC).isoformat(),
            }
            self._audit.setdefault(task_id, []).append(entry)

    # ── Lifecycle ───────────────────────────────────────────────────────

    def close(self) -> None:
        with self._lock:
            self._events.clear()
            self._events_by_task.clear()
            self._budgets.clear()
            self._states.clear()
            self._transitions.clear()
            self._failure_summaries.clear()
            self._completion_summaries.clear()
            self._replan_requests.clear()
            self._replan_results.clear()
            self._outbox.clear()
            self._plan_versions.clear()
            self._audit.clear()
