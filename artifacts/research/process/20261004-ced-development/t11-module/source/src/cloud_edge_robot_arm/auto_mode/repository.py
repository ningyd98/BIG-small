"""仓储接口或实现，隔离业务服务与底层存储细节。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from cloud_edge_robot_arm.auto_mode.models import ModeSwitchPolicySnapshot, ModeTransitionCheckpoint
from cloud_edge_robot_arm.contracts import (
    AutoModeDecision,
    AutoModeStatus,
    AutoModeTransition,
    AutoModeTransitionStatus,
    RiskSnapshot,
)
from cloud_edge_robot_arm.repositories.event_autonomy.protocol import IdempotencyConflictError


@runtime_checkable
class AutoModeRepository(Protocol):
    """AUTO 模式仓储协议，统一内存和 SQLite 实现的持久化边界。"""

    def save_risk_snapshot(self, snapshot: RiskSnapshot) -> RiskSnapshot:
        """保存风险快照并返回规范化后的快照。"""
        ...

    def latest_risk_snapshot(self, task_id: str) -> RiskSnapshot | None:
        """按任务查询最新风险快照，缺失时返回 None。"""
        ...

    def save_decision(self, decision: AutoModeDecision) -> AutoModeDecision:
        """保存 AUTO 决策记录并返回可审计副本。"""
        ...

    def latest_decision(self, task_id: str) -> AutoModeDecision | None:
        """按任务查询最新 AUTO 决策，缺失时返回 None。"""
        ...

    def save_transition(self, transition: AutoModeTransition) -> AutoModeTransition:
        """保存模式切换记录，并按幂等键拒绝冲突 payload。"""
        ...

    def get_transition(self, transition_id: str) -> AutoModeTransition | None:
        """按切换 ID 查询模式切换记录。"""
        ...

    def get_transition_by_idempotency(self, idempotency_key: str) -> AutoModeTransition | None:
        """按幂等键查询已准备的模式切换记录。"""
        ...

    def latest_prepared_transition(self, task_id: str) -> AutoModeTransition | None:
        """按任务查询最近一次 PREPARED 状态的切换记录。"""
        ...

    def save_status(self, status: AutoModeStatus) -> AutoModeStatus:
        """保存任务当前 AUTO 模式状态。"""
        ...

    def get_status(self, task_id: str) -> AutoModeStatus | None:
        """按任务查询当前 AUTO 模式状态。"""
        ...

    def prepare_transition(self, transition: AutoModeTransition) -> AutoModeTransition:
        """原子准备相同幂等事务。"""
        ...

    def save_transition_checkpoint(
        self, transition_id: str, checkpoint: ModeTransitionCheckpoint
    ) -> ModeTransitionCheckpoint:
        """持久化模式提交边界证明。"""
        ...

    def get_transition_checkpoint(self, transition_id: str) -> ModeTransitionCheckpoint | None:
        """读取模式提交边界证明。"""
        ...

    def commit_transition_if_current(
        self,
        transition_id: str,
        *,
        committed_at: datetime,
        boundary: ModeTransitionCheckpoint | None = None,
        require_verified_boundary: bool = False,
        mode_policy: ModeSwitchPolicySnapshot | None = None,
        commit_guard: Callable[[], ModeTransitionCheckpoint | None] | None = None,
    ) -> AutoModeTransition:
        """原子比较当前模式版本并提交。"""
        ...

    def abort_transition(
        self, transition_id: str, *, reason: str, aborted_at: datetime
    ) -> AutoModeTransition:
        """只中止prepared事务。"""
        ...

    def record_audit_event(
        self, task_id: str, event_type: str, details: dict[str, object] | None = None
    ) -> None:
        """记录模式决策审计事件，不保存敏感硬件凭据。"""
        ...

    def close(self) -> None:
        """释放仓储资源；内存实现可为空操作。"""
        ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InMemoryAutoModeRepository:
    """内存 AUTO 模式仓储，供单元测试和无数据库运行时使用。"""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or _utc_now
        self._lock = threading.RLock()
        self._checkpoints: dict[str, tuple[str, ModeTransitionCheckpoint]] = {}
        self._snapshots: dict[str, RiskSnapshot] = {}
        self._decisions: dict[str, AutoModeDecision] = {}
        self._transitions: dict[str, AutoModeTransition] = {}
        self._transition_idempotency: dict[str, str] = {}
        self._statuses: dict[str, AutoModeStatus] = {}
        self._hashes: dict[str, str] = {}
        self._audit: list[dict[str, object]] = []

    def save_risk_snapshot(self, snapshot: RiskSnapshot) -> RiskSnapshot:
        """保存风险快照的深拷贝，避免调用方后续修改污染仓储。"""
        self._snapshots[snapshot.snapshot_id] = snapshot.model_copy(deep=True)
        self._hashes[f"risk:{snapshot.snapshot_id}"] = _hash(snapshot)
        return snapshot

    def latest_risk_snapshot(self, task_id: str) -> RiskSnapshot | None:
        """返回任务最新风险快照的深拷贝，缺失时返回 None。"""
        matches = [s for s in self._snapshots.values() if s.task_id == task_id]
        if not matches:
            return None
        return sorted(matches, key=lambda s: s.created_at)[-1].model_copy(deep=True)

    def save_decision(self, decision: AutoModeDecision) -> AutoModeDecision:
        """保存 AUTO 决策并记录 payload hash 便于审计。"""
        self._decisions[decision.decision_id] = decision.model_copy(deep=True)
        self._hashes[f"decision:{decision.decision_id}"] = _hash(decision)
        return decision

    def latest_decision(self, task_id: str) -> AutoModeDecision | None:
        """返回任务最新 AUTO 决策的深拷贝。"""
        matches = [d for d in self._decisions.values() if d.task_id == task_id]
        if not matches:
            return None
        return sorted(matches, key=lambda d: d.created_at)[-1].model_copy(deep=True)

    def save_transition(self, transition: AutoModeTransition) -> AutoModeTransition:
        """保存模式切换记录，并在幂等键冲突时抛出显式错误。"""
        with self._lock:
            existing_id = self._transition_idempotency.get(transition.idempotency_key)
            existing = self._transitions.get(existing_id) if existing_id is not None else None
            _validate_transition_save(existing, transition)
            existing = self._transitions.get(transition.transition_id)
            _validate_transition_save(existing, transition)
            self._transitions[transition.transition_id] = transition.model_copy(deep=True)
            self._transition_idempotency[transition.idempotency_key] = transition.transition_id
            return transition.model_copy(deep=True)

    def get_transition(self, transition_id: str) -> AutoModeTransition | None:
        """按 transition_id 返回模式切换记录的深拷贝。"""
        transition = self._transitions.get(transition_id)
        return None if transition is None else transition.model_copy(deep=True)

    def get_transition_by_idempotency(self, idempotency_key: str) -> AutoModeTransition | None:
        """按幂等键返回此前准备的模式切换记录。"""
        transition_id = self._transition_idempotency.get(idempotency_key)
        return None if transition_id is None else self.get_transition(transition_id)

    def latest_prepared_transition(self, task_id: str) -> AutoModeTransition | None:
        """返回任务最近一次 PREPARED 切换，供恢复流程继续提交或回滚。"""
        matches = [
            transition
            for transition in self._transitions.values()
            if transition.task_id == task_id and transition.status.value == "PREPARED"
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda transition: transition.prepared_at)[-1].model_copy(
            deep=True
        )

    def save_status(self, status: AutoModeStatus) -> AutoModeStatus:
        """保存任务 AUTO 模式状态的深拷贝。"""
        with self._lock:
            self._statuses[status.task_id] = status.model_copy(deep=True)
            return status.model_copy(deep=True)

    def get_status(self, task_id: str) -> AutoModeStatus | None:
        """按任务读取当前 AUTO 模式状态。"""
        status = self._statuses.get(task_id)
        return None if status is None else status.model_copy(deep=True)

    def record_audit_event(
        self, task_id: str, event_type: str, details: dict[str, object] | None = None
    ) -> None:
        """追加内存审计事件，用于测试决策链路而不触碰真实硬件。"""
        self._audit.append(
            {
                "task_id": task_id,
                "event_type": event_type,
                "details": dict(details or {}),
                "created_at": self._clock().isoformat(),
            }
        )

    def close(self) -> None:
        """内存仓储没有外部连接，关闭操作保持幂等空实现。"""
        return None

    def prepare_transition(self, transition: AutoModeTransition) -> AutoModeTransition:
        """原子准备或返回相同幂等请求，不复用冲突的请求内容。"""
        with self._lock:
            existing = self.get_transition_by_idempotency(transition.idempotency_key)
            if existing is not None:
                if existing.payload_hash != transition.payload_hash:
                    raise IdempotencyConflictError("mode transition idempotency conflict")
                return existing
            return self.save_transition(transition)

    def save_transition_checkpoint(
        self, transition_id: str, checkpoint: ModeTransitionCheckpoint
    ) -> ModeTransitionCheckpoint:
        """保存绑定prepared请求hash的checkpoint，不允许在旧版本上换绑。"""
        checkpoint = ModeTransitionCheckpoint.model_validate(checkpoint.model_dump())
        with self._lock:
            record = self.get_transition(transition_id)
            _validate_checkpoint(record, checkpoint)
            assert record is not None
            self._checkpoints[transition_id] = (
                record.payload_hash,
                checkpoint.model_copy(deep=True),
            )
            return checkpoint.model_copy(deep=True)

    def get_transition_checkpoint(self, transition_id: str) -> ModeTransitionCheckpoint | None:
        """读取绑定当前请求hash的持久化checkpoint证明。"""
        with self._lock:
            pair = self._checkpoints.get(transition_id)
            record = self.get_transition(transition_id)
            if pair is None or record is None or pair[0] != record.payload_hash:
                return None
            return pair[1].model_copy(deep=True)

    def commit_transition_if_current(
        self,
        transition_id: str,
        *,
        committed_at: datetime,
        boundary: ModeTransitionCheckpoint | None = None,
        require_verified_boundary: bool = False,
        mode_policy: ModeSwitchPolicySnapshot | None = None,
        commit_guard: Callable[[], ModeTransitionCheckpoint | None] | None = None,
    ) -> AutoModeTransition:
        """同一临界区内比较当前模式版本并同时提交状态和事务。"""
        with self._lock:
            record = self.get_transition(transition_id)
            if record is None:
                raise ValueError("mode transition does not exist")
            if record.status == AutoModeTransitionStatus.COMMITTED:
                return record
            current = self.get_status(record.task_id)
            _validate_commit(
                record,
                current,
                committed_at,
                boundary,
                self.get_transition_checkpoint(transition_id),
                require_verified_boundary,
                mode_policy,
                commit_guard,
            )
            assert current is not None
            updated, status = _committed_values(record, current, committed_at)
            self._transitions[transition_id] = updated.model_copy(deep=True)
            self._statuses[record.task_id] = status.model_copy(deep=True)
            return updated

    def abort_transition(
        self, transition_id: str, *, reason: str, aborted_at: datetime
    ) -> AutoModeTransition:
        """只允许prepared事务中止；重复中止返回最初结果。"""
        with self._lock:
            record = self.get_transition(transition_id)
            if record is None:
                raise KeyError(transition_id)
            if record.status == AutoModeTransitionStatus.COMMITTED:
                raise ValueError("COMMITTED transition cannot be aborted")
            if record.status != AutoModeTransitionStatus.PREPARED:
                return record
            updated = record.model_copy(
                update={
                    "status": AutoModeTransitionStatus.ABORTED,
                    "aborted_at": aborted_at,
                    "reason": reason,
                },
                deep=True,
            )
            self._transitions[transition_id] = updated
            return updated.model_copy(deep=True)


class SQLiteAutoModeRepository:
    """SQLite AUTO 模式仓储，将审计记录和状态快照落盘保存。"""

    def __init__(self, path: str | Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or _utc_now
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()
        self._memory = InMemoryAutoModeRepository(clock=self._clock)
        self._load()

    def save_risk_snapshot(self, snapshot: RiskSnapshot) -> RiskSnapshot:
        """保存风险快照到内存镜像和 SQLite 表。"""
        saved = self._memory.save_risk_snapshot(snapshot)
        self._upsert("risk_snapshots", "snapshot_id", snapshot.snapshot_id, snapshot.task_id, saved)
        return saved

    def latest_risk_snapshot(self, task_id: str) -> RiskSnapshot | None:
        """从内存镜像读取任务最新风险快照。"""
        return self._memory.latest_risk_snapshot(task_id)

    def save_decision(self, decision: AutoModeDecision) -> AutoModeDecision:
        """保存 AUTO 决策到内存镜像和 SQLite 表。"""
        saved = self._memory.save_decision(decision)
        self._upsert(
            "auto_mode_decisions", "decision_id", decision.decision_id, decision.task_id, saved
        )
        return saved

    def latest_decision(self, task_id: str) -> AutoModeDecision | None:
        """从内存镜像读取任务最新 AUTO 决策。"""
        return self._memory.latest_decision(task_id)

    def save_transition(self, transition: AutoModeTransition) -> AutoModeTransition:
        """保存模式切换记录，并保持幂等冲突检查与 SQLite 落盘一致。"""
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            _validate_transition_save(
                self.get_transition_by_idempotency(transition.idempotency_key), transition
            )
            _validate_transition_save(self.get_transition(transition.transition_id), transition)
            self._upsert_transition(transition, commit=False)
            return transition.model_copy(deep=True)

    def get_transition(self, transition_id: str) -> AutoModeTransition | None:
        """按 transition_id 读取模式切换记录。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM mode_transitions WHERE transition_id=?", (transition_id,)
            ).fetchone()
            return (
                None if row is None else AutoModeTransition.model_validate_json(row["payload_json"])
            )

    def get_transition_by_idempotency(self, idempotency_key: str) -> AutoModeTransition | None:
        """按幂等键读取模式切换记录。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM mode_transitions WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            return (
                None if row is None else AutoModeTransition.model_validate_json(row["payload_json"])
            )

    def latest_prepared_transition(self, task_id: str) -> AutoModeTransition | None:
        """读取任务最近一次 PREPARED 切换，用于恢复未完成切换。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT payload_json FROM mode_transitions WHERE task_id=? "
                "ORDER BY created_at DESC",
                (task_id,),
            )
            for row in rows:
                record = AutoModeTransition.model_validate_json(row["payload_json"])
                if record.status == AutoModeTransitionStatus.PREPARED:
                    return record
            return None

    def save_status(self, status: AutoModeStatus) -> AutoModeStatus:
        """保存当前 AUTO 模式状态到内存镜像和 SQLite 表。"""
        with self._lock:
            self._upsert("auto_mode_statuses", "task_id", status.task_id, status.task_id, status)
            return status.model_copy(deep=True)

    def get_status(self, task_id: str) -> AutoModeStatus | None:
        """按任务读取当前 AUTO 模式状态。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM auto_mode_statuses WHERE task_id=?", (task_id,)
            ).fetchone()
            return None if row is None else AutoModeStatus.model_validate_json(row["payload_json"])

    def record_audit_event(
        self, task_id: str, event_type: str, details: dict[str, object] | None = None
    ) -> None:
        """记录 AUTO 模式审计事件，details 只保存结构化业务字段。"""
        self._memory.record_audit_event(task_id, event_type, details)
        self._conn.execute(
            """
            INSERT INTO auto_mode_audit_events(task_id, event_type, details_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                task_id,
                event_type,
                json.dumps(details or {}, sort_keys=True),
                self._clock().isoformat(),
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        """关闭 SQLite 连接，避免测试和服务退出时泄漏句柄。"""
        self._conn.close()

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS risk_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auto_mode_decisions (
                decision_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mode_transitions (
                transition_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auto_mode_statuses (
                task_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mode_transition_checkpoints (
                transition_id TEXT PRIMARY KEY,
                payload_hash TEXT NOT NULL,
                checkpoint_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auto_mode_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def _load(self) -> None:
        for row in self._conn.execute(
            "SELECT payload_json FROM risk_snapshots ORDER BY created_at"
        ):
            self._memory.save_risk_snapshot(RiskSnapshot.model_validate_json(row["payload_json"]))
        for row in self._conn.execute(
            "SELECT payload_json FROM auto_mode_decisions ORDER BY created_at"
        ):
            self._memory.save_decision(AutoModeDecision.model_validate_json(row["payload_json"]))
        for row in self._conn.execute(
            "SELECT payload_json FROM mode_transitions ORDER BY created_at"
        ):
            record = AutoModeTransition.model_validate_json(row["payload_json"])
            self._memory._transitions[record.transition_id] = record
            self._memory._transition_idempotency[record.idempotency_key] = record.transition_id
        for row in self._conn.execute(
            "SELECT payload_json FROM auto_mode_statuses ORDER BY updated_at"
        ):
            self._memory.save_status(AutoModeStatus.model_validate_json(row["payload_json"]))

    def _upsert(
        self,
        table: str,
        key_name: str,
        key_value: str,
        task_id: str,
        payload: BaseModel,
        *,
        commit: bool = True,
    ) -> None:
        payload_json = payload.model_dump_json()
        payload_hash = _hash(payload)
        now = self._clock().isoformat()
        if table == "auto_mode_statuses":
            self._conn.execute(
                """
                INSERT INTO auto_mode_statuses(task_id, payload_json, payload_hash, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    payload_hash = excluded.payload_hash,
                    updated_at = excluded.updated_at
                """,
                (key_value, payload_json, payload_hash, now),
            )
        else:
            self._conn.execute(
                f"""
                INSERT INTO {table}({key_name}, task_id, payload_json, payload_hash, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT({key_name}) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    payload_hash = excluded.payload_hash
                """,
                (key_value, task_id, payload_json, payload_hash, now),
            )
        if commit:
            self._conn.commit()

    def _upsert_transition(self, transition: AutoModeTransition, *, commit: bool = True) -> None:
        payload_json = transition.model_dump_json()
        payload_hash = _hash(transition)
        now = self._clock().isoformat()
        self._conn.execute(
            """
            INSERT INTO mode_transitions(
                transition_id,
                task_id,
                idempotency_key,
                payload_json,
                payload_hash,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(transition_id) DO UPDATE SET
                task_id = excluded.task_id,
                idempotency_key = excluded.idempotency_key,
                payload_json = excluded.payload_json,
                payload_hash = excluded.payload_hash
            """,
            (
                transition.transition_id,
                transition.task_id,
                transition.idempotency_key,
                payload_json,
                payload_hash,
                now,
            ),
        )
        if commit:
            self._conn.commit()

    def prepare_transition(self, transition: AutoModeTransition) -> AutoModeTransition:
        """SQLite写事务内准备幂等请求，跨连接不会创建重复事务。"""
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            existing = self.get_transition_by_idempotency(transition.idempotency_key)
            if existing is not None:
                if existing.payload_hash != transition.payload_hash:
                    raise IdempotencyConflictError("mode transition idempotency conflict")
                return existing
            self._upsert_transition(transition, commit=False)
            return transition.model_copy(deep=True)

    def save_transition_checkpoint(
        self, transition_id: str, checkpoint: ModeTransitionCheckpoint
    ) -> ModeTransitionCheckpoint:
        """将checkpoint与prepared payload hash原子绑定并保存到SQLite。"""
        checkpoint = ModeTransitionCheckpoint.model_validate(checkpoint.model_dump())
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            record = self.get_transition(transition_id)
            _validate_checkpoint(record, checkpoint)
            assert record is not None
            self._conn.execute(
                """INSERT INTO mode_transition_checkpoints(
                transition_id, payload_hash, checkpoint_json) VALUES (?, ?, ?)
                ON CONFLICT(transition_id) DO UPDATE SET
                payload_hash=excluded.payload_hash, checkpoint_json=excluded.checkpoint_json""",
                (transition_id, record.payload_hash, checkpoint.model_dump_json()),
            )
            return checkpoint.model_copy(deep=True)

    def get_transition_checkpoint(self, transition_id: str) -> ModeTransitionCheckpoint | None:
        """直接读取SQLite中的checkpoint，拒绝换绑或过期请求hash。"""
        with self._lock:
            row = self._conn.execute(
                """SELECT c.payload_hash, c.checkpoint_json,
                t.payload_json FROM mode_transition_checkpoints c JOIN mode_transitions t
                ON c.transition_id=t.transition_id WHERE c.transition_id=?""",
                (transition_id,),
            ).fetchone()
            if row is None:
                return None
            record = AutoModeTransition.model_validate_json(row["payload_json"])
            if record.payload_hash != row["payload_hash"]:
                return None
            return ModeTransitionCheckpoint.model_validate_json(row["checkpoint_json"])

    def commit_transition_if_current(
        self,
        transition_id: str,
        *,
        committed_at: datetime,
        boundary: ModeTransitionCheckpoint | None = None,
        require_verified_boundary: bool = False,
        mode_policy: ModeSwitchPolicySnapshot | None = None,
        commit_guard: Callable[[], ModeTransitionCheckpoint | None] | None = None,
    ) -> AutoModeTransition:
        """BEGIN IMMEDIATE内比较当前版本并同时更新状态和提交记录。"""
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            record = self.get_transition(transition_id)
            if record is None:
                raise ValueError("mode transition does not exist")
            if record.status == AutoModeTransitionStatus.COMMITTED:
                return record
            current = self.get_status(record.task_id)
            _validate_commit(
                record,
                current,
                committed_at,
                boundary,
                self.get_transition_checkpoint(transition_id),
                require_verified_boundary,
                mode_policy,
                commit_guard,
            )
            assert current is not None
            updated, status = _committed_values(record, current, committed_at)
            self._upsert_transition(updated, commit=False)
            self._upsert(
                "auto_mode_statuses",
                "task_id",
                record.task_id,
                record.task_id,
                status,
                commit=False,
            )
            return updated

    def abort_transition(
        self, transition_id: str, *, reason: str, aborted_at: datetime
    ) -> AutoModeTransition:
        """写事务内中止prepared记录；已提交记录不可改写。"""
        with self._lock, self._conn:
            self._conn.execute("BEGIN IMMEDIATE")
            record = self.get_transition(transition_id)
            if record is None:
                raise KeyError(transition_id)
            if record.status == AutoModeTransitionStatus.COMMITTED:
                raise ValueError("COMMITTED transition cannot be aborted")
            if record.status != AutoModeTransitionStatus.PREPARED:
                return record
            updated = record.model_copy(
                update={
                    "status": AutoModeTransitionStatus.ABORTED,
                    "aborted_at": aborted_at,
                    "reason": reason,
                },
                deep=True,
            )
            self._upsert_transition(updated, commit=False)
            return updated


def _hash(value: BaseModel) -> str:
    canonical = json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_checkpoint(
    record: AutoModeTransition | None, checkpoint: ModeTransitionCheckpoint
) -> None:
    if record is None or record.status != AutoModeTransitionStatus.PREPARED:
        raise ValueError("checkpoint requires a prepared transition")
    if (
        checkpoint.task_id != record.task_id
        or checkpoint.mode_version != record.expected_mode_version
    ):
        raise ValueError("checkpoint identity/version mismatch")


def _validate_commit(
    record: AutoModeTransition,
    current: AutoModeStatus | None,
    now: datetime,
    boundary: ModeTransitionCheckpoint | None,
    stored: ModeTransitionCheckpoint | None,
    require_boundary: bool,
    mode_policy: ModeSwitchPolicySnapshot | None,
    commit_guard: Callable[[], ModeTransitionCheckpoint | None] | None,
) -> None:
    if record.status != AutoModeTransitionStatus.PREPARED:
        raise ValueError(f"only prepared transitions can commit: {record.status}")
    if current is None:
        raise ValueError("current mode state is missing")
    if (
        current.current_mode != record.from_mode
        or current.mode_version != record.expected_mode_version
    ):
        raise ValueError("current mode/version changed before commit")
    if record.new_mode_version != record.expected_mode_version + 1:
        raise ValueError("new mode version must advance exactly once")
    if now.tzinfo is None or now.utcoffset() is None or now < record.prepared_at:
        raise ValueError("commit time must be aware and after preparation")
    if require_boundary:
        from cloud_edge_robot_arm.auto_mode.baseline_policies import verify_mode_switch_policy

        if mode_policy is None or not verify_mode_switch_policy(mode_policy)["accepted"]:
            raise ValueError("research mode commit requires verified selection policy evidence")
        if commit_guard is None:
            raise ValueError("verified current boundary guard is required")
    if commit_guard is not None:
        boundary = commit_guard()
    if require_boundary and (boundary is None or stored is None):
        raise ValueError("verified boundary guard and durable checkpoint are required")
    if boundary is not None:
        boundary = ModeTransitionCheckpoint.model_validate(boundary.model_dump())
        _validate_checkpoint(record, boundary)
        if boundary.atomic_action_active:
            raise ValueError("atomic action must finish before mode commit")
        if stored is None or stored != boundary:
            raise ValueError("current boundary differs from durable checkpoint")
        if boundary.persisted_at > now:
            raise ValueError("checkpoint is from the future")
        if mode_policy is not None:
            if boundary.confirmation_count < mode_policy.confirmation_count:
                raise ValueError("mode proposal confirmation count is insufficient")
            if current.switch_count >= mode_policy.max_switches:
                raise ValueError("mode switch limit exhausted")
            if current.last_switch_at is None:
                if mode_policy.min_dwell_s > 0 or mode_policy.cooldown_s > 0:
                    raise ValueError("last mode switch time is unknown")
            else:
                elapsed = (now - current.last_switch_at).total_seconds()
                if elapsed < max(mode_policy.min_dwell_s, mode_policy.cooldown_s):
                    raise ValueError("frozen dwell/cooldown time is not met")


def _committed_values(
    record: AutoModeTransition, current: AutoModeStatus, now: datetime
) -> tuple[AutoModeTransition, AutoModeStatus]:
    transition = record.model_copy(
        update={"status": AutoModeTransitionStatus.COMMITTED, "committed_at": now}, deep=True
    )
    status = current.model_copy(
        update={
            "current_mode": record.to_mode,
            "mode_version": record.new_mode_version,
            "switch_count": current.switch_count + 1,
            "last_switch_at": now,
            "last_decision_id": record.decision_id,
            "updated_at": now,
        },
        deep=True,
    )
    return transition, status


def _validate_transition_save(
    existing: AutoModeTransition | None, incoming: AutoModeTransition
) -> None:
    if existing is None:
        if incoming.status != AutoModeTransitionStatus.PREPARED:
            raise ValueError("terminal transition must be created by commit/abort CAS")
        return
    if existing.status == AutoModeTransitionStatus.PREPARED and incoming.status != existing.status:
        raise ValueError("terminal transition must be created by commit/abort CAS")
    if (
        existing.transition_id != incoming.transition_id
        or existing.payload_hash != incoming.payload_hash
    ):
        raise IdempotencyConflictError("mode transition idempotency/payload conflict")
    if existing.status != AutoModeTransitionStatus.PREPARED and existing != incoming:
        raise ValueError("terminal mode transition cannot be overwritten")
