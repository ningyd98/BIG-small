"""EventAutonomyRepository Protocol — persistence contract for Phase 6.

The repository is the durable source of truth for event-triggered autonomy.
Duplicate writes are idempotent only when the payload hash matches; otherwise
repositories raise a structured conflict instead of silently swallowing database
constraint errors.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from cloud_edge_robot_arm.contracts.models import (
    ActiveTaskContractRecord,
    CommandAck,
    CompletionSummary,
    EdgeEvent,
    ExecutionCheckpoint,
    FailureSummary,
    LocalReplanningRequest,
    LocalReplanningResponse,
    PendingMessage,
    RecoveryBudget,
    ReplanApplyRecord,
    TaskContract,
)


class RepositoryConflictError(RuntimeError):
    """Base class for repository conflicts that must surface to callers."""


class IdempotencyConflictError(RepositoryConflictError):
    """Raised when the same unique key is reused with different content."""


class VersionConflictError(RepositoryConflictError):
    """Raised when a compare-and-set version update fails."""


@runtime_checkable
class EventAutonomyRepository(Protocol):
    """Unified persistence contract for event-triggered edge autonomy."""

    # ── Events ──────────────────────────────────────────────────────────

    def save_event(self, event: EdgeEvent) -> EdgeEvent:
        """Persist an edge event with same-key same-content idempotency."""
        ...

    def get_event(self, event_id: str) -> EdgeEvent | None:
        """Retrieve an event by its unique ID. Returns None if not found."""
        ...

    def list_events(self, task_id: str) -> list[EdgeEvent]:
        """List all events for a given task, ordered by creation time."""
        ...

    def mark_event_handled(self, event_id: str, handled_at: datetime | None = None) -> bool:
        """Mark an event as processed. Returns False if not found."""
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
        event_id: str = "",
    ) -> tuple[bool, RecoveryBudget | None]:
        """Atomically consume one retry across task, step, skill, and event dimensions."""
        ...

    # ── State Machine ───────────────────────────────────────────────────

    def save_state(self, task_id: str, state: str, reason: str, event_id: str = "") -> None:
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
        """Persist a failure summary with payload-hash idempotency."""
        ...

    def get_failure_summary(self, summary_id: str) -> FailureSummary | None:
        """Retrieve a failure summary by ID. Returns None if not found."""
        ...

    # ── Completion Summary ──────────────────────────────────────────────

    def save_completion_summary(self, summary: CompletionSummary) -> CompletionSummary:
        """Persist a completion summary with payload-hash idempotency."""
        ...

    def get_completion_summary(self, summary_id: str) -> CompletionSummary | None:
        """Retrieve a completion summary by ID. Returns None if not found."""
        ...

    def get_completion_summary_for_task(self, task_id: str) -> CompletionSummary | None:
        """Retrieve the latest completion summary for a task."""
        ...

    # ── Replan ──────────────────────────────────────────────────────────

    def save_replan_request(self, request: LocalReplanningRequest) -> LocalReplanningRequest:
        """Persist a replan request with request/idempotency-key conflict checks."""
        ...

    def get_replan_request(self, request_id: str) -> LocalReplanningRequest | None:
        """Retrieve a replan request by ID."""
        ...

    def save_replan_result(self, result: LocalReplanningResponse) -> LocalReplanningResponse:
        """Persist a replan result with payload-hash idempotency."""
        ...

    def get_replan_result(self, request_id: str) -> LocalReplanningResponse | None:
        """Retrieve a replan result by request ID."""
        ...

    # ── Active TaskContract ─────────────────────────────────────────────

    def save_active_contract(
        self,
        contract: TaskContract,
        *,
        plan_id: str,
        robot_id: str,
        status: str = "ACTIVE",
        based_on_plan_version: int | None = None,
        correlation_id: str = "",
    ) -> ActiveTaskContractRecord:
        """Persist a contract version and make it active when status is ACTIVE."""
        ...

    def get_active_contract(self, task_id: str) -> ActiveTaskContractRecord | None:
        """Return the current active contract for a task."""
        ...

    def advance_active_contract_if_current(
        self,
        *,
        task_id: str,
        expected_plan_version: int,
        expected_command_seq: int,
        new_contract: TaskContract,
        plan_id: str,
        robot_id: str,
        based_on_plan_version: int,
        correlation_id: str = "",
    ) -> ActiveTaskContractRecord | None:
        """CAS update active contract and retain historical versions."""
        ...

    def list_contract_versions(self, task_id: str) -> list[ActiveTaskContractRecord]:
        """Return all contract versions for a task in ascending version order."""
        ...

    # ── Checkpoint ──────────────────────────────────────────────────────

    def save_execution_checkpoint(self, checkpoint: ExecutionCheckpoint) -> ExecutionCheckpoint:
        """Persist an execution checkpoint with payload-hash idempotency."""
        ...

    def get_latest_execution_checkpoint(self, task_id: str) -> ExecutionCheckpoint | None:
        """Return the newest checkpoint for a task."""
        ...

    def get_checkpoint(self, checkpoint_id: str) -> ExecutionCheckpoint | None:
        """Return a checkpoint by ID."""
        ...

    def compare_and_set_checkpoint(
        self,
        *,
        checkpoint_id: str,
        expected_checkpoint_hash: str,
        new_checkpoint: ExecutionCheckpoint,
    ) -> bool:
        """CAS checkpoint update by hash."""
        ...

    # ── Replan apply and ACK ────────────────────────────────────────────

    def save_replan_apply_record(self, record: ReplanApplyRecord) -> ReplanApplyRecord:
        """Persist a replan apply record with payload-hash idempotency."""
        ...

    def get_replan_apply_record(self, apply_id: str) -> ReplanApplyRecord | None:
        """Return a replan apply record by ID."""
        ...

    def get_replan_apply_record_for_request(self, request_id: str) -> ReplanApplyRecord | None:
        """Return the apply record for a replanning request."""
        ...

    def save_command_ack(self, ack: CommandAck) -> CommandAck:
        """Persist a command ACK with payload-hash idempotency."""
        ...

    def get_command_ack(self, request_id: str) -> CommandAck | None:
        """Return the latest ACK associated with a replan request."""
        ...

    # ── Outbox ──────────────────────────────────────────────────────────

    def enqueue_outbox(self, message: PendingMessage) -> PendingMessage:
        """Persist a message before attempting to send."""
        ...

    def claim_outbox_message(self) -> PendingMessage | None:
        """Atomically claim the next PENDING/RETRY_WAIT message."""
        ...

    def mark_outbox_sent(self, message_id: str) -> bool:
        """Mark a message as successfully sent. Transition: SENDING -> SENT."""
        ...

    def mark_outbox_failed(self, message_id: str, error: str) -> bool:
        """Handle a send failure and move to RETRY_WAIT or DEAD_LETTER."""
        ...

    def list_pending_outbox(self, task_id: str | None = None) -> list[PendingMessage]:
        """List PENDING/RETRY_WAIT messages, optionally filtered by task_id."""
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
        """CAS version bump for compatibility with Phase 6.1 checks."""
        ...

    # ── Audit ───────────────────────────────────────────────────────────

    def record_audit_event(self, task_id: str, event_type: str, details: dict[str, object]) -> None:
        """Record an immutable audit event for traceability."""
        ...

    # ── Lifecycle ───────────────────────────────────────────────────────

    def close(self) -> None:
        """Release database connections and other resources."""
        ...
