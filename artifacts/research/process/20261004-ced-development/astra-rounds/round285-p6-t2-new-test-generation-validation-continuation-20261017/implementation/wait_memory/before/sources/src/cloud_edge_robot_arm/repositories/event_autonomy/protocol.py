"""Isaac 通信协议模型，限制前端或服务只能发送受控仿真消息。

EventAutonomyRepository Protocol — persistence contract for Phase 6.

The repository is the durable source of truth for event-triggered autonomy.
Duplicate writes are idempotent only when the payload hash matches; otherwise
repositories raise a structured conflict instead of silently swallowing database
constraint errors.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from functools import wraps
import json
from typing import TYPE_CHECKING, Protocol, runtime_checkable

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

if TYPE_CHECKING:
    from cloud_edge_robot_arm.edge.evidence.models import EvidenceVerdict
    from cloud_edge_robot_arm.edge.recovery.lifecycle import (
        RecoveryAuthorizationEvidence,
        RecoveryAuthorizationResult,
        RecoveryRecord,
        RecoveryReservationEvidence,
        RecoveryTransitionEvidence,
        VerificationBudgetRecord,
    )
    from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudgetState
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
        VisualBootstrapDefinition,
        VisualBootstrapPromotionInput,
        VisualBootstrapRecord,
        VisualBootstrapTransitionInput,
        VisualBootstrapTransitionResult,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
        VisualOwnerPublicationRecord,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import (
        VisualSupervisionDefinition,
        VisualSupervisionRecord,
        VisualSupervisionTransitionInput,
        VisualSupervisionTransitionResult,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import (
        VisualVerificationRouteInput,
        VisualVerificationRouteRecord,
        VisualVerificationRouteWriteResult,
    )
    from cloud_edge_robot_arm.vision.owner_registration import (
        StepGroundingBinding,
        VisualOriginalPlan,
    )


class RepositoryConflictError(RuntimeError):
    """Base class for repository conflicts that must surface to callers."""


_LOCAL_WRITERS = frozenset("initialize_visual_bootstrap_if_absent transition_visual_bootstrap_if_current initialize_visual_owner_if_absent publish_visual_boundary_if_current route_visual_verification_if_current initialize_visual_supervision_if_absent transition_visual_supervision_if_current save_event mark_event_handled save_retry_budget initialize_retry_budget_if_absent consume_retry_if_available initialize_verification_budget_if_absent initialize_recovery_if_absent advance_recovery_if_current reserve_reobservation_if_current consume_retry_and_authorize_recovery_if_current save_state save_state_transition save_failure_summary save_completion_summary save_replan_request save_replan_result save_active_contract advance_active_contract_if_current save_execution_checkpoint compare_and_set_checkpoint save_replan_apply_record update_replan_apply_record_if_current save_command_ack enqueue_outbox claim_outbox_message mark_outbox_sent mark_outbox_failed advance_plan_version_if_current record_audit_event".split())
_LOCAL_READERS = frozenset("get_visual_bootstrap get_visual_original_plan get_visual_owner_publication get_visual_supervision_source_publication get_visual_supervision get_verification_budget get_retry_budget get_recovery get_event get_replan_request get_replan_apply_record get_state".split())
_LOCAL_MISSING = object()


def local_value(value):
    """Exact data serialization for operation binding, with no default=str."""
    from collections.abc import Mapping
    from cloud_edge_robot_arm.vision.local_temporal import _copy

    if callable(getattr(value, "to_payload", None)):
        return _copy(local_value(value.to_payload()))
    if callable(getattr(value, "model_dump", None)):
        return _copy(value.model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: local_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: local_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [local_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return _copy(value)


def local_get_unlocked(repository, category, key):
    """Caller owns the actual event lock. Returned JSON is always detached."""
    if hasattr(repository, "_conn"):
        row = repository._conn.execute(
            "SELECT value_json FROM visual_local_tasks_v1 WHERE category=? AND record_key=?",
            (category, key),
        ).fetchone()
        return None if row is None else json.loads(row["value_json"])
    stored = repository._local_tasks.get((category, key))
    return None if stored is None else json.loads(stored)


def local_put_unlocked(repository, category, key, value, task_id):
    from cloud_edge_robot_arm.vision.local_temporal import _canonical, _copy
    from cloud_edge_robot_arm.vision.worker_runtime import _local_scope_for

    _local_scope_for(repository, required=True)
    raw = _canonical(_copy(value))
    if hasattr(repository, "_conn"):
        repository._conn.execute(
            "INSERT INTO visual_local_tasks_v1 (category,record_key,task_id,value_json) VALUES (?,?,?,?) "
            "ON CONFLICT(category,record_key) DO UPDATE SET value_json=excluded.value_json",
            (category, key, task_id, raw),
        )
    else:
        repository._local_tasks[(category, key)] = raw


def local_receipt_unlocked(repository, receipt):
    from cloud_edge_robot_arm.vision.worker_runtime import _local_scope_for
    from cloud_edge_robot_arm.vision.local_temporal import _canonical, _copy

    _local_scope_for(repository, required=True)
    if hasattr(repository, "_conn"):
        keys = list(receipt)
        repository._conn.execute(
            "INSERT INTO visual_local_publications_v1 (" + ",".join(keys) + ") VALUES ("
            + ",".join("?" for _ in keys) + ") ON CONFLICT(operation_id) DO UPDATE SET "
            + ",".join(key + "=excluded." + key for key in keys if key != "operation_id"),
            tuple(receipt[key] for key in keys),
        )
        repository._conn.execute("COMMIT")
        repository._conn.execute("SELECT 1").fetchone()
    else:
        repository._local_publications[receipt["operation_id"]] = _canonical(_copy(receipt))


def local_receipt_read_unlocked(repository, operation_id):
    if hasattr(repository, "_conn"):
        row = repository._conn.execute("SELECT * FROM visual_local_publications_v1 WHERE operation_id=?",
                                       (operation_id,)).fetchone()
        return None if row is None else dict(row)
    raw = repository._local_publications.get(operation_id)
    return None if raw is None else json.loads(raw)


def _local_target(repository, name, args, kwargs):
    """Resolve the actual addressed record, including key-only mutation APIs."""
    values = list(args) + list(kwargs.values())
    for value in values:
        payload = value.to_payload() if callable(getattr(value, "to_payload", None)) else None
        if isinstance(payload, dict) and str(payload.get("schema_version", "")).endswith(".local.v1"):
            return True
        task = getattr(value, "task_id", None)
        if task and local_get_unlocked(repository, "binding", task) is not None:
            return True
        if isinstance(value, str) and local_get_unlocked(repository, "binding", value) is not None:
            return True
    key_sources = {
        "mark_event_handled": "event", "advance_recovery_if_current": "recovery",
        "reserve_reobservation_if_current": "recovery", "consume_retry_and_authorize_recovery_if_current": "recovery",
        "save_replan_result": "replan", "compare_and_set_checkpoint": "checkpoint",
        "update_replan_apply_record_if_current": "apply", "mark_outbox_sent": "outbox", "mark_outbox_failed": "outbox",
    }
    category = key_sources.get(name)
    if category is not None:
        for value in values:
            key = value if isinstance(value, str) else getattr(value, "request_id", None)
            if key and local_get_unlocked(repository, category, key) is not None:
                return True
    if name == "claim_outbox_message":
        if hasattr(repository, "_conn"):
            return repository._conn.execute("SELECT 1 FROM visual_local_tasks_v1 WHERE category='outbox' LIMIT 1").fetchone() is not None
        return any(category == "outbox" for category, _ in repository._local_tasks)
    return False


def _local_legacy_write_guard_unlocked(repository, name, args, kwargs) -> None:
    """Fence a public legacy writer while its actual storage lock is held."""
    if _local_target(repository, name, args, kwargs):
        raise ValueError("operational task mutation requires the registered private publication scope")


def local_event_repository(cls):
    """Close the complete public writer surface without replacing its real lock."""
    def wrap(name, original):
        @wraps(original)
        def dispatch(self, *args, **kwargs):
            from cloud_edge_robot_arm.vision.worker_runtime import _local_scope_for, _local_read_record

            scope = _local_scope_for(self)
            if scope is not None:
                if name in _LOCAL_WRITERS:
                    return scope.runtime._local_mutate(name, args, kwargs)
                result = _local_read_record(self, name, args, kwargs)
                if result is not _LOCAL_MISSING:
                    return result
                raise ValueError("private operational reader has no matching local source")
            lock = self._write_lock if hasattr(self, "_write_lock") else self._lock
            with lock:
                if name in _LOCAL_READERS:
                    result = _local_read_record(self, name, args, kwargs)
                    if result is not _LOCAL_MISSING:
                        return result
                elif _local_target(self, name, args, kwargs):
                    negative = (name == "save_state" and len(args) >= 2 and type(args[1]) is str
                                and args[1] == "CANCELLED" and not kwargs)
                    if not negative:
                        raise ValueError("operational task mutation requires the registered private publication scope")
                    if hasattr(self, "_conn"):
                        with self._conn:
                            self._conn.execute("BEGIN IMMEDIATE")
                            self._conn.execute("INSERT INTO visual_local_tasks_v1 VALUES ('state',?,?,?) "
                                               "ON CONFLICT(category,record_key) DO UPDATE SET value_json=excluded.value_json",
                                               (args[0], args[0], json.dumps("CANCELLED")))
                    else:
                        self._local_tasks[("state", args[0])] = json.dumps("CANCELLED")
                    return None
            return original(self, *args, **kwargs)
        return dispatch

    for name in sorted(_LOCAL_WRITERS | _LOCAL_READERS):
        original = getattr(cls, name, None)
        if original is not None:
            setattr(cls, name, wrap(name, original))
    return cls


class IdempotencyConflictError(RepositoryConflictError):
    """Raised when the same unique key is reused with different content."""


class VersionConflictError(RepositoryConflictError):
    """Raised when a compare-and-set version update fails."""


@runtime_checkable
class EventAutonomyRepository(Protocol):
    """Unified persistence contract for event-triggered edge autonomy."""

    def initialize_visual_supervision_if_absent(
        self, definition: VisualSupervisionDefinition
    ) -> VisualSupervisionRecord:
        """Persist fixed original periodic/wait limits; never refill existing costs."""
        ...

    def get_visual_supervision(self, task_id: str) -> VisualSupervisionRecord | None:
        """Detached source history, including lost pending costs; no replay authority."""
        ...

    def get_visual_supervision_source_publication(
        self, task_id: str
    ) -> VisualOwnerPublicationRecord | None:
        """Literal observer source only; does not extend grounding action freshness."""
        ...

    def transition_visual_supervision_if_current(
        self, *, request: VisualSupervisionTransitionInput
    ) -> VisualSupervisionTransitionResult | None:
        """Atomic local source claim only; no camera, provider, wait or action effect."""
        ...

    def initialize_visual_bootstrap_if_absent(
        self, definition: VisualBootstrapDefinition
    ) -> VisualBootstrapRecord:
        """Create one immutable job/run/episode source, never ordinary task pools."""
        ...

    def get_visual_bootstrap(self, bootstrap_id: str) -> VisualBootstrapRecord | None:
        """Detached source history; a pending claim never authorizes replay."""
        ...

    def transition_visual_bootstrap_if_current(
        self, *, request: VisualBootstrapTransitionInput
    ) -> VisualBootstrapTransitionResult | None:
        """Atomic BOOTSTRAP_SOURCE_ONLY transition; no external effects or adoption."""
        ...

    def initialize_visual_owner_if_absent(
        self,
        original: VisualOriginalPlan,
        checkpoint: ExecutionCheckpoint,
        verification_state: VerificationBudgetState,
        retry_budget: RecoveryBudget,
        *,
        bootstrap_promotion: VisualBootstrapPromotionInput | None = None,
    ) -> VisualOwnerPublicationRecord:
        """Atomically register a durable source only, preserving complete existing pools."""
        ...

    def get_visual_original_plan(
        self, task_id: str, plan_version: int
    ) -> VisualOriginalPlan | None: ...

    def get_visual_owner_publication(self, task_id: str) -> VisualOwnerPublicationRecord | None:
        """Coherent current durable source; stale/expired publications remain unavailable."""
        ...

    def publish_visual_boundary_if_current(
        self,
        *,
        task_id: str,
        owner_epoch: str,
        expected_owner_revision: int,
        expected_contract_hash: str,
        expected_checkpoint_hash: str,
        checkpoint: ExecutionCheckpoint,
        grounding: StepGroundingBinding | None,
        state_generation: int,
    ) -> VisualOwnerPublicationRecord | None:
        """CAS checkpoint/publication only, with no physical or mode authority."""
        ...

    def route_visual_verification_if_current(
        self,
        *,
        request: VisualVerificationRouteInput,
    ) -> VisualVerificationRouteWriteResult | None:
        """Atomic SOURCE_ROUTE_ONLY pool/publication routing; no effect authority."""
        ...

    def get_visual_verification_route(
        self,
        task_id: str,
        event_key: str,
    ) -> VisualVerificationRouteRecord | None:
        """Detached history only; duplicates never authorize another capture."""
        ...

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

    def initialize_retry_budget_if_absent(self, budget: RecoveryBudget) -> RecoveryBudget:
        """Atomically create the task pool once, preserving any existing complete budget."""
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

    def initialize_verification_budget_if_absent(
        self,
        task_id: str,
        state: VerificationBudgetState,
    ) -> VerificationBudgetRecord:
        """Create the task verification pool once without refilling allowances."""
        ...

    def get_verification_budget(self, task_id: str) -> VerificationBudgetRecord | None:
        """Return a detached durable task verification pool."""
        ...

    def initialize_recovery_if_absent(self, record: RecoveryRecord) -> RecoveryRecord:
        """Persist DETECTED only, preserving exact same-identity initialization."""
        ...

    def get_recovery(self, recovery_id: str) -> RecoveryRecord | None: ...

    def list_unresolved_recoveries(self, task_id: str) -> list[RecoveryRecord]:
        """Exclude only evidence-verified resolved records, not exhausted failures."""
        ...

    def list_recoveries(self, task_id: str) -> list[RecoveryRecord]:
        """All detached event-linked records, including evidence-resolved history."""
        ...

    def advance_recovery_if_current(
        self,
        record: RecoveryRecord,
        *,
        expected_state: str,
        expected_revision: int,
        expected_budget_revision: int,
        verified_transition: RecoveryTransitionEvidence,
    ) -> RecoveryRecord | None: ...

    def reserve_reobservation_if_current(
        self,
        *,
        recovery_id: str,
        expected_revision: int,
        expected_budget_revision: int,
        reservation: RecoveryReservationEvidence | None = None,
    ) -> RecoveryRecord | None:
        """Reserve a durable task allowance before the caller captures a new frame."""
        ...

    def consume_retry_and_authorize_recovery_if_current(
        self,
        *,
        recovery_id: str,
        expected_recovery_revision: int,
        expected_verification_budget_revision: int,
        expected_retry_count: int,
        step_id: str,
        skill: str,
        authorization: RecoveryAuthorizationEvidence,
    ) -> RecoveryAuthorizationResult:
        """Atomically authorize and consume the existing task retry authority once."""
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
        replan_record: ReplanApplyRecord | None = None,
        activation_guard: Callable[[ReplanApplyRecord, ExecutionCheckpoint, bool], EvidenceVerdict]
        | None = None,
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

    def update_replan_apply_record_if_current(
        self,
        record: ReplanApplyRecord,
        *,
        expected_status: str,
    ) -> ReplanApplyRecord | None:
        """CAS actual stage/resume/start evidence; activation uses active-contract CAS."""
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
