"""EventAutonomyRepository Protocol — persistence contract for Phase 6.

Follows the same pattern as SupervisionRepository from
cloud/supervision/repository.py — runtime-checkable Protocol with
clear method signatures for both InMemory and SQLite implementations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from cloud_edge_robot_arm.contracts.models import (
    CompletionSummary,
    EdgeEvent,
    FailureSummary,
    LocalReplanningRequest,
    LocalReplanningResponse,
    PendingMessage,
    RecoveryBudget,
)


@runtime_checkable
class EventAutonomyRepository(Protocol):
    """Unified persistence contract for event-triggered edge autonomy.

    Covers:
    - Edge events (detection, persistence, handling)
    - Retry budgets (CAS-safe atomic consumption)
    - Event mode state machine (state + transitions)
    - Failure summaries (deterministic, persisted)
    - Completion summaries (evaluated, not assumed)
    - Replan requests and results (CAS version management)
    - Outbox (persist-before-send, atomic claim, DEAD_LETTER)
    - Audit events (immutable log)

    All date/time values use ISO 8601 strings in UTC.
    All CAS operations MUST be atomic (SQLite rowcount or Lock-guarded).
    """

    # ── Events ──────────────────────────────────────────────────────────

    def save_event(self, event: EdgeEvent) -> EdgeEvent:
        """Persist an edge event. Idempotent on event_id unique constraint."""
        ...

    def get_event(self, event_id: str) -> EdgeEvent | None:
        """Retrieve an event by its unique ID. Returns None if not found."""
        ...

    def list_events(self, task_id: str) -> list[EdgeEvent]:
        """List all events for a given task, ordered by creation time."""
        ...

    def mark_event_handled(self, event_id: str, handled_at: datetime | None = None) -> bool:
        """Mark an event as having been processed. Returns False if not found."""
        ...

    # ── Retry Budget ────────────────────────────────────────────────────

    def save_retry_budget(self, budget: RecoveryBudget) -> RecoveryBudget:
        """Persist or update a retry budget. Upsert on task_id."""
        ...

    def get_retry_budget(self, task_id: str) -> RecoveryBudget | None:
        """Get the current retry budget for a task."""
        ...

    def consume_retry_if_available(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        expected_count: int,
    ) -> tuple[bool, RecoveryBudget | None]:
        """Atomically consume one retry via CAS.

        Only succeeds if retry_count_used == expected_count AND
        remaining_retries > 0. Returns (consumed, updated_budget_or_None).
        Must be safe against concurrent consumers.
        """
        ...

    # ── State Machine ───────────────────────────────────────────────────

    def save_state(
        self,
        task_id: str,
        state: str,
        reason: str,
        event_id: str = "",
    ) -> None:
        """Persist the current event mode state for a task."""
        ...

    def get_state(self, task_id: str) -> str | None:
        """Get the current event mode state. Returns None if not initialized."""
        ...

    def save_state_transition(
        self,
        task_id: str,
        from_state: str,
        to_state: str,
        reason: str,
        event_id: str = "",
    ) -> None:
        """Record a state transition for audit trail."""
        ...

    def list_state_transitions(self, task_id: str) -> list[dict[str, object]]:
        """List all state transitions for a task in chronological order."""
        ...

    # ── Failure Summary ─────────────────────────────────────────────────

    def save_failure_summary(self, summary: FailureSummary) -> FailureSummary:
        """Persist a failure summary. Idempotent on summary_id unique constraint."""
        ...

    def get_failure_summary(self, summary_id: str) -> FailureSummary | None:
        """Retrieve a failure summary by ID. Returns None if not found."""
        ...

    # ── Completion Summary ──────────────────────────────────────────────

    def save_completion_summary(self, summary: CompletionSummary) -> CompletionSummary:
        """Persist a completion summary. Idempotent on summary_id unique constraint."""
        ...

    def get_completion_summary(self, summary_id: str) -> CompletionSummary | None:
        """Retrieve a completion summary by ID. Returns None if not found."""
        ...

    def get_completion_summary_for_task(self, task_id: str) -> CompletionSummary | None:
        """Retrieve the latest completion summary for a task."""
        ...

    # ── Replan ──────────────────────────────────────────────────────────

    def save_replan_request(self, request: LocalReplanningRequest) -> LocalReplanningRequest:
        """Persist a replan request. Idempotent on request_id unique constraint."""
        ...

    def get_replan_request(self, request_id: str) -> LocalReplanningRequest | None:
        """Retrieve a replan request by ID."""
        ...

    def save_replan_result(self, result: LocalReplanningResponse) -> LocalReplanningResponse:
        """Persist a replan result. Idempotent on request_id unique constraint."""
        ...

    def get_replan_result(self, request_id: str) -> LocalReplanningResponse | None:
        """Retrieve a replan result by request ID."""
        ...

    # ── Outbox ──────────────────────────────────────────────────────────

    def enqueue_outbox(self, message: PendingMessage) -> PendingMessage:
        """Persist a message before attempting to send (persist-before-send)."""
        ...

    def claim_outbox_message(self) -> PendingMessage | None:
        """Atomically claim the next PENDING message.

        Transition: PENDING -> SENDING. Only one consumer succeeds.
        Returns None if no pending messages are available.
        """
        ...

    def mark_outbox_sent(self, message_id: str) -> bool:
        """Mark a message as successfully sent. Transition: SENDING -> SENT."""
        ...

    def mark_outbox_failed(self, message_id: str, error: str) -> bool:
        """Handle a send failure.

        Increments retry_count. If retry_count >= max_retries:
        SENDING -> DEAD_LETTER. Otherwise: SENDING -> PENDING
        with exponential backoff on next_attempt_at.
        """
        ...

    def list_pending_outbox(self, task_id: str | None = None) -> list[PendingMessage]:
        """List PENDING messages, optionally filtered by task_id."""
        ...

    # ── Version Management ──────────────────────────────────────────────

    def advance_plan_version_if_current(
        self,
        task_id: str,
        expected_plan_version: int,
        expected_command_seq: int,
        new_plan_version: int,
        new_command_seq: int,
    ) -> bool:
        """CAS version bump. Only succeeds if current version matches expected.

        Prevents two replan results from simultaneously upgrading the version,
        and prevents old results from overwriting new ones.
        """
        ...

    # ── Audit ───────────────────────────────────────────────────────────

    def record_audit_event(
        self,
        task_id: str,
        event_type: str,
        details: dict[str, object],
    ) -> None:
        """Record an immutable audit event for traceability."""
        ...

    # ── Lifecycle ───────────────────────────────────────────────────────

    def close(self) -> None:
        """Release database connections and other resources."""
        ...
