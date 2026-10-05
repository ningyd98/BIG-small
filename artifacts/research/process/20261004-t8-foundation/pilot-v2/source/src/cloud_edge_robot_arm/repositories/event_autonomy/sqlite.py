"""SQLite 仓储实现，负责事务、幂等写入和可恢复状态。

SQLite-backed EventAutonomyRepository with conflict-aware idempotency.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
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


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_hash(value: Any) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _checkpoint_hash(checkpoint: ExecutionCheckpoint) -> str:
    payload = checkpoint.model_dump(mode="json")
    payload["checkpoint_hash"] = ""
    return _canonical_hash(payload)


def _apply_hash(record: ReplanApplyRecord) -> str:
    payload = record.model_dump(mode="json")
    payload["apply_hash"] = ""
    return _canonical_hash(payload)


def _same_or_conflict(entity: str, key: str, existing_hash: str, new_hash: str) -> None:
    if existing_hash != new_hash:
        raise IdempotencyConflictError(f"{entity} idempotency conflict for key {key!r}")


class SQLiteEventAutonomyRepository:
    """SQLite-backed persistent repository with CAS and conflict semantics."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._write_lock = Lock()
        self._create_schema()
        self._migrate_schema()

    def _create_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS edge_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                step_id TEXT,
                severity TEXT NOT NULL DEFAULT 'ERROR',
                reason_code TEXT DEFAULT '',
                reason_detail TEXT DEFAULT '',
                robot_id TEXT DEFAULT '',
                plan_id TEXT DEFAULT '',
                plan_version INTEGER NOT NULL DEFAULT 0,
                command_seq INTEGER NOT NULL DEFAULT 0,
                details_json TEXT DEFAULT '{}',
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                handled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_edge_events_task ON edge_events(task_id);

            CREATE TABLE IF NOT EXISTS recovery_budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                budget_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL UNIQUE,
                per_step_retry_limit INTEGER NOT NULL DEFAULT 3,
                per_skill_retry_limit INTEGER NOT NULL DEFAULT 5,
                task_total_retry_limit INTEGER NOT NULL DEFAULT 10,
                retry_count_used INTEGER NOT NULL DEFAULT 0,
                task_retry_count INTEGER NOT NULL DEFAULT 0,
                step_retry_counts_json TEXT DEFAULT '{}',
                skill_retry_counts_json TEXT DEFAULT '{}',
                event_retry_counts_json TEXT DEFAULT '{}',
                retry_cooldown_ms INTEGER NOT NULL DEFAULT 500,
                retry_deadline TEXT,
                retry_backoff_policy TEXT NOT NULL DEFAULT 'exponential',
                effective_retry_limit INTEGER NOT NULL DEFAULT 3,
                remaining_retries INTEGER NOT NULL DEFAULT 3,
                scene_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recovery_budgets_task ON recovery_budgets(task_id);

            CREATE TABLE IF NOT EXISTS recovery_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                skill TEXT NOT NULL,
                event_id TEXT DEFAULT '',
                attempt_number INTEGER NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                error_code TEXT DEFAULT '',
                duration_ms INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recovery_attempts_task
                ON recovery_attempts(task_id, step_id);

            CREATE TABLE IF NOT EXISTS event_mode_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                current_state TEXT NOT NULL,
                reason TEXT DEFAULT '',
                event_id TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS event_mode_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                reason TEXT DEFAULT '',
                event_id TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_event_mode_transitions_task
                ON event_mode_transitions(task_id);

            CREATE TABLE IF NOT EXISTS failure_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                failure_event_id TEXT NOT NULL,
                failed_step_id TEXT NOT NULL,
                completed_step_ids_json TEXT DEFAULT '[]',
                failure_type TEXT DEFAULT '',
                severity TEXT DEFAULT 'ERROR',
                reason TEXT NOT NULL,
                recovery_hint TEXT DEFAULT '',
                local_retry_count INTEGER NOT NULL DEFAULT 0,
                retry_limit INTEGER NOT NULL DEFAULT 0,
                requested_replan_scope TEXT DEFAULT '',
                plan_version INTEGER NOT NULL DEFAULT 0,
                command_seq INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_failure_summaries_task ON failure_summaries(task_id);

            CREATE TABLE IF NOT EXISTS completion_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                final_plan_version INTEGER NOT NULL DEFAULT 0,
                completed_step_ids_json TEXT DEFAULT '[]',
                completion_criteria_results_json TEXT DEFAULT '{}',
                local_retry_count INTEGER NOT NULL DEFAULT 0,
                cloud_replan_count INTEGER NOT NULL DEFAULT 0,
                result TEXT NOT NULL DEFAULT 'SUCCESS',
                final_safety_decision TEXT DEFAULT 'ALLOW',
                plan_version INTEGER NOT NULL DEFAULT 0,
                command_seq INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_completion_summaries_task
                ON completion_summaries(task_id);

            CREATE TABLE IF NOT EXISTS replan_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT,
                task_id TEXT NOT NULL,
                trigger_event_id TEXT NOT NULL,
                failure_summary_id TEXT DEFAULT '',
                current_plan_version INTEGER NOT NULL DEFAULT 0,
                current_command_seq INTEGER NOT NULL DEFAULT 1,
                requested_replan_scope TEXT DEFAULT '',
                completed_step_ids_json TEXT DEFAULT '[]',
                failed_step_id TEXT DEFAULT '',
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_replan_requests_idempotency
                ON replan_requests(idempotency_key)
                WHERE idempotency_key IS NOT NULL AND idempotency_key != '';
            CREATE INDEX IF NOT EXISTS idx_replan_requests_task ON replan_requests(task_id);

            CREATE TABLE IF NOT EXISTS replan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                outcome TEXT NOT NULL DEFAULT 'REPLANNED',
                new_plan_version INTEGER NOT NULL DEFAULT 0,
                new_command_seq INTEGER NOT NULL DEFAULT 1,
                new_steps_json TEXT DEFAULT '[]',
                validation_errors_json TEXT DEFAULT '[]',
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_replan_results_task ON replan_results(task_id);

            CREATE TABLE IF NOT EXISTS event_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT,
                task_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'PENDING',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 5,
                backoff_base_ms INTEGER NOT NULL DEFAULT 1000,
                next_attempt_at TEXT,
                claimed_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_event_outbox_task ON event_outbox(task_id);
            CREATE INDEX IF NOT EXISTS idx_event_outbox_status ON event_outbox(status);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_event_outbox_idempotency
                ON event_outbox(idempotency_key)
                WHERE idempotency_key IS NOT NULL AND idempotency_key != '';

            CREATE TABLE IF NOT EXISTS event_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_event_audit_events_task ON event_audit_events(task_id);

            CREATE TABLE IF NOT EXISTS plan_versions (
                task_id TEXT PRIMARY KEY,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_contract_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                scene_version INTEGER NOT NULL,
                status TEXT NOT NULL,
                based_on_plan_version INTEGER,
                contract_json TEXT NOT NULL,
                record_json TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                superseded_at TEXT,
                correlation_id TEXT DEFAULT '',
                UNIQUE(task_id, plan_version)
            );
            CREATE INDEX IF NOT EXISTS idx_contract_versions_task
                ON task_contract_versions(task_id, plan_version);

            CREATE TABLE IF NOT EXISTS active_task_contracts (
                task_id TEXT PRIMARY KEY,
                plan_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                scene_version INTEGER NOT NULL,
                record_json TEXT NOT NULL,
                contract_hash TEXT NOT NULL,
                activated_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS execution_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                execution_state TEXT NOT NULL,
                completed_step_ids_json TEXT DEFAULT '[]',
                payload_json TEXT NOT NULL,
                checkpoint_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_checkpoints_task ON execution_checkpoints(task_id, id);

            CREATE TABLE IF NOT EXISTS replan_apply_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apply_id TEXT NOT NULL UNIQUE,
                request_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                plan_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                previous_plan_version INTEGER NOT NULL,
                previous_command_seq INTEGER NOT NULL,
                new_plan_version INTEGER NOT NULL,
                new_command_seq INTEGER NOT NULL,
                checkpoint_id TEXT DEFAULT '',
                status TEXT NOT NULL,
                reason TEXT DEFAULT '',
                payload_json TEXT NOT NULL,
                apply_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_replan_apply_task ON replan_apply_records(task_id);

            CREATE TABLE IF NOT EXISTS command_acks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ack_key TEXT NOT NULL UNIQUE,
                request_id TEXT DEFAULT '',
                task_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                checkpoint_id TEXT DEFAULT '',
                status TEXT NOT NULL,
                accepted INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_command_acks_task
                ON command_acks(task_id, plan_version, command_seq);
            """
        )
        self._conn.commit()

    def _migrate_schema(self) -> None:
        additions = {
            "edge_events": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "failure_summaries": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "completion_summaries": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "replan_requests": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "replan_results": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "event_outbox": [("payload_hash", "TEXT NOT NULL DEFAULT ''")],
            "recovery_budgets": [
                ("task_retry_count", "INTEGER NOT NULL DEFAULT 0"),
                ("step_retry_counts_json", "TEXT DEFAULT '{}'"),
                ("skill_retry_counts_json", "TEXT DEFAULT '{}'"),
                ("event_retry_counts_json", "TEXT DEFAULT '{}'"),
            ],
            "recovery_attempts": [("event_id", "TEXT DEFAULT ''")],
        }
        for table, cols in additions.items():
            existing = {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}
            for name, ddl in cols:
                if name not in existing:
                    self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
        self._conn.commit()

    # ── generic helpers ──────────────────────────────────────────────────

    def _existing_by_key(self, table: str, key_col: str, key: str) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self._conn.execute(
            f"SELECT payload_json, payload_hash FROM {table} WHERE {key_col} = ?",
            (key,),
        ).fetchone()
        return row

    def _json(self, value: Any) -> str:
        return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))

    # ── Events ──────────────────────────────────────────────────────────

    def save_event(self, event: EdgeEvent) -> EdgeEvent:
        payload = event.model_dump_json()
        payload_hash = _canonical_hash(event)
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("edge_events", "event_id", event.event_id)
            if row is not None:
                _same_or_conflict(
                    "EdgeEvent",
                    event.event_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return EdgeEvent.model_validate_json(row["payload_json"])
            saved = event.model_copy(update={"event_hash": event.event_hash or payload_hash})
            payload = saved.model_dump_json()
            self._conn.execute(
                """INSERT INTO edge_events (
                    event_id, task_id, event_type, step_id, severity, reason_code,
                    reason_detail, robot_id, plan_id, plan_version, command_seq,
                    details_json, payload_json, payload_hash, handled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                (
                    saved.event_id,
                    saved.task_id,
                    saved.event_type.value,
                    saved.step_id,
                    saved.severity,
                    saved.reason_code,
                    saved.reason_detail,
                    saved.robot_id,
                    saved.plan_id,
                    saved.plan_version,
                    saved.command_seq,
                    self._json(saved.details),
                    payload,
                    payload_hash,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return saved

    def get_event(self, event_id: str) -> EdgeEvent | None:
        row = self._conn.execute(
            "SELECT payload_json FROM edge_events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return None if row is None else EdgeEvent.model_validate_json(row["payload_json"])

    def list_events(self, task_id: str) -> list[EdgeEvent]:
        rows = self._conn.execute(
            "SELECT payload_json FROM edge_events WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [EdgeEvent.model_validate_json(r["payload_json"]) for r in rows]

    def mark_event_handled(self, event_id: str, handled_at: datetime | None = None) -> bool:
        now = (handled_at or datetime.now(UTC)).isoformat()
        with self._write_lock:
            cursor = self._conn.execute(
                "UPDATE edge_events SET handled = 1, updated_at = ? WHERE event_id = ?",
                (now, event_id),
            )
            self._conn.commit()
            return cursor.rowcount == 1

    # ── Retry Budget ────────────────────────────────────────────────────

    def save_retry_budget(self, budget: RecoveryBudget) -> RecoveryBudget:
        now = _iso_now()
        deadline = budget.retry_deadline.isoformat() if budget.retry_deadline else None
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO recovery_budgets (
                    budget_id, task_id, per_step_retry_limit, per_skill_retry_limit,
                    task_total_retry_limit, retry_count_used, task_retry_count,
                    step_retry_counts_json, skill_retry_counts_json, event_retry_counts_json,
                    retry_cooldown_ms, retry_deadline, retry_backoff_policy,
                    effective_retry_limit, remaining_retries, scene_version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    per_step_retry_limit = excluded.per_step_retry_limit,
                    per_skill_retry_limit = excluded.per_skill_retry_limit,
                    task_total_retry_limit = excluded.task_total_retry_limit,
                    retry_count_used = excluded.retry_count_used,
                    task_retry_count = excluded.task_retry_count,
                    step_retry_counts_json = excluded.step_retry_counts_json,
                    skill_retry_counts_json = excluded.skill_retry_counts_json,
                    event_retry_counts_json = excluded.event_retry_counts_json,
                    retry_deadline = excluded.retry_deadline,
                    effective_retry_limit = excluded.effective_retry_limit,
                    remaining_retries = excluded.remaining_retries,
                    scene_version = excluded.scene_version,
                    updated_at = excluded.updated_at""",
                (
                    budget.budget_id,
                    budget.task_id,
                    budget.per_step_retry_limit,
                    budget.per_skill_retry_limit,
                    budget.task_total_retry_limit,
                    budget.retry_count_used,
                    budget.task_retry_count,
                    self._json(budget.step_retry_counts),
                    self._json(budget.skill_retry_counts),
                    self._json(budget.event_retry_counts),
                    budget.retry_cooldown_ms,
                    deadline,
                    budget.retry_backoff_policy,
                    budget.effective_retry_limit,
                    budget.remaining_retries,
                    budget.scene_version,
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return self.get_retry_budget(budget.task_id) or budget

    def get_retry_budget(self, task_id: str) -> RecoveryBudget | None:
        row = self._conn.execute(
            "SELECT * FROM recovery_budgets WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            return None
        return RecoveryBudget(
            budget_id=row["budget_id"],
            task_id=row["task_id"],
            per_step_retry_limit=row["per_step_retry_limit"],
            per_skill_retry_limit=row["per_skill_retry_limit"],
            task_total_retry_limit=row["task_total_retry_limit"],
            retry_count_used=row["retry_count_used"],
            task_retry_count=row["task_retry_count"],
            step_retry_counts=json.loads(row["step_retry_counts_json"] or "{}"),
            skill_retry_counts=json.loads(row["skill_retry_counts_json"] or "{}"),
            event_retry_counts=json.loads(row["event_retry_counts_json"] or "{}"),
            retry_cooldown_ms=row["retry_cooldown_ms"],
            retry_deadline=datetime.fromisoformat(row["retry_deadline"])
            if row["retry_deadline"]
            else None,
            retry_backoff_policy=row["retry_backoff_policy"],
            effective_retry_limit=row["effective_retry_limit"],
            remaining_retries=row["remaining_retries"],
            scene_version=row["scene_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def consume_retry_if_available(
        self,
        task_id: str,
        step_id: str,
        skill: str,
        expected_count: int,
        event_id: str = "",
    ) -> tuple[bool, RecoveryBudget | None]:
        now = _iso_now()
        with self._write_lock:
            budget = self.get_retry_budget(task_id)
            if budget is None:
                return False, None
            if budget.retry_count_used != expected_count or budget.remaining_retries <= 0:
                return False, budget
            if event_id and budget.event_retry_counts.get(event_id, 0) > 0:
                return False, budget
            step_counts = dict(budget.step_retry_counts)
            skill_counts = dict(budget.skill_retry_counts)
            event_counts = dict(budget.event_retry_counts)
            step_count = step_counts.get(step_id, 0)
            skill_count = skill_counts.get(skill, 0)
            effective_remaining = min(
                max(0, budget.task_total_retry_limit - budget.task_retry_count),
                max(0, budget.per_step_retry_limit - step_count),
                max(0, budget.per_skill_retry_limit - skill_count),
                budget.remaining_retries,
            )
            if effective_remaining <= 0:
                return False, budget
            if step_id:
                step_counts[step_id] = step_count + 1
            if skill:
                skill_counts[skill] = skill_count + 1
            if event_id:
                event_counts[event_id] = 1
            cursor = self._conn.execute(
                """UPDATE recovery_budgets
                   SET retry_count_used = retry_count_used + 1,
                       task_retry_count = task_retry_count + 1,
                       step_retry_counts_json = ?,
                       skill_retry_counts_json = ?,
                       event_retry_counts_json = ?,
                       remaining_retries = remaining_retries - 1,
                       updated_at = ?
                   WHERE task_id = ? AND retry_count_used = ? AND remaining_retries > 0""",
                (
                    self._json(step_counts),
                    self._json(skill_counts),
                    self._json(event_counts),
                    now,
                    task_id,
                    expected_count,
                ),
            )
            if cursor.rowcount != 1:
                self._conn.commit()
                return False, self.get_retry_budget(task_id)
            self._conn.execute(
                """INSERT INTO recovery_attempts
                   (task_id, step_id, skill, event_id, attempt_number, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, step_id, skill, event_id, expected_count + 1, now),
            )
            self._conn.commit()
            return True, self.get_retry_budget(task_id)

    # ── State Machine ───────────────────────────────────────────────────

    def save_state(self, task_id: str, state: str, reason: str, event_id: str = "") -> None:
        now = _iso_now()
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO event_mode_states
                   (task_id, current_state, reason, event_id, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                       current_state = excluded.current_state,
                       reason = excluded.reason,
                       event_id = excluded.event_id,
                       updated_at = excluded.updated_at""",
                (task_id, state, reason, event_id, now),
            )
            self._conn.commit()

    def get_state(self, task_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT current_state FROM event_mode_states WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return None if row is None else row["current_state"]

    def save_state_transition(
        self, task_id: str, from_state: str, to_state: str, reason: str, event_id: str = ""
    ) -> None:
        now = _iso_now()
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO event_mode_transitions
                   (task_id, from_state, to_state, reason, event_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, from_state, to_state, reason, event_id, now),
            )
            self._conn.execute(
                """INSERT INTO event_mode_states
                   (task_id, current_state, reason, event_id, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                       current_state = excluded.current_state,
                       reason = excluded.reason,
                       event_id = excluded.event_id,
                       updated_at = excluded.updated_at""",
                (task_id, to_state, reason, event_id, now),
            )
            self._conn.commit()

    def list_state_transitions(self, task_id: str) -> list[dict[str, object]]:
        rows = self._conn.execute(
            """SELECT from_state, to_state, reason, event_id, created_at
               FROM event_mode_transitions WHERE task_id = ? ORDER BY id""",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Failure/Completion/Replan helpers ───────────────────────────────

    def save_failure_summary(self, summary: FailureSummary) -> FailureSummary:
        payload_hash = _canonical_hash(summary)
        payload = summary.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("failure_summaries", "summary_id", summary.summary_id)
            if row is not None:
                _same_or_conflict(
                    "FailureSummary",
                    summary.summary_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return FailureSummary.model_validate_json(row["payload_json"])
            saved = summary.model_copy(
                update={"summary_hash": summary.summary_hash or payload_hash}
            )
            payload = saved.model_dump_json()
            self._conn.execute(
                """INSERT INTO failure_summaries (
                    summary_id, task_id, failure_event_id, failed_step_id,
                    completed_step_ids_json, failure_type, severity, reason,
                    recovery_hint, local_retry_count, retry_limit,
                    requested_replan_scope, plan_version, command_seq,
                    payload_json, payload_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.summary_id,
                    saved.task_id,
                    saved.failure_event_id,
                    saved.failed_step_id,
                    self._json(saved.completed_step_ids),
                    saved.failure_type,
                    saved.severity,
                    saved.reason,
                    saved.recovery_hint,
                    saved.local_retry_count,
                    saved.retry_limit,
                    saved.requested_replan_scope,
                    saved.plan_version,
                    saved.command_seq,
                    payload,
                    payload_hash,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return saved

    def get_failure_summary(self, summary_id: str) -> FailureSummary | None:
        row = self._conn.execute(
            "SELECT payload_json FROM failure_summaries WHERE summary_id = ?",
            (summary_id,),
        ).fetchone()
        return None if row is None else FailureSummary.model_validate_json(row["payload_json"])

    def save_completion_summary(self, summary: CompletionSummary) -> CompletionSummary:
        payload_hash = _canonical_hash(summary)
        payload = summary.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("completion_summaries", "summary_id", summary.summary_id)
            if row is not None:
                existing = CompletionSummary.model_validate_json(row["payload_json"])
                if existing.summary_hash and existing.summary_hash == summary.summary_hash:
                    return existing
                _same_or_conflict(
                    "CompletionSummary",
                    summary.summary_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return existing
            saved = summary.model_copy(
                update={"summary_hash": summary.summary_hash or payload_hash}
            )
            payload = saved.model_dump_json()
            self._conn.execute(
                """INSERT INTO completion_summaries (
                    summary_id, task_id, final_plan_version, completed_step_ids_json,
                    completion_criteria_results_json, local_retry_count, cloud_replan_count,
                    result, final_safety_decision, plan_version, command_seq,
                    payload_json, payload_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.summary_id,
                    saved.task_id,
                    saved.final_plan_version,
                    self._json(saved.completed_step_ids),
                    self._json(saved.completion_criteria_results),
                    saved.local_retry_count,
                    saved.cloud_replan_count,
                    saved.result,
                    saved.final_safety_decision,
                    saved.plan_version,
                    saved.command_seq,
                    payload,
                    payload_hash,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return saved

    def get_completion_summary(self, summary_id: str) -> CompletionSummary | None:
        row = self._conn.execute(
            "SELECT payload_json FROM completion_summaries WHERE summary_id = ?",
            (summary_id,),
        ).fetchone()
        return None if row is None else CompletionSummary.model_validate_json(row["payload_json"])

    def get_completion_summary_for_task(self, task_id: str) -> CompletionSummary | None:
        row = self._conn.execute(
            """SELECT payload_json FROM completion_summaries
               WHERE task_id = ? ORDER BY id DESC LIMIT 1""",
            (task_id,),
        ).fetchone()
        return None if row is None else CompletionSummary.model_validate_json(row["payload_json"])

    def save_replan_request(self, request: LocalReplanningRequest) -> LocalReplanningRequest:
        payload_hash = _canonical_hash(request)
        payload = request.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("replan_requests", "request_id", request.request_id)
            if row is not None:
                _same_or_conflict(
                    "LocalReplanningRequest",
                    request.request_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return LocalReplanningRequest.model_validate_json(row["payload_json"])
            if request.idempotency_key:
                row = self._conn.execute(
                    """SELECT payload_json, payload_hash FROM replan_requests
                       WHERE idempotency_key = ?""",
                    (request.idempotency_key,),
                ).fetchone()
                if row is not None:
                    _same_or_conflict(
                        "LocalReplanningRequest",
                        request.idempotency_key,
                        row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                        payload_hash,
                    )
                    return LocalReplanningRequest.model_validate_json(row["payload_json"])
            self._conn.execute(
                """INSERT INTO replan_requests (
                    request_id, idempotency_key, task_id, trigger_event_id,
                    failure_summary_id, current_plan_version, current_command_seq,
                    requested_replan_scope, completed_step_ids_json, failed_step_id,
                    payload_json, payload_hash, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.request_id,
                    request.idempotency_key or None,
                    request.task_id,
                    request.trigger_event_id,
                    request.failure_summary_id,
                    request.current_plan_version,
                    request.current_command_seq,
                    request.requested_replan_scope,
                    self._json(request.completed_step_ids),
                    request.failed_step_id,
                    payload,
                    payload_hash,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return request

    def get_replan_request(self, request_id: str) -> LocalReplanningRequest | None:
        row = self._conn.execute(
            "SELECT payload_json FROM replan_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return (
            None if row is None else LocalReplanningRequest.model_validate_json(row["payload_json"])
        )

    def save_replan_result(self, result: LocalReplanningResponse) -> LocalReplanningResponse:
        payload_hash = _canonical_hash(result)
        payload = result.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("replan_results", "request_id", result.request_id)
            if row is not None:
                _same_or_conflict(
                    "LocalReplanningResponse",
                    result.request_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return LocalReplanningResponse.model_validate_json(row["payload_json"])
            task_id = self._task_id_for_request(result.request_id)
            saved = result.model_copy(
                update={"response_hash": result.response_hash or payload_hash}
            )
            payload = saved.model_dump_json()
            self._conn.execute(
                """INSERT INTO replan_results (
                    request_id, task_id, outcome, new_plan_version, new_command_seq,
                    new_steps_json, validation_errors_json, payload_json, payload_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.request_id,
                    task_id,
                    saved.outcome,
                    saved.new_plan_version,
                    saved.new_command_seq,
                    self._json([s.model_dump(mode="json") for s in saved.new_steps]),
                    self._json(saved.validation_errors),
                    payload,
                    payload_hash,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return saved

    def get_replan_result(self, request_id: str) -> LocalReplanningResponse | None:
        row = self._conn.execute(
            "SELECT payload_json FROM replan_results WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return (
            None
            if row is None
            else LocalReplanningResponse.model_validate_json(row["payload_json"])
        )

    def _task_id_for_request(self, request_id: str) -> str:
        row = self._conn.execute(
            "SELECT task_id FROM replan_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return "" if row is None else row["task_id"]

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
        with self._write_lock:
            return self._save_active_contract_locked(
                contract,
                plan_id=plan_id,
                robot_id=robot_id,
                status=status,
                based_on_plan_version=based_on_plan_version,
                correlation_id=correlation_id,
            )

    def _save_active_contract_locked(
        self,
        contract: TaskContract,
        *,
        plan_id: str,
        robot_id: str,
        status: str,
        based_on_plan_version: int | None,
        correlation_id: str,
    ) -> ActiveTaskContractRecord:
        now = datetime.now(UTC)
        contract_hash = _canonical_hash(contract)
        existing = self._conn.execute(
            """SELECT record_json, contract_hash FROM task_contract_versions
               WHERE task_id = ? AND plan_version = ?""",
            (contract.task_id, contract.plan_version),
        ).fetchone()
        if existing is not None:
            _same_or_conflict(
                "ActiveTaskContract",
                f"{contract.task_id}:{contract.plan_version}",
                existing["contract_hash"],
                contract_hash,
            )
            record = ActiveTaskContractRecord.model_validate_json(existing["record_json"])
            if status == ActiveContractStatus.ACTIVE.value:
                self._set_active_locked(record)
            self._conn.commit()
            return record
        record = ActiveTaskContractRecord(
            task_id=contract.task_id,
            plan_id=plan_id,
            robot_id=robot_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            scene_version=contract.scene_version,
            contract=contract,
            status=status,
            based_on_plan_version=based_on_plan_version,
            created_at=now,
            activated_at=now,
            correlation_id=correlation_id,
            contract_hash=contract_hash,
        )
        if status == ActiveContractStatus.ACTIVE.value:
            current = self.get_active_contract(contract.task_id)
            if current is not None and current.plan_version != record.plan_version:
                self._supersede_version_locked(current.task_id, current.plan_version, now)
        self._conn.execute(
            """INSERT INTO task_contract_versions (
                task_id, plan_id, robot_id, plan_version, command_seq, scene_version,
                status, based_on_plan_version, contract_json, record_json, contract_hash,
                created_at, activated_at, superseded_at, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.task_id,
                record.plan_id,
                record.robot_id,
                record.plan_version,
                record.command_seq,
                record.scene_version,
                record.status,
                record.based_on_plan_version,
                contract.model_dump_json(),
                record.model_dump_json(),
                record.contract_hash,
                record.created_at.isoformat(),
                record.activated_at.isoformat(),
                record.superseded_at.isoformat() if record.superseded_at else None,
                record.correlation_id,
            ),
        )
        if status == ActiveContractStatus.ACTIVE.value:
            self._set_active_locked(record)
            self._conn.execute(
                """INSERT INTO plan_versions (task_id, plan_version, command_seq, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(task_id) DO UPDATE SET
                       plan_version = excluded.plan_version,
                       command_seq = excluded.command_seq,
                       updated_at = excluded.updated_at""",
                (record.task_id, record.plan_version, record.command_seq, _iso_now()),
            )
        self._conn.commit()
        return record

    def _set_active_locked(self, record: ActiveTaskContractRecord) -> None:
        now = _iso_now()
        self._conn.execute(
            """INSERT INTO active_task_contracts (
                task_id, plan_id, robot_id, plan_version, command_seq, scene_version,
                record_json, contract_hash, activated_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                plan_id = excluded.plan_id,
                robot_id = excluded.robot_id,
                plan_version = excluded.plan_version,
                command_seq = excluded.command_seq,
                scene_version = excluded.scene_version,
                record_json = excluded.record_json,
                contract_hash = excluded.contract_hash,
                activated_at = excluded.activated_at,
                updated_at = excluded.updated_at""",
            (
                record.task_id,
                record.plan_id,
                record.robot_id,
                record.plan_version,
                record.command_seq,
                record.scene_version,
                record.model_dump_json(),
                record.contract_hash,
                record.activated_at.isoformat(),
                now,
            ),
        )

    def _supersede_version_locked(self, task_id: str, plan_version: int, at: datetime) -> None:
        row = self._conn.execute(
            "SELECT record_json FROM task_contract_versions WHERE task_id = ? AND plan_version = ?",
            (task_id, plan_version),
        ).fetchone()
        if row is None:
            return
        record = ActiveTaskContractRecord.model_validate_json(row["record_json"])
        updated = record.model_copy(
            update={"status": ActiveContractStatus.SUPERSEDED.value, "superseded_at": at},
            deep=True,
        )
        self._conn.execute(
            """UPDATE task_contract_versions
               SET status = ?, record_json = ?, superseded_at = ?
               WHERE task_id = ? AND plan_version = ?""",
            (
                updated.status,
                updated.model_dump_json(),
                updated.superseded_at.isoformat() if updated.superseded_at else None,
                task_id,
                plan_version,
            ),
        )

    def get_active_contract(self, task_id: str) -> ActiveTaskContractRecord | None:
        row = self._conn.execute(
            "SELECT record_json FROM active_task_contracts WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return (
            None
            if row is None
            else ActiveTaskContractRecord.model_validate_json(row["record_json"])
        )

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
        with self._write_lock:
            row = self._conn.execute(
                """SELECT record_json FROM active_task_contracts
                   WHERE task_id = ? AND plan_version = ? AND command_seq = ?""",
                (task_id, expected_plan_version, expected_command_seq),
            ).fetchone()
            if row is None:
                return None
            if (
                new_contract.plan_version <= expected_plan_version
                or new_contract.command_seq <= expected_command_seq
            ):
                return None
            self._supersede_version_locked(task_id, expected_plan_version, datetime.now(UTC))
            record = self._save_active_contract_locked(
                new_contract,
                plan_id=plan_id,
                robot_id=robot_id,
                status=ActiveContractStatus.ACTIVE.value,
                based_on_plan_version=based_on_plan_version,
                correlation_id=correlation_id,
            )
            return record

    def list_contract_versions(self, task_id: str) -> list[ActiveTaskContractRecord]:
        rows = self._conn.execute(
            """SELECT record_json FROM task_contract_versions
               WHERE task_id = ? ORDER BY plan_version""",
            (task_id,),
        ).fetchall()
        return [ActiveTaskContractRecord.model_validate_json(r["record_json"]) for r in rows]

    # ── Checkpoints ─────────────────────────────────────────────────────

    def save_execution_checkpoint(self, checkpoint: ExecutionCheckpoint) -> ExecutionCheckpoint:
        h = checkpoint.checkpoint_hash or _checkpoint_hash(checkpoint)
        saved = checkpoint.model_copy(update={"checkpoint_hash": h}, deep=True)
        payload = saved.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                """SELECT payload_json, checkpoint_hash FROM execution_checkpoints
                   WHERE checkpoint_id = ?""",
                (saved.checkpoint_id,),
            ).fetchone()
            if row is not None:
                _same_or_conflict(
                    "ExecutionCheckpoint", saved.checkpoint_id, row["checkpoint_hash"], h
                )
                return ExecutionCheckpoint.model_validate_json(row["payload_json"])
            self._conn.execute(
                """INSERT INTO execution_checkpoints (
                    checkpoint_id, task_id, plan_id, robot_id, plan_version, command_seq,
                    execution_state, completed_step_ids_json, payload_json, checkpoint_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.checkpoint_id,
                    saved.task_id,
                    saved.plan_id,
                    saved.robot_id,
                    saved.plan_version,
                    saved.command_seq,
                    saved.execution_state,
                    self._json(saved.completed_step_ids),
                    payload,
                    h,
                    saved.created_at.isoformat(),
                    now,
                ),
            )
            self._conn.commit()
            return saved

    def get_latest_execution_checkpoint(self, task_id: str) -> ExecutionCheckpoint | None:
        row = self._conn.execute(
            """SELECT payload_json FROM execution_checkpoints
               WHERE task_id = ? ORDER BY id DESC LIMIT 1""",
            (task_id,),
        ).fetchone()
        return None if row is None else ExecutionCheckpoint.model_validate_json(row["payload_json"])

    def get_checkpoint(self, checkpoint_id: str) -> ExecutionCheckpoint | None:
        row = self._conn.execute(
            "SELECT payload_json FROM execution_checkpoints WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        return None if row is None else ExecutionCheckpoint.model_validate_json(row["payload_json"])

    def compare_and_set_checkpoint(
        self,
        *,
        checkpoint_id: str,
        expected_checkpoint_hash: str,
        new_checkpoint: ExecutionCheckpoint,
    ) -> bool:
        existing = self.get_checkpoint(checkpoint_id)
        if existing is None or existing.checkpoint_hash != expected_checkpoint_hash:
            return False
        h = new_checkpoint.checkpoint_hash or _checkpoint_hash(new_checkpoint)
        saved = new_checkpoint.model_copy(update={"checkpoint_hash": h}, deep=True)
        payload = saved.model_dump_json()
        with self._write_lock:
            if saved.checkpoint_id == checkpoint_id:
                cursor = self._conn.execute(
                    """UPDATE execution_checkpoints
                       SET task_id = ?, plan_id = ?, robot_id = ?, plan_version = ?,
                           command_seq = ?, execution_state = ?, completed_step_ids_json = ?,
                           payload_json = ?, checkpoint_hash = ?, updated_at = ?
                       WHERE checkpoint_id = ? AND checkpoint_hash = ?""",
                    (
                        saved.task_id,
                        saved.plan_id,
                        saved.robot_id,
                        saved.plan_version,
                        saved.command_seq,
                        saved.execution_state,
                        self._json(saved.completed_step_ids),
                        payload,
                        h,
                        _iso_now(),
                        checkpoint_id,
                        expected_checkpoint_hash,
                    ),
                )
                self._conn.commit()
                return cursor.rowcount == 1
            row = self._conn.execute(
                "SELECT checkpoint_hash FROM execution_checkpoints WHERE checkpoint_id = ?",
                (saved.checkpoint_id,),
            ).fetchone()
            if row is not None:
                _same_or_conflict(
                    "ExecutionCheckpoint", saved.checkpoint_id, row["checkpoint_hash"], h
                )
                return True
            self._conn.execute(
                """INSERT INTO execution_checkpoints (
                    checkpoint_id, task_id, plan_id, robot_id, plan_version, command_seq,
                    execution_state, completed_step_ids_json, payload_json, checkpoint_hash,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.checkpoint_id,
                    saved.task_id,
                    saved.plan_id,
                    saved.robot_id,
                    saved.plan_version,
                    saved.command_seq,
                    saved.execution_state,
                    self._json(saved.completed_step_ids),
                    payload,
                    h,
                    saved.created_at.isoformat(),
                    _iso_now(),
                ),
            )
            self._conn.commit()
            return True

    # ── Replan apply and ACK ────────────────────────────────────────────

    def save_replan_apply_record(self, record: ReplanApplyRecord) -> ReplanApplyRecord:
        h = record.apply_hash or _apply_hash(record)
        saved = record.model_copy(update={"apply_hash": h}, deep=True)
        payload = saved.model_dump_json()
        with self._write_lock:
            row = self._conn.execute(
                """SELECT payload_json, apply_hash FROM replan_apply_records
                   WHERE apply_id = ? OR request_id = ?""",
                (saved.apply_id, saved.request_id),
            ).fetchone()
            if row is not None:
                _same_or_conflict("ReplanApplyRecord", saved.apply_id, row["apply_hash"], h)
                return ReplanApplyRecord.model_validate_json(row["payload_json"])
            self._conn.execute(
                """INSERT INTO replan_apply_records (
                    apply_id, request_id, task_id, plan_id, robot_id,
                    previous_plan_version, previous_command_seq, new_plan_version,
                    new_command_seq, checkpoint_id, status, reason, payload_json,
                    apply_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    saved.apply_id,
                    saved.request_id,
                    saved.task_id,
                    saved.plan_id,
                    saved.robot_id,
                    saved.previous_plan_version,
                    saved.previous_command_seq,
                    saved.new_plan_version,
                    saved.new_command_seq,
                    saved.checkpoint_id,
                    saved.status,
                    saved.reason,
                    payload,
                    h,
                    saved.created_at.isoformat(),
                ),
            )
            self._conn.commit()
            return saved

    def get_replan_apply_record(self, apply_id: str) -> ReplanApplyRecord | None:
        row = self._conn.execute(
            "SELECT payload_json FROM replan_apply_records WHERE apply_id = ?",
            (apply_id,),
        ).fetchone()
        return None if row is None else ReplanApplyRecord.model_validate_json(row["payload_json"])

    def get_replan_apply_record_for_request(self, request_id: str) -> ReplanApplyRecord | None:
        row = self._conn.execute(
            "SELECT payload_json FROM replan_apply_records WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return None if row is None else ReplanApplyRecord.model_validate_json(row["payload_json"])

    def save_command_ack(self, ack: CommandAck) -> CommandAck:
        key = ack.request_id or f"{ack.task_id}:{ack.plan_version}:{ack.command_seq}"
        h = _canonical_hash(ack)
        payload = ack.model_dump_json()
        with self._write_lock:
            row = self._conn.execute(
                "SELECT payload_json, payload_hash FROM command_acks WHERE ack_key = ?",
                (key,),
            ).fetchone()
            if row is not None:
                _same_or_conflict("CommandAck", key, row["payload_hash"], h)
                return CommandAck.model_validate_json(row["payload_json"])
            self._conn.execute(
                """INSERT INTO command_acks (
                    ack_key, request_id, task_id, plan_version, command_seq,
                    checkpoint_id, status, accepted, payload_json, payload_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    key,
                    ack.request_id,
                    ack.task_id,
                    ack.plan_version,
                    ack.command_seq,
                    ack.checkpoint_id,
                    ack.status,
                    int(ack.accepted),
                    payload,
                    h,
                    _iso_now(),
                ),
            )
            self._conn.commit()
            return ack

    def get_command_ack(self, request_id: str) -> CommandAck | None:
        row = self._conn.execute(
            """SELECT payload_json FROM command_acks
               WHERE ack_key = ? OR request_id = ? ORDER BY id DESC LIMIT 1""",
            (request_id, request_id),
        ).fetchone()
        return None if row is None else CommandAck.model_validate_json(row["payload_json"])

    # ── Outbox ──────────────────────────────────────────────────────────

    def enqueue_outbox(self, message: PendingMessage) -> PendingMessage:
        payload_hash = _canonical_hash(message)
        payload = message.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            row = self._existing_by_key("event_outbox", "message_id", message.message_id)
            if row is not None:
                _same_or_conflict(
                    "PendingMessage",
                    message.message_id,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return PendingMessage.model_validate_json(row["payload_json"])
            idempotency_key = message.idempotency_key or message.message_id
            row = self._conn.execute(
                "SELECT payload_json, payload_hash FROM event_outbox WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is not None:
                _same_or_conflict(
                    "PendingMessage",
                    idempotency_key,
                    row["payload_hash"] or _canonical_hash(json.loads(row["payload_json"])),
                    payload_hash,
                )
                return PendingMessage.model_validate_json(row["payload_json"])
            self._conn.execute(
                """INSERT INTO event_outbox (
                    message_id, idempotency_key, task_id, message_type, payload_json,
                    payload_hash, status, retry_count, max_retries, backoff_base_ms,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    message.message_id,
                    idempotency_key,
                    message.task_id,
                    message.message_type,
                    payload,
                    payload_hash,
                    message.status.value,
                    message.retry_count,
                    message.max_retries,
                    message.backoff_base_ms,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return message

    def claim_outbox_message(self) -> PendingMessage | None:
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                """SELECT message_id, payload_json FROM event_outbox
                   WHERE status IN ('PENDING', 'RETRY_WAIT')
                     AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                   ORDER BY id LIMIT 1""",
                (now,),
            ).fetchone()
            if row is None:
                return None
            msg = PendingMessage.model_validate_json(row["payload_json"])
            updated = msg.model_copy(update={"status": MessageStatus.SENDING}, deep=True)
            updated_payload = updated.model_dump_json()
            cursor = self._conn.execute(
                """UPDATE event_outbox
                   SET status = 'SENDING', claimed_at = ?, payload_json = ?,
                       payload_hash = ?, updated_at = ?
                   WHERE message_id = ? AND status IN ('PENDING', 'RETRY_WAIT')""",
                (now, updated_payload, _canonical_hash(updated), now, msg.message_id),
            )
            self._conn.commit()
            return updated if cursor.rowcount == 1 else None

    def mark_outbox_sent(self, message_id: str) -> bool:
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                "SELECT status, payload_json FROM event_outbox WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            if row is None:
                return False
            if row["status"] == "SENT":
                return True
            if row["status"] != "SENDING":
                return False
            msg = PendingMessage.model_validate_json(row["payload_json"])
            updated = msg.model_copy(update={"status": MessageStatus.SENT}, deep=True)
            cursor = self._conn.execute(
                """UPDATE event_outbox
                   SET status = 'SENT', payload_json = ?, payload_hash = ?, updated_at = ?
                   WHERE message_id = ? AND status = 'SENDING'""",
                (updated.model_dump_json(), _canonical_hash(updated), now, message_id),
            )
            self._conn.commit()
            return cursor.rowcount == 1

    def mark_outbox_failed(self, message_id: str, error: str) -> bool:
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                """SELECT retry_count, max_retries, backoff_base_ms, payload_json
                   FROM event_outbox WHERE message_id = ?""",
                (message_id,),
            ).fetchone()
            if row is None:
                return False
            msg = PendingMessage.model_validate_json(row["payload_json"])
            new_count = int(row["retry_count"]) + 1
            if new_count >= int(row["max_retries"]):
                new_status = MessageStatus.DEAD_LETTER
                next_attempt = None
            else:
                new_status = MessageStatus.RETRY_WAIT
                backoff_ms = int(row["backoff_base_ms"]) * (2 ** (new_count - 1))
                next_attempt = datetime.now(UTC) + timedelta(milliseconds=backoff_ms)
            updated = msg.model_copy(
                update={
                    "status": new_status,
                    "retry_count": new_count,
                    "last_error": error,
                    "next_retry_at": next_attempt,
                },
                deep=True,
            )
            self._conn.execute(
                """UPDATE event_outbox
                   SET status = ?, retry_count = ?, last_error = ?, next_attempt_at = ?,
                       payload_json = ?, payload_hash = ?, updated_at = ?
                   WHERE message_id = ?""",
                (
                    new_status.value,
                    new_count,
                    error,
                    next_attempt.isoformat() if next_attempt else None,
                    updated.model_dump_json(),
                    _canonical_hash(updated),
                    now,
                    message_id,
                ),
            )
            self._conn.commit()
            return True

    def list_pending_outbox(self, task_id: str | None = None) -> list[PendingMessage]:
        if task_id is None:
            rows = self._conn.execute(
                """SELECT payload_json FROM event_outbox
                   WHERE status IN ('PENDING', 'RETRY_WAIT') ORDER BY id"""
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT payload_json FROM event_outbox
                   WHERE status IN ('PENDING', 'RETRY_WAIT') AND task_id = ? ORDER BY id""",
                (task_id,),
            ).fetchall()
        return [PendingMessage.model_validate_json(r["payload_json"]) for r in rows]

    # ── Version Management ──────────────────────────────────────────────

    def advance_plan_version_if_current(
        self,
        task_id: str,
        expected_plan_version: int,
        expected_command_seq: int,
        new_plan_version: int,
        new_command_seq: int,
    ) -> bool:
        if new_plan_version <= expected_plan_version or new_command_seq <= expected_command_seq:
            return False
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                "SELECT plan_version, command_seq FROM plan_versions WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    """INSERT INTO plan_versions
                       (task_id, plan_version, command_seq, updated_at)
                       VALUES (?, ?, ?, ?)""",
                    (task_id, expected_plan_version, expected_command_seq, now),
                )
            elif (
                int(row["plan_version"]) != expected_plan_version
                or int(row["command_seq"]) != expected_command_seq
            ):
                self._conn.commit()
                return False
            cursor = self._conn.execute(
                """UPDATE plan_versions
                   SET plan_version = ?, command_seq = ?, updated_at = ?
                   WHERE task_id = ? AND plan_version = ? AND command_seq = ?""",
                (
                    new_plan_version,
                    new_command_seq,
                    now,
                    task_id,
                    expected_plan_version,
                    expected_command_seq,
                ),
            )
            self._conn.commit()
            return cursor.rowcount == 1

    # ── Audit/Lifecycle ─────────────────────────────────────────────────

    def record_audit_event(self, task_id: str, event_type: str, details: dict[str, object]) -> None:
        now = _iso_now()
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO event_audit_events
                   (task_id, event_type, details_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (task_id, event_type, self._json(details), now),
            )
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()
