"""SQLite-backed EventAutonomyRepository — production-grade persistence.

Follows the SQLiteSupervisionRepository pattern from
cloud/supervision/repository.py. Uses WAL mode, CAS via rowcount checks,
and 11 tables with unique constraints and indices.

All datetime columns use ISO 8601 UTC text.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock

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


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


class SQLiteEventAutonomyRepository:
    """SQLite-backed persistent repository with CAS semantics.

    Uses WAL journal mode for concurrent reads. Write operations are
    serialized by a threading.Lock. CAS operations use UPDATE ... WHERE
    with rowcount checks to prevent:
    - Double event handling (event_id UNIQUE)
    - Double budget consumption (retry_count_used == expected_count check)
    - Concurrent replan version bumps (MAX(new_plan_version) check)
    - Old results overwriting new (advance_plan_version_if_current CAS)
    - Double outbox claiming (PENDING -> SENDING atomic transition)
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._write_lock = Lock()
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript("""
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
                handled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_edge_events_task
                ON edge_events(task_id);

            CREATE TABLE IF NOT EXISTS recovery_budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                budget_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL UNIQUE,
                per_step_retry_limit INTEGER NOT NULL DEFAULT 3,
                per_skill_retry_limit INTEGER NOT NULL DEFAULT 5,
                task_total_retry_limit INTEGER NOT NULL DEFAULT 10,
                retry_count_used INTEGER NOT NULL DEFAULT 0,
                retry_cooldown_ms INTEGER NOT NULL DEFAULT 500,
                retry_deadline TEXT,
                retry_backoff_policy TEXT NOT NULL DEFAULT 'exponential',
                effective_retry_limit INTEGER NOT NULL DEFAULT 3,
                remaining_retries INTEGER NOT NULL DEFAULT 3,
                scene_version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recovery_budgets_task
                ON recovery_budgets(task_id);

            CREATE TABLE IF NOT EXISTS recovery_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                skill TEXT NOT NULL,
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
            CREATE INDEX IF NOT EXISTS idx_event_mode_states_task
                ON event_mode_states(task_id);

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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_failure_summaries_task
                ON failure_summaries(task_id);

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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_replan_requests_idempotency
                ON replan_requests(idempotency_key)
                WHERE idempotency_key IS NOT NULL AND idempotency_key != '';
            CREATE INDEX IF NOT EXISTS idx_replan_requests_task
                ON replan_requests(task_id);

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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_replan_results_task
                ON replan_results(task_id);

            CREATE TABLE IF NOT EXISTS event_outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT,
                task_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
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
            CREATE INDEX IF NOT EXISTS idx_event_outbox_task
                ON event_outbox(task_id);
            CREATE INDEX IF NOT EXISTS idx_event_outbox_status
                ON event_outbox(status);
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
            CREATE INDEX IF NOT EXISTS idx_event_audit_events_task
                ON event_audit_events(task_id);

            CREATE TABLE IF NOT EXISTS plan_versions (
                task_id TEXT PRIMARY KEY,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        self._conn.commit()

    # ── Events ──────────────────────────────────────────────────────────

    def save_event(self, event: EdgeEvent) -> EdgeEvent:
        payload = event.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            try:
                self._conn.execute(
                    """INSERT INTO edge_events (
                        event_id, task_id, event_type, step_id, severity,
                        reason_code, reason_detail, robot_id, plan_id,
                        plan_version, command_seq, details_json,
                        payload_json, handled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                    (
                        event.event_id,
                        event.task_id,
                        event.event_type.value,
                        event.step_id,
                        event.severity,
                        event.reason_code,
                        event.reason_detail,
                        event.robot_id,
                        event.plan_id,
                        event.plan_version,
                        event.command_seq,
                        json.dumps(event.details, default=str),
                        payload,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.commit()
        return self.get_event(event.event_id) or event

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
                    task_total_retry_limit, retry_count_used, retry_cooldown_ms,
                    retry_deadline, retry_backoff_policy, effective_retry_limit,
                    remaining_retries, scene_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    per_step_retry_limit = excluded.per_step_retry_limit,
                    per_skill_retry_limit = excluded.per_skill_retry_limit,
                    task_total_retry_limit = excluded.task_total_retry_limit,
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
            """SELECT budget_id, task_id, per_step_retry_limit, per_skill_retry_limit,
                      task_total_retry_limit, retry_count_used, retry_cooldown_ms,
                      retry_deadline, retry_backoff_policy, effective_retry_limit,
                      remaining_retries, scene_version, created_at, updated_at
               FROM recovery_budgets WHERE task_id = ?""",
            (task_id,),
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
            retry_cooldown_ms=row["retry_cooldown_ms"],
            retry_deadline=(
                datetime.fromisoformat(row["retry_deadline"]) if row["retry_deadline"] else None
            ),
            retry_backoff_policy=row["retry_backoff_policy"],
            effective_retry_limit=row["effective_retry_limit"],
            remaining_retries=row["remaining_retries"],
            scene_version=row["scene_version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def consume_retry_if_available(
        self, task_id: str, step_id: str, skill: str, expected_count: int
    ) -> tuple[bool, RecoveryBudget | None]:
        now = _iso_now()
        with self._write_lock:
            cursor = self._conn.execute(
                """UPDATE recovery_budgets
                   SET retry_count_used = retry_count_used + 1,
                       remaining_retries = remaining_retries - 1,
                       updated_at = ?
                   WHERE task_id = ?
                     AND retry_count_used = ?
                     AND remaining_retries > 0""",
                (now, task_id, expected_count),
            )
            if cursor.rowcount != 1:
                self._conn.commit()
                return False, self.get_retry_budget(task_id)
            self._conn.execute(
                """INSERT INTO recovery_attempts
                   (task_id, step_id, skill, attempt_number, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (task_id, step_id, skill, expected_count + 1, now),
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
        return [
            {
                "from_state": r["from_state"],
                "to_state": r["to_state"],
                "reason": r["reason"],
                "event_id": r["event_id"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # ── Failure Summary ─────────────────────────────────────────────────

    def save_failure_summary(self, summary: FailureSummary) -> FailureSummary:
        payload = summary.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            try:
                self._conn.execute(
                    """INSERT INTO failure_summaries (
                        summary_id, task_id, failure_event_id, failed_step_id,
                        completed_step_ids_json, failure_type, severity, reason,
                        recovery_hint, local_retry_count, retry_limit,
                        requested_replan_scope, plan_version, command_seq,
                        payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        summary.summary_id,
                        summary.task_id,
                        summary.failure_event_id,
                        summary.failed_step_id,
                        json.dumps(summary.completed_step_ids),
                        summary.failure_type,
                        summary.severity,
                        summary.reason,
                        summary.recovery_hint,
                        summary.local_retry_count,
                        summary.retry_limit,
                        summary.requested_replan_scope,
                        summary.plan_version,
                        summary.command_seq,
                        payload,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.commit()
        return self.get_failure_summary(summary.summary_id) or summary

    def get_failure_summary(self, summary_id: str) -> FailureSummary | None:
        row = self._conn.execute(
            "SELECT payload_json FROM failure_summaries WHERE summary_id = ?",
            (summary_id,),
        ).fetchone()
        return None if row is None else FailureSummary.model_validate_json(row["payload_json"])

    # ── Completion Summary ──────────────────────────────────────────────

    def save_completion_summary(self, summary: CompletionSummary) -> CompletionSummary:
        payload = summary.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            try:
                self._conn.execute(
                    """INSERT INTO completion_summaries (
                        summary_id, task_id, final_plan_version,
                        completed_step_ids_json, completion_criteria_results_json,
                        local_retry_count, cloud_replan_count,
                        result, final_safety_decision,
                        plan_version, command_seq,
                        payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        summary.summary_id,
                        summary.task_id,
                        summary.final_plan_version,
                        json.dumps(summary.completed_step_ids),
                        json.dumps(summary.completion_criteria_results),
                        summary.local_retry_count,
                        summary.cloud_replan_count,
                        summary.result,
                        summary.final_safety_decision,
                        summary.plan_version,
                        summary.command_seq,
                        payload,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.commit()
        return self.get_completion_summary(summary.summary_id) or summary

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

    # ── Replan ──────────────────────────────────────────────────────────

    def save_replan_request(self, request: LocalReplanningRequest) -> LocalReplanningRequest:
        payload = request.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            try:
                self._conn.execute(
                    """INSERT INTO replan_requests (
                        request_id, idempotency_key, task_id, trigger_event_id,
                        failure_summary_id, current_plan_version, current_command_seq,
                        requested_replan_scope, completed_step_ids_json,
                        failed_step_id, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        request.request_id,
                        request.idempotency_key or None,
                        request.task_id,
                        request.trigger_event_id,
                        request.failure_summary_id,
                        request.current_plan_version,
                        request.current_command_seq,
                        request.requested_replan_scope,
                        json.dumps(request.completed_step_ids),
                        request.failed_step_id,
                        payload,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.commit()
        return self.get_replan_request(request.request_id) or request

    def get_replan_request(self, request_id: str) -> LocalReplanningRequest | None:
        row = self._conn.execute(
            "SELECT payload_json FROM replan_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        return (
            None if row is None else LocalReplanningRequest.model_validate_json(row["payload_json"])
        )

    def save_replan_result(self, result: LocalReplanningResponse) -> LocalReplanningResponse:
        payload = result.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            task_id = _extract_task_id(result)
            try:
                self._conn.execute(
                    """INSERT INTO replan_results (
                        request_id, task_id, outcome, new_plan_version,
                        new_command_seq, new_steps_json,
                        validation_errors_json, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        result.request_id,
                        task_id,
                        result.outcome,
                        result.new_plan_version,
                        result.new_command_seq,
                        json.dumps([s.model_dump(mode="json") for s in result.new_steps]),
                        json.dumps(result.validation_errors),
                        payload,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.commit()
        return self.get_replan_result(result.request_id) or result

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

    # ── Outbox ──────────────────────────────────────────────────────────

    def enqueue_outbox(self, message: PendingMessage) -> PendingMessage:
        payload = message.model_dump_json()
        now = _iso_now()
        with self._write_lock:
            try:
                self._conn.execute(
                    """INSERT INTO event_outbox (
                        message_id, idempotency_key, task_id, message_type, payload_json,
                        status, retry_count, max_retries, backoff_base_ms,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        message.message_id,
                        message.idempotency_key or message.message_id,
                        message.task_id,
                        message.message_type,
                        payload,
                        MessageStatus.PENDING.value,
                        message.retry_count,
                        message.max_retries,
                        message.backoff_base_ms,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.commit()
        return message

    def claim_outbox_message(self) -> PendingMessage | None:
        now = _iso_now()
        with self._write_lock:
            row = self._conn.execute(
                """SELECT payload_json FROM event_outbox
                   WHERE status IN ('PENDING', 'RETRY_WAIT')
                     AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                   ORDER BY id LIMIT 1""",
                (now,),
            ).fetchone()
            if row is None:
                return None
            msg = PendingMessage.model_validate_json(row["payload_json"])
            # Update both status column AND payload_json to keep them in sync
            import json as _json

            payload_dict = _json.loads(row["payload_json"])
            payload_dict["status"] = "SENDING"
            updated_payload = _json.dumps(payload_dict, default=str)
            cursor = self._conn.execute(
                """UPDATE event_outbox
                   SET status = 'SENDING', claimed_at = ?, payload_json = ?, updated_at = ?
                   WHERE message_id = ? AND status IN ('PENDING', 'RETRY_WAIT')""",
                (now, updated_payload, now, msg.message_id),
            )
            self._conn.commit()
            if cursor.rowcount != 1:
                return None
            return PendingMessage.model_validate_json(updated_payload)

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
            import json as _json

            payload_dict = _json.loads(row["payload_json"])
            payload_dict["status"] = "SENT"
            updated_payload = _json.dumps(payload_dict, default=str)
            cursor = self._conn.execute(
                """UPDATE event_outbox
                   SET status = 'SENT', payload_json = ?, updated_at = ?
                   WHERE message_id = ? AND status = 'SENDING'""",
                (updated_payload, now, message_id),
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
            import json as _json

            new_count = int(row["retry_count"]) + 1
            max_retries = int(row["max_retries"])
            if new_count >= max_retries:
                new_status = "DEAD_LETTER"
                next_attempt = None
            else:
                new_status = "RETRY_WAIT"
                backoff_ms = int(row["backoff_base_ms"]) * (2 ** (new_count - 1))
                next_attempt = (datetime.now(UTC) + timedelta(milliseconds=backoff_ms)).isoformat()
            payload_dict = _json.loads(row["payload_json"])
            payload_dict["status"] = new_status
            payload_dict["retry_count"] = new_count
            payload_dict["last_error"] = error
            payload_dict["next_retry_at"] = next_attempt
            updated_payload = _json.dumps(payload_dict, default=str)
            self._conn.execute(
                """UPDATE event_outbox
                   SET status = ?, retry_count = ?, last_error = ?,
                       next_attempt_at = ?, payload_json = ?, updated_at = ?
                   WHERE message_id = ?""",
                (new_status, new_count, error, next_attempt, updated_payload, now, message_id),
            )
            self._conn.commit()
            return True

    def list_pending_outbox(self, task_id: str | None = None) -> list[PendingMessage]:
        if task_id is not None:
            rows = self._conn.execute(
                """SELECT payload_json FROM event_outbox
                   WHERE status IN ('PENDING', 'RETRY_WAIT') AND task_id = ?
                   ORDER BY id""",
                (task_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT payload_json FROM event_outbox
                   WHERE status IN ('PENDING', 'RETRY_WAIT')
                   ORDER BY id""",
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
                   WHERE task_id = ?
                     AND plan_version = ?
                     AND command_seq = ?""",
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

    # ── Audit ───────────────────────────────────────────────────────────

    def record_audit_event(self, task_id: str, event_type: str, details: dict[str, object]) -> None:
        now = _iso_now()
        with self._write_lock:
            self._conn.execute(
                """INSERT INTO event_audit_events (task_id, event_type, details_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (task_id, event_type, json.dumps(details, default=str), now),
            )
            self._conn.commit()

    # ── Lifecycle ───────────────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()


def _extract_task_id(result: LocalReplanningResponse) -> str:
    """Extract task_id from request_id convention: replan-req-{task_id}-...
    Falls back to empty string if format doesn't match."""
    parts = result.request_id.split("-")
    if len(parts) >= 3 and parts[0] == "replan" and parts[1] == "req":
        return parts[2]
    return ""
