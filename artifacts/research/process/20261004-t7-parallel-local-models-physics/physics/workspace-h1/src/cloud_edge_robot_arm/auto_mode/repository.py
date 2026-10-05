"""仓储接口或实现，隔离业务服务与底层存储细节。"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from cloud_edge_robot_arm.contracts import (
    AutoModeDecision,
    AutoModeStatus,
    AutoModeTransition,
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
        h = _hash(transition)
        existing_id = self._transition_idempotency.get(transition.idempotency_key)
        if existing_id is not None:
            existing = self._transitions[existing_id]
            if _hash(existing) != h and existing.transition_id != transition.transition_id:
                raise IdempotencyConflictError("mode transition idempotency conflict")
        existing_transition = self._transitions.get(transition.transition_id)
        if (
            existing_transition is not None
            and existing_transition.payload_hash
            and transition.payload_hash
        ):
            if (
                existing_transition.payload_hash != transition.payload_hash
                and existing_transition.status == transition.status
            ):
                raise IdempotencyConflictError("mode transition payload conflict")
        self._transitions[transition.transition_id] = transition.model_copy(deep=True)
        self._transition_idempotency[transition.idempotency_key] = transition.transition_id
        return transition

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
        self._statuses[status.task_id] = status.model_copy(deep=True)
        return status

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


class SQLiteAutoModeRepository:
    """SQLite AUTO 模式仓储，将审计记录和状态快照落盘保存。"""

    def __init__(self, path: str | Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock or _utc_now
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
        saved = self._memory.save_transition(transition)
        self._upsert_transition(saved)
        return saved

    def get_transition(self, transition_id: str) -> AutoModeTransition | None:
        """按 transition_id 读取模式切换记录。"""
        return self._memory.get_transition(transition_id)

    def get_transition_by_idempotency(self, idempotency_key: str) -> AutoModeTransition | None:
        """按幂等键读取模式切换记录。"""
        return self._memory.get_transition_by_idempotency(idempotency_key)

    def latest_prepared_transition(self, task_id: str) -> AutoModeTransition | None:
        """读取任务最近一次 PREPARED 切换，用于恢复未完成切换。"""
        return self._memory.latest_prepared_transition(task_id)

    def save_status(self, status: AutoModeStatus) -> AutoModeStatus:
        """保存当前 AUTO 模式状态到内存镜像和 SQLite 表。"""
        saved = self._memory.save_status(status)
        self._upsert("auto_mode_statuses", "task_id", status.task_id, status.task_id, saved)
        return saved

    def get_status(self, task_id: str) -> AutoModeStatus | None:
        """按任务读取当前 AUTO 模式状态。"""
        return self._memory.get_status(task_id)

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
            self._memory.save_transition(
                AutoModeTransition.model_validate_json(row["payload_json"])
            )
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
        self._conn.commit()

    def _upsert_transition(self, transition: AutoModeTransition) -> None:
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
        self._conn.commit()


def _hash(value: BaseModel) -> str:
    canonical = json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
