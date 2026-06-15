from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from cloud_edge_robot_arm.auto_mode.models import (
    AutoModeTransitionRecord,
    AutoModeTransitionRequest,
)
from cloud_edge_robot_arm.contracts import AutoModeTransitionStatus, ControlMode
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ModeTransitionService:
    def __init__(
        self, *, clock: Callable[[], datetime] | None = None, repository: object | None = None
    ) -> None:
        self._clock = clock or _utc_now
        self._repository = repository
        self._transitions: dict[str, AutoModeTransitionRecord] = {}
        self._by_idempotency: dict[str, str] = {}

    def prepare(self, request: AutoModeTransitionRequest) -> AutoModeTransitionRecord:
        if request.idempotency_key in self._by_idempotency:
            existing_id = self._by_idempotency[request.idempotency_key]
            existing = self._transitions[existing_id]
            if existing.payload_hash != self._payload_hash(request):
                raise IdempotencyConflictError("auto mode transition idempotency conflict")
            return existing
        transition_id = f"transition-{request.task_id}-{len(self._transitions) + 1}"
        record = AutoModeTransitionRecord(
            transition_id=transition_id,
            task_id=request.task_id,
            from_mode=request.from_mode,
            to_mode=request.to_mode,
            status=AutoModeTransitionStatus.PREPARED,
            expected_mode_version=request.expected_mode_version,
            new_mode_version=request.expected_mode_version + 1,
            idempotency_key=request.idempotency_key,
            decision_id=request.decision_id,
            prepared_at=self._clock(),
            reason=request.reason,
            payload_hash=self._payload_hash(request),
        )
        self._transitions[transition_id] = record
        self._by_idempotency[request.idempotency_key] = transition_id
        return record

    def commit(self, transition_id: str) -> AutoModeTransitionRecord:
        record = self._transitions[transition_id]
        updated = record.model_copy(
            update={"status": AutoModeTransitionStatus.COMMITTED, "committed_at": self._clock()},
            deep=True,
        )
        self._transitions[transition_id] = updated
        return updated

    def abort(self, transition_id: str, *, reason: str) -> AutoModeTransitionRecord:
        record = self._transitions.get(transition_id)
        if record is None:
            return AutoModeTransitionRecord(
                transition_id=transition_id,
                task_id="unknown",
                from_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
                to_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
                status=AutoModeTransitionStatus.ABORTED,
                expected_mode_version=0,
                new_mode_version=0,
                idempotency_key=f"missing-{transition_id}",
                prepared_at=self._clock(),
                aborted_at=self._clock(),
                reason=reason,
            )
        updated = record.model_copy(
            update={
                "status": AutoModeTransitionStatus.ABORTED,
                "aborted_at": self._clock(),
                "reason": reason,
            },
            deep=True,
        )
        self._transitions[transition_id] = updated
        return updated

    def _payload_hash(self, request: AutoModeTransitionRequest) -> str:
        import hashlib
        import json

        canonical = json.dumps(
            request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
