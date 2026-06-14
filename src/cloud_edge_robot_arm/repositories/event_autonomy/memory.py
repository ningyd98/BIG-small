"""In-memory EventAutonomyRepository — thread-safe, test/CI only."""

from __future__ import annotations

import hashlib
import json
import threading
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from cloud_edge_robot_arm.contracts.models import (
    ActiveContractStatus,
    ActiveTaskContractRecord,
    CommandAck,
    CompletionSummary,
    EdgeEvent,
    ExecutionCheckpoint,
    FailureSummary,
    LocalReplanningRequest,
    LocalReplanningResponse,
    MessageStatus,
    PendingMessage,
    RecoveryBudget,
    ReplanApplyRecord,
    TaskContract,
)
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
    IdempotencyConflictError,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _canonical_hash(value: Any) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _contract_hash(contract: TaskContract) -> str:
    return _canonical_hash(contract)


def _checkpoint_hash(checkpoint: ExecutionCheckpoint) -> str:
    payload = checkpoint.model_dump(mode="json")
    payload["checkpoint_hash"] = ""
    return _canonical_hash(payload)


def _apply_hash(record: ReplanApplyRecord) -> str:
    payload = record.model_dump(mode="json")
    payload["apply_hash"] = ""
    return _canonical_hash(payload)


