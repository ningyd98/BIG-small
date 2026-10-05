"""AUTO 模式事务服务，将幂等准备和模式版本提交交给同一仓储。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from cloud_edge_robot_arm.auto_mode.models import (
    AutoModeState,
    AutoModeTransitionRecord,
    AutoModeTransitionRequest,
    ModeSwitchPolicySnapshot,
    ModeTransitionCheckpoint,
)
from cloud_edge_robot_arm.auto_mode.repository import AutoModeRepository, InMemoryAutoModeRepository
from cloud_edge_robot_arm.contracts import AutoModeTransitionStatus, ControlMode


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ModeTransitionService:
    """保留prepare/commit/abort API，研究提交额外要求真实边界证明。"""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        repository: AutoModeRepository | None = None,
        commit_guard: Callable[[AutoModeTransitionRecord], ModeTransitionCheckpoint | None]
        | None = None,
        require_verified_boundary: bool = False,
        mode_switch_policy: ModeSwitchPolicySnapshot | None = None,
    ) -> None:
        self._clock = clock or _utc_now
        self._legacy_local = repository is None and not require_verified_boundary
        self._repository = (
            repository if repository is not None else InMemoryAutoModeRepository(clock=self._clock)
        )
        self._commit_guard = commit_guard
        self._require_verified_boundary = require_verified_boundary
        self._mode_switch_policy = (
            ModeSwitchPolicySnapshot.model_validate(mode_switch_policy.model_dump())
            if mode_switch_policy is not None
            else None
        )

    def prepare(self, request: AutoModeTransitionRequest) -> AutoModeTransitionRecord:
        """幂等准备请求，重启后仍从仓储返回原来的prepared或terminal记录。"""
        if self._legacy_local and self._repository.get_status(request.task_id) is None:
            # Historical standalone callers own no persistent or physical mode state.
            # External repositories and research services never infer current state.
            self._repository.save_status(
                AutoModeState(
                    task_id=request.task_id,
                    current_mode=request.from_mode,
                    mode_version=request.expected_mode_version,
                    updated_at=self._clock(),
                )
            )
        canonical = json.dumps(
            request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        record = AutoModeTransitionRecord(
            transition_id=f"transition-{uuid4().hex}",
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
            payload_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )
        return self._repository.prepare_transition(record)

    def commit(self, transition_id: str) -> AutoModeTransitionRecord:
        """提交时重新读取原子边界，并在仓储写事务内比较模式版本。"""
        record = self._repository.get_transition(transition_id)
        if record is None:
            raise KeyError(transition_id)
        if record.status == AutoModeTransitionStatus.COMMITTED:
            return record
        if self._require_verified_boundary and self._commit_guard is None:
            raise ValueError("research mode commit requires a current boundary guard")
        callback = self._commit_guard
        guard = (lambda: callback(record)) if callback is not None else None
        return self._repository.commit_transition_if_current(
            transition_id,
            committed_at=self._clock(),
            require_verified_boundary=self._require_verified_boundary,
            mode_policy=self._mode_switch_policy,
            commit_guard=guard,
        )

    def abort(self, transition_id: str, *, reason: str) -> AutoModeTransitionRecord:
        """中止prepared事务；缺失时保留历史可审计占位语义。"""
        if self._repository.get_transition(transition_id) is None:
            now = self._clock()
            return AutoModeTransitionRecord(
                transition_id=transition_id,
                task_id="unknown",
                from_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
                to_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
                status=AutoModeTransitionStatus.ABORTED,
                expected_mode_version=0,
                new_mode_version=0,
                idempotency_key=f"missing-{transition_id}",
                prepared_at=now,
                aborted_at=now,
                reason=reason,
            )
        return self._repository.abort_transition(
            transition_id, reason=reason, aborted_at=self._clock()
        )