class InMemoryEventAutonomyRepository:
    """Thread-safe in-memory implementation for testing and CI."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, EdgeEvent] = {}
        self._event_hashes: dict[str, str] = {}
        self._events_by_task: dict[str, list[str]] = {}
        self._budgets: dict[str, RecoveryBudget] = {}
        self._states: dict[str, str] = {}
        self._transitions: dict[str, list[dict[str, object]]] = {}
        self._failure_summaries: dict[str, FailureSummary] = {}
        self._failure_hashes: dict[str, str] = {}
        self._completion_summaries: dict[str, CompletionSummary] = {}
        self._completion_hashes: dict[str, str] = {}
        self._replan_requests: dict[str, LocalReplanningRequest] = {}
        self._replan_request_hashes: dict[str, str] = {}
        self._replan_idempotency: dict[str, str] = {}
        self._replan_results: dict[str, LocalReplanningResponse] = {}
        self._replan_result_hashes: dict[str, str] = {}
        self._outbox: dict[str, PendingMessage] = {}
        self._outbox_hashes: dict[str, str] = {}
        self._outbox_idempotency: dict[str, str] = {}
        self._plan_versions: dict[str, tuple[int, int]] = {}
        self._active_contracts: dict[str, ActiveTaskContractRecord] = {}
        self._contract_versions: dict[str, list[ActiveTaskContractRecord]] = {}
        self._checkpoints: dict[str, ExecutionCheckpoint] = {}
        self._checkpoint_hashes: dict[str, str] = {}
        self._checkpoints_by_task: dict[str, list[str]] = {}
        self._apply_records: dict[str, ReplanApplyRecord] = {}
        self._apply_by_request: dict[str, str] = {}
        self._apply_hashes: dict[str, str] = {}
        self._acks_by_key: dict[str, CommandAck] = {}
        self._ack_hashes: dict[str, str] = {}
        self._audit: dict[str, list[dict[str, object]]] = {}

    # ── generic idempotency helpers ───────────────────────────────────────

    @staticmethod
    def _ensure_same_hash(entity: str, key: str, existing_hash: str, new_hash: str) -> None:
        if existing_hash != new_hash:
            raise IdempotencyConflictError(f"{entity} idempotency conflict for key {key!r}")

    # ── Events ──────────────────────────────────────────────────────────

    def save_event(self, event: EdgeEvent) -> EdgeEvent:
        with self._lock:
            payload_hash = _canonical_hash(event)
            existing = self._events.get(event.event_id)
            if existing is not None:
                self._ensure_same_hash(
                    "EdgeEvent", event.event_id, self._event_hashes[event.event_id], payload_hash
                )
                return existing
            saved = event.model_copy(update={"event_hash": event.event_hash or payload_hash})
            self._events[event.event_id] = saved
            self._event_hashes[event.event_id] = payload_hash
            self._events_by_task.setdefault(event.task_id, []).append(event.event_id)
            return saved

    def get_event(self, event_id: str) -> EdgeEvent | None:
        with self._lock:
            event = self._events.get(event_id)
            return None if event is None else event.model_copy(deep=True)

    def list_events(self, task_id: str) -> list[EdgeEvent]:
        with self._lock:
            ids = self._events_by_task.get(task_id, [])
            return [self._events[eid].model_copy(deep=True) for eid in ids if eid in self._events]

    def mark_event_handled(self, event_id: str, handled_at: datetime | None = None) -> bool:
        return event_id in self._events

    # ── Retry Budget ────────────────────────────────────────────────────

    def save_retry_budget(self, budget: RecoveryBudget) -> RecoveryBudget:
        with self._lock:
            snapshot = budget.model_copy(deep=True)
            self._budgets[budget.task_id] = snapshot
            return snapshot

    def get_retry_budget(self, task_id: str) -> RecoveryBudget | None:
        with self._lock:
            budget = self._budgets.get(task_id)
            return None if budget is None else budget.model_copy(deep=True)

    def consume_retry_if_available(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        expected_count: int,
        event_id: str = "",
    ) -> tuple[bool, RecoveryBudget | None]:
        with self._lock:
            budget = self._budgets.get(task_id)
            if budget is None:
                return False, None
            if budget.retry_count_used != expected_count:
                return False, budget.model_copy(deep=True)
            if budget.remaining_retries <= 0:
                return False, budget.model_copy(deep=True)
            if event_id and budget.event_retry_counts.get(event_id, 0) > 0:
                return False, budget.model_copy(deep=True)

            step_counts = dict(budget.step_retry_counts)
            skill_counts = dict(budget.skill_retry_counts)
            event_counts = dict(budget.event_retry_counts)
            step_count = step_counts.get(step_id, 0)
            skill_count = skill_counts.get(skill, 0)
            task_count = budget.task_retry_count
            effective_remaining = min(
                max(0, budget.task_total_retry_limit - task_count),
                max(0, budget.per_step_retry_limit - step_count),
                max(0, budget.per_skill_retry_limit - skill_count),
                budget.remaining_retries,
            )
            if effective_remaining <= 0:
                return False, budget.model_copy(deep=True)

            now = _utc_now()
            if step_id:
                step_counts[step_id] = step_count + 1
            if skill:
                skill_counts[skill] = skill_count + 1
            if event_id:
                event_counts[event_id] = 1
            updated = budget.model_copy(
                update={
                    "retry_count_used": budget.retry_count_used + 1,
                    "task_retry_count": budget.task_retry_count + 1,
                    "step_retry_counts": step_counts,
                    "skill_retry_counts": skill_counts,
                    "event_retry_counts": event_counts,
                    "remaining_retries": budget.remaining_retries - 1,
                    "updated_at": now,
                },
                deep=True,
            )
            self._budgets[task_id] = updated
            return True, updated.model_copy(deep=True)

    # ── State Machine ───────────────────────────────────────────────────

    def save_state(self, task_id: str, state: str, reason: str, event_id: str = "") -> None:
        with self._lock:
            self._states[task_id] = state

    def get_state(self, task_id: str) -> str | None:
        with self._lock:
            return self._states.get(task_id)

    def save_state_transition(
        self, task_id: str, from_state: str, to_state: str, reason: str, event_id: str = ""
    ) -> None:
        with self._lock:
            entry: dict[str, object] = {
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "event_id": event_id,
                "timestamp": _utc_now().isoformat(),
            }
            self._transitions.setdefault(task_id, []).append(entry)
            self._states[task_id] = to_state

    def list_state_transitions(self, task_id: str) -> list[dict[str, object]]:
        with self._lock:
            return deepcopy(self._transitions.get(task_id, []))

    # ── Failure Summary ─────────────────────────────────────────────────

    def save_failure_summary(self, summary: FailureSummary) -> FailureSummary:
        with self._lock:
            payload_hash = _canonical_hash(summary)
            existing = self._failure_summaries.get(summary.summary_id)
            if existing is not None:
                self._ensure_same_hash(
                    "FailureSummary",
                    summary.summary_id,
                    self._failure_hashes[summary.summary_id],
                    payload_hash,
                )
                return existing
            saved = summary.model_copy(
                update={"summary_hash": summary.summary_hash or payload_hash}
            )
            self._failure_summaries[summary.summary_id] = saved
            self._failure_hashes[summary.summary_id] = payload_hash
            return saved

    def get_failure_summary(self, summary_id: str) -> FailureSummary | None:
        with self._lock:
            summary = self._failure_summaries.get(summary_id)
            return None if summary is None else summary.model_copy(deep=True)

    # ── Completion Summary ──────────────────────────────────────────────

    def save_completion_summary(self, summary: CompletionSummary) -> CompletionSummary:
        with self._lock:
            payload_hash = _canonical_hash(summary)
            existing = self._completion_summaries.get(summary.summary_id)
            if existing is not None:
                if existing.summary_hash and existing.summary_hash == summary.summary_hash:
                    return existing
                self._ensure_same_hash(
                    "CompletionSummary",
                    summary.summary_id,
                    self._completion_hashes[summary.summary_id],
                    payload_hash,
                )
                return existing
            saved = summary.model_copy(
                update={"summary_hash": summary.summary_hash or payload_hash}
            )
            self._completion_summaries[summary.summary_id] = saved
            self._completion_hashes[summary.summary_id] = payload_hash
            return saved

    def get_completion_summary(self, summary_id: str) -> CompletionSummary | None:
        with self._lock:
            summary = self._completion_summaries.get(summary_id)
            return None if summary is None else summary.model_copy(deep=True)

    def get_completion_summary_for_task(self, task_id: str) -> CompletionSummary | None:
        with self._lock:
            matches = [s for s in self._completion_summaries.values() if s.task_id == task_id]
            return None if not matches else matches[-1].model_copy(deep=True)

    # ── Replan ──────────────────────────────────────────────────────────

    def save_replan_request(self, request: LocalReplanningRequest) -> LocalReplanningRequest:
        with self._lock:
            payload_hash = _canonical_hash(request)
            existing = self._replan_requests.get(request.request_id)
            if existing is not None:
                self._ensure_same_hash(
                    "LocalReplanningRequest",
                    request.request_id,
                    self._replan_request_hashes[request.request_id],
                    payload_hash,
                )
                return existing
            if request.idempotency_key:
                existing_id = self._replan_idempotency.get(request.idempotency_key)
                if existing_id is not None:
                    self._ensure_same_hash(
                        "LocalReplanningRequest",
                        request.idempotency_key,
                        self._replan_request_hashes[existing_id],
                        payload_hash,
                    )
                    return self._replan_requests[existing_id]
                self._replan_idempotency[request.idempotency_key] = request.request_id
            self._replan_requests[request.request_id] = request.model_copy(deep=True)
            self._replan_request_hashes[request.request_id] = payload_hash
            return self._replan_requests[request.request_id]

    def get_replan_request(self, request_id: str) -> LocalReplanningRequest | None:
        with self._lock:
            request = self._replan_requests.get(request_id)
            return None if request is None else request.model_copy(deep=True)

    def save_replan_result(self, result: LocalReplanningResponse) -> LocalReplanningResponse:
        with self._lock:
            payload_hash = _canonical_hash(result)
            existing = self._replan_results.get(result.request_id)
            if existing is not None:
                self._ensure_same_hash(
                    "LocalReplanningResponse",
                    result.request_id,
                    self._replan_result_hashes[result.request_id],
                    payload_hash,
                )
                return existing
            saved = result.model_copy(
                update={"response_hash": result.response_hash or payload_hash}
            )
            self._replan_results[result.request_id] = saved
            self._replan_result_hashes[result.request_id] = payload_hash
            return saved

    def get_replan_result(self, request_id: str) -> LocalReplanningResponse | None:
        with self._lock:
            result = self._replan_results.get(request_id)
            return None if result is None else result.model_copy(deep=True)

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
        with self._lock:
            h = _contract_hash(contract)
            existing = self._version_record(contract.task_id, contract.plan_version)
            if existing is not None:
                self._ensure_same_hash(
                    "ActiveTaskContract",
                    f"{contract.task_id}:{contract.plan_version}",
                    existing.contract_hash,
                    h,
                )
                if status == ActiveContractStatus.ACTIVE.value:
                    self._active_contracts[contract.task_id] = existing
                    self._plan_versions[contract.task_id] = (
                        contract.plan_version,
                        contract.command_seq,
                    )
                return existing.model_copy(deep=True)
            now = _utc_now()
            record = ActiveTaskContractRecord(
                task_id=contract.task_id,
                plan_id=plan_id,
                robot_id=robot_id,
                plan_version=contract.plan_version,
                command_seq=contract.command_seq,
                scene_version=contract.scene_version,
                contract=contract.model_copy(deep=True),
                status=status,
                based_on_plan_version=based_on_plan_version,
                created_at=now,
                activated_at=now,
                correlation_id=correlation_id,
                contract_hash=h,
            )
            if status == ActiveContractStatus.ACTIVE.value:
                current = self._active_contracts.get(contract.task_id)
                if current is not None and current.plan_version != record.plan_version:
                    superseded = current.model_copy(
                        update={
                            "status": ActiveContractStatus.SUPERSEDED.value,
                            "superseded_at": now,
                        },
                        deep=True,
                    )
                    self._replace_version_record(superseded)
                self._active_contracts[contract.task_id] = record
                self._plan_versions[contract.task_id] = (
                    contract.plan_version,
                    contract.command_seq,
                )
            self._contract_versions.setdefault(contract.task_id, []).append(record)
            return record.model_copy(deep=True)

    def get_active_contract(self, task_id: str) -> ActiveTaskContractRecord | None:
        with self._lock:
            record = self._active_contracts.get(task_id)
            return None if record is None else record.model_copy(deep=True)

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
        with self._lock:
            active = self._active_contracts.get(task_id)
            if active is None:
                return None
            if (
                active.plan_version != expected_plan_version
                or active.command_seq != expected_command_seq
            ):
                return None
            if new_contract.plan_version <= expected_plan_version:
                return None
            if new_contract.command_seq <= expected_command_seq:
                return None
            # Reuse save logic while holding the same lock by writing directly.
            now = _utc_now()
            superseded = active.model_copy(
                update={"status": ActiveContractStatus.SUPERSEDED.value, "superseded_at": now},
                deep=True,
            )
            self._replace_version_record(superseded)
            h = _contract_hash(new_contract)
            existing = self._version_record(task_id, new_contract.plan_version)
            if existing is not None:
                self._ensure_same_hash(
                    "ActiveTaskContract",
                    f"{task_id}:{new_contract.plan_version}",
                    existing.contract_hash,
                    h,
                )
                self._active_contracts[task_id] = existing
                return existing.model_copy(deep=True)
            record = ActiveTaskContractRecord(
                task_id=task_id,
                plan_id=plan_id,
                robot_id=robot_id,
                plan_version=new_contract.plan_version,
                command_seq=new_contract.command_seq,
                scene_version=new_contract.scene_version,
                contract=new_contract.model_copy(deep=True),
                status=ActiveContractStatus.ACTIVE.value,
                based_on_plan_version=based_on_plan_version,
                created_at=now,
                activated_at=now,
                correlation_id=correlation_id,
                contract_hash=h,
            )
            self._contract_versions.setdefault(task_id, []).append(record)
            self._active_contracts[task_id] = record
            self._plan_versions[task_id] = (new_contract.plan_version, new_contract.command_seq)
            return record.model_copy(deep=True)

    def list_contract_versions(self, task_id: str) -> list[ActiveTaskContractRecord]:
        with self._lock:
            return [r.model_copy(deep=True) for r in self._contract_versions.get(task_id, [])]

    def _version_record(self, task_id: str, plan_version: int) -> ActiveTaskContractRecord | None:
        for record in self._contract_versions.get(task_id, []):
            if record.plan_version == plan_version:
                return record
        return None

    def _replace_version_record(self, replacement: ActiveTaskContractRecord) -> None:
        versions = self._contract_versions.get(replacement.task_id, [])
        for idx, record in enumerate(versions):
            if record.plan_version == replacement.plan_version:
                versions[idx] = replacement
                return
        versions.append(replacement)
        self._contract_versions[replacement.task_id] = versions

    # ── Checkpoint ──────────────────────────────────────────────────────

    def save_execution_checkpoint(self, checkpoint: ExecutionCheckpoint) -> ExecutionCheckpoint:
        with self._lock:
            h = checkpoint.checkpoint_hash or _checkpoint_hash(checkpoint)
            saved = checkpoint.model_copy(
                update={"checkpoint_hash": h, "updated_at": checkpoint.updated_at}, deep=True
            )
            existing = self._checkpoints.get(saved.checkpoint_id)
            if existing is not None:
                self._ensure_same_hash(
                    "ExecutionCheckpoint",
                    saved.checkpoint_id,
                    self._checkpoint_hashes[saved.checkpoint_id],
                    h,
                )
                return existing.model_copy(deep=True)
            self._checkpoints[saved.checkpoint_id] = saved
            self._checkpoint_hashes[saved.checkpoint_id] = h
            self._checkpoints_by_task.setdefault(saved.task_id, []).append(saved.checkpoint_id)
            return saved.model_copy(deep=True)

    def get_latest_execution_checkpoint(self, task_id: str) -> ExecutionCheckpoint | None:
        with self._lock:
            ids = self._checkpoints_by_task.get(task_id, [])
            if not ids:
                return None
            checkpoint = self._checkpoints[ids[-1]]
            return checkpoint.model_copy(deep=True)

    def get_checkpoint(self, checkpoint_id: str) -> ExecutionCheckpoint | None:
        with self._lock:
            checkpoint = self._checkpoints.get(checkpoint_id)
            return None if checkpoint is None else checkpoint.model_copy(deep=True)

    def compare_and_set_checkpoint(
        self,
        *,
        checkpoint_id: str,
        expected_checkpoint_hash: str,
        new_checkpoint: ExecutionCheckpoint,
    ) -> bool:
        with self._lock:
            existing = self._checkpoints.get(checkpoint_id)
            if existing is None:
                return False
            if existing.checkpoint_hash != expected_checkpoint_hash:
                return False
            h = new_checkpoint.checkpoint_hash or _checkpoint_hash(new_checkpoint)
            saved = new_checkpoint.model_copy(update={"checkpoint_hash": h}, deep=True)
            self._checkpoints.pop(checkpoint_id, None)
            self._checkpoint_hashes.pop(checkpoint_id, None)
            self._checkpoints[saved.checkpoint_id] = saved
            self._checkpoint_hashes[saved.checkpoint_id] = h
            ids = self._checkpoints_by_task.setdefault(saved.task_id, [])
            if checkpoint_id in ids:
                ids[ids.index(checkpoint_id)] = saved.checkpoint_id
            elif saved.checkpoint_id not in ids:
                ids.append(saved.checkpoint_id)
            return True

    # ── Replan apply and ACK ────────────────────────────────────────────

    def save_replan_apply_record(self, record: ReplanApplyRecord) -> ReplanApplyRecord:
        with self._lock:
            h = record.apply_hash or _apply_hash(record)
            existing = self._apply_records.get(record.apply_id)
            if existing is not None:
                self._ensure_same_hash(
                    "ReplanApplyRecord", record.apply_id, self._apply_hashes[record.apply_id], h
                )
                return existing.model_copy(deep=True)
            existing_id = self._apply_by_request.get(record.request_id)
            if existing_id is not None:
                self._ensure_same_hash(
                    "ReplanApplyRecord", record.request_id, self._apply_hashes[existing_id], h
                )
                return self._apply_records[existing_id].model_copy(deep=True)
            saved = record.model_copy(update={"apply_hash": h}, deep=True)
            self._apply_records[saved.apply_id] = saved
            self._apply_by_request[saved.request_id] = saved.apply_id
            self._apply_hashes[saved.apply_id] = h
            return saved.model_copy(deep=True)

    def get_replan_apply_record(self, apply_id: str) -> ReplanApplyRecord | None:
        with self._lock:
            record = self._apply_records.get(apply_id)
            return None if record is None else record.model_copy(deep=True)

    def get_replan_apply_record_for_request(self, request_id: str) -> ReplanApplyRecord | None:
        with self._lock:
            apply_id = self._apply_by_request.get(request_id)
            if apply_id is None:
                return None
            return self._apply_records[apply_id].model_copy(deep=True)

    def save_command_ack(self, ack: CommandAck) -> CommandAck:
        with self._lock:
            key = ack.request_id or f"{ack.task_id}:{ack.plan_version}:{ack.command_seq}"
            h = _canonical_hash(ack)
            existing = self._acks_by_key.get(key)
            if existing is not None:
                self._ensure_same_hash("CommandAck", key, self._ack_hashes[key], h)
                return existing.model_copy(deep=True)
            saved = ack.model_copy(deep=True)
            self._acks_by_key[key] = saved
            self._ack_hashes[key] = h
            return saved.model_copy(deep=True)

    def get_command_ack(self, request_id: str) -> CommandAck | None:
        with self._lock:
            ack = self._acks_by_key.get(request_id)
            return None if ack is None else ack.model_copy(deep=True)

    # ── Outbox ──────────────────────────────────────────────────────────

    def enqueue_outbox(self, message: PendingMessage) -> PendingMessage:
        with self._lock:
            payload_hash = _canonical_hash(message)
            existing = self._outbox.get(message.message_id)
            if existing is not None:
                self._ensure_same_hash(
                    "PendingMessage",
                    message.message_id,
                    self._outbox_hashes[message.message_id],
                    payload_hash,
                )
                return existing.model_copy(deep=True)
            if message.idempotency_key:
                existing_id = self._outbox_idempotency.get(message.idempotency_key)
                if existing_id is not None:
                    self._ensure_same_hash(
                        "PendingMessage",
                        message.idempotency_key,
                        self._outbox_hashes[existing_id],
                        payload_hash,
                    )
                    return self._outbox[existing_id].model_copy(deep=True)
                self._outbox_idempotency[message.idempotency_key] = message.message_id
            self._outbox[message.message_id] = message.model_copy(deep=True)
            self._outbox_hashes[message.message_id] = payload_hash
            return self._outbox[message.message_id].model_copy(deep=True)

    def claim_outbox_message(self) -> PendingMessage | None:
        with self._lock:
            for msg in self._outbox.values():
                now = _utc_now()
                if msg.status not in {MessageStatus.PENDING, MessageStatus.RETRY_WAIT}:
                    continue
                if msg.next_retry_at is not None and msg.next_retry_at > now:
                    continue
                updated = msg.model_copy(update={"status": MessageStatus.SENDING}, deep=True)
                self._outbox[msg.message_id] = updated
                self._outbox_hashes[msg.message_id] = _canonical_hash(updated)
                return updated.model_copy(deep=True)
            return None

    def mark_outbox_sent(self, message_id: str) -> bool:
        with self._lock:
            msg = self._outbox.get(message_id)
            if msg is None:
                return False
            if msg.status == MessageStatus.SENT:
                return True
            if msg.status != MessageStatus.SENDING:
                return False
            updated = msg.model_copy(update={"status": MessageStatus.SENT}, deep=True)
            self._outbox[message_id] = updated
            self._outbox_hashes[message_id] = _canonical_hash(updated)
            return True

    def mark_outbox_failed(self, message_id: str, error: str) -> bool:
        with self._lock:
            msg = self._outbox.get(message_id)
            if msg is None:
                return False
            new_count = msg.retry_count + 1
            if new_count >= msg.max_retries:
                new_status = MessageStatus.DEAD_LETTER
                next_attempt = None
            else:
                new_status = MessageStatus.RETRY_WAIT
                backoff_ms = msg.backoff_base_ms * (2 ** (new_count - 1))
                next_attempt = _utc_now() + timedelta(milliseconds=backoff_ms)
            updated = msg.model_copy(
                update={
                    "status": new_status,
                    "retry_count": new_count,
                    "last_error": error,
                    "next_retry_at": next_attempt,
                },
                deep=True,
            )
            self._outbox[message_id] = updated
            self._outbox_hashes[message_id] = _canonical_hash(updated)
            return True

    def list_pending_outbox(self, task_id: str | None = None) -> list[PendingMessage]:
        with self._lock:
            result: list[PendingMessage] = []
            for msg in self._outbox.values():
                if msg.status not in {MessageStatus.PENDING, MessageStatus.RETRY_WAIT}:
                    continue
                if task_id is not None and msg.task_id != task_id:
                    continue
                result.append(msg.model_copy(deep=True))
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

    def record_audit_event(self, task_id: str, event_type: str, details: dict[str, object]) -> None:
        with self._lock:
            entry: dict[str, object] = {
                "event_type": event_type,
                "details": deepcopy(details),
                "created_at": _utc_now().isoformat(),
            }
            self._audit.setdefault(task_id, []).append(entry)

    # ── Lifecycle ───────────────────────────────────────────────────────

    def close(self) -> None:
        with self._lock:
            self._events.clear()
            self._event_hashes.clear()
            self._events_by_task.clear()
            self._budgets.clear()
            self._states.clear()
            self._transitions.clear()
            self._failure_summaries.clear()
            self._failure_hashes.clear()
            self._completion_summaries.clear()
            self._completion_hashes.clear()
            self._replan_requests.clear()
            self._replan_request_hashes.clear()
            self._replan_idempotency.clear()
            self._replan_results.clear()
            self._replan_result_hashes.clear()
            self._outbox.clear()
            self._outbox_hashes.clear()
            self._outbox_idempotency.clear()
            self._plan_versions.clear()
            self._active_contracts.clear()
            self._contract_versions.clear()
            self._checkpoints.clear()
            self._checkpoint_hashes.clear()
            self._checkpoints_by_task.clear()
            self._apply_records.clear()
            self._apply_by_request.clear()
            self._apply_hashes.clear()
            self._acks_by_key.clear()
            self._ack_hashes.clear()
            self._audit.clear()
