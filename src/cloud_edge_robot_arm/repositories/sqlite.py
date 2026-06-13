from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from cloud_edge_robot_arm.contracts import TaskContract
from cloud_edge_robot_arm.repositories.base import TaskRepository
from cloud_edge_robot_arm.repositories.models import (
    AcceptedCommandDecision,
    AcceptedCommandRecord,
    ActionExecutionRecord,
    AuditEventRecord,
    StateTransitionRecord,
    StepExecutionRecord,
    TaskRecord,
    utc_now,
)


def _to_iso(value: datetime) -> str:
    return value.isoformat()


def _from_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SQLiteRepository(TaskRepository):
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._create_schema()

    def create_task_from_contract(self, contract: TaskContract) -> TaskRecord:
        now = utc_now()
        existing = self.get_task(contract.task_id)
        created_at = existing.created_at if existing is not None else now
        record = TaskRecord(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            state="CREATED",
            contract_json=contract.model_dump_json(),
            created_at=created_at,
            updated_at=now,
        )
        self._connection.execute(
            """
            INSERT INTO tasks (
                task_id, plan_version, command_seq, state, contract_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                plan_version = excluded.plan_version,
                command_seq = excluded.command_seq,
                state = excluded.state,
                contract_json = excluded.contract_json,
                updated_at = excluded.updated_at
            """,
            (
                record.task_id,
                record.plan_version,
                record.command_seq,
                record.state,
                record.contract_json,
                _to_iso(record.created_at),
                _to_iso(record.updated_at),
            ),
        )
        self._connection.commit()
        return record

    def get_task(self, task_id: str) -> TaskRecord | None:
        row = self._connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        return self._task_from_row(row)

    def update_task_state(self, task_id: str, state: str) -> None:
        self._connection.execute(
            "UPDATE tasks SET state = ?, updated_at = ? WHERE task_id = ?",
            (state, _to_iso(utc_now()), task_id),
        )
        self._connection.commit()

    def list_tasks_by_state(self, state: str) -> list[TaskRecord]:
        rows = self._connection.execute(
            "SELECT * FROM tasks WHERE state = ? ORDER BY created_at",
            (state,),
        ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def record_state_transition(
        self,
        *,
        task_id: str,
        from_state: str,
        to_state: str,
        reason: str,
    ) -> StateTransitionRecord:
        record = StateTransitionRecord(
            task_id=task_id,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
        )
        self._connection.execute(
            """
            INSERT INTO task_state_transitions (
                task_id, from_state, to_state, reason, timestamp
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.task_id,
                record.from_state,
                record.to_state,
                record.reason,
                _to_iso(record.timestamp),
            ),
        )
        self.update_task_state(task_id, to_state)
        return record

    def list_state_transitions(self, task_id: str) -> list[StateTransitionRecord]:
        rows = self._connection.execute(
            "SELECT * FROM task_state_transitions WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [self._transition_from_row(row) for row in rows]

    def record_step_execution(self, record: StepExecutionRecord) -> StepExecutionRecord:
        self._connection.execute(
            """
            INSERT INTO step_executions (
                task_id, step_id, skill, attempt, success, error_code, duration_ms, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.task_id,
                record.step_id,
                record.skill,
                record.attempt,
                int(record.success),
                record.error_code,
                record.duration_ms,
                _to_iso(record.timestamp),
            ),
        )
        self._connection.commit()
        return record

    def list_step_executions(self, task_id: str) -> list[StepExecutionRecord]:
        rows = self._connection.execute(
            "SELECT * FROM step_executions WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [self._step_from_row(row) for row in rows]

    def record_action_execution(self, record: ActionExecutionRecord) -> ActionExecutionRecord:
        self._connection.execute(
            """
            INSERT INTO action_executions (
                task_id,
                step_id,
                action_id,
                action_type,
                success,
                error_code,
                duration_ms,
                timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.task_id,
                record.step_id,
                record.action_id,
                record.action_type,
                int(record.success),
                record.error_code,
                record.duration_ms,
                _to_iso(record.timestamp),
            ),
        )
        self._connection.commit()
        return record

    def list_action_executions(self, task_id: str) -> list[ActionExecutionRecord]:
        rows = self._connection.execute(
            "SELECT * FROM action_executions WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [self._action_from_row(row) for row in rows]

    def accept_command(
        self,
        contract: TaskContract,
        *,
        payload_hash: str,
    ) -> AcceptedCommandDecision:
        existing = self._connection.execute(
            """
            SELECT * FROM accepted_commands
            WHERE task_id = ? AND command_seq = ?
            """,
            (contract.task_id, contract.command_seq),
        ).fetchone()
        if existing is not None:
            existing_hash = str(existing["payload_hash"])
            if existing_hash == payload_hash:
                return AcceptedCommandDecision(
                    accepted=False,
                    code="COMMAND_SEQ_REPLAYED",
                    message="command_seq has already been accepted for this task",
                    existing_hash=existing_hash,
                )
            return AcceptedCommandDecision(
                accepted=False,
                code="COMMAND_SEQ_CONFLICT",
                message="command_seq was reused with a different payload",
                existing_hash=existing_hash,
            )

        last = self._connection.execute(
            """
            SELECT MAX(command_seq) AS max_seq, MAX(plan_version) AS max_plan
            FROM accepted_commands
            WHERE task_id = ?
            """,
            (contract.task_id,),
        ).fetchone()
        if last is not None and last["max_seq"] is not None:
            if contract.command_seq <= int(last["max_seq"]):
                return AcceptedCommandDecision(
                    accepted=False,
                    code="COMMAND_SEQ_REPLAYED",
                    message="command_seq is not greater than the last accepted sequence",
                )
            if contract.plan_version < int(last["max_plan"]):
                return AcceptedCommandDecision(
                    accepted=False,
                    code="STALE_PLAN_VERSION",
                    message="plan_version is older than the last accepted command",
                )

        record = AcceptedCommandRecord(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            payload_hash=payload_hash,
        )
        self._connection.execute(
            """
            INSERT INTO accepted_commands (
                task_id, plan_version, command_seq, payload_hash, accepted_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.task_id,
                record.plan_version,
                record.command_seq,
                record.payload_hash,
                _to_iso(record.accepted_at),
            ),
        )
        self._connection.commit()
        return AcceptedCommandDecision(
            accepted=True,
            code="ACCEPTED",
            message="command accepted",
        )

    def record_audit_event(
        self,
        *,
        task_id: str,
        event_type: str,
        details: dict[str, object] | None = None,
    ) -> AuditEventRecord:
        record = AuditEventRecord(
            task_id=task_id,
            event_type=event_type,
            details=dict(details or {}),
        )
        self._connection.execute(
            """
            INSERT INTO audit_events (task_id, event_type, details_json, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (
                record.task_id,
                record.event_type,
                json.dumps(record.details, sort_keys=True),
                _to_iso(record.timestamp),
            ),
        )
        self._connection.commit()
        return record

    def list_audit_events(self, task_id: str) -> list[AuditEventRecord]:
        rows = self._connection.execute(
            "SELECT * FROM audit_events WHERE task_id = ? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [self._audit_from_row(row) for row in rows]

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                state TEXT NOT NULL,
                contract_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_state_transitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS step_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                skill TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                success INTEGER NOT NULL,
                error_code TEXT,
                duration_ms INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS action_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                step_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                success INTEGER NOT NULL,
                error_code TEXT,
                duration_ms INTEGER NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS accepted_commands (
                task_id TEXT NOT NULL,
                plan_version INTEGER NOT NULL,
                command_seq INTEGER NOT NULL,
                payload_hash TEXT NOT NULL,
                accepted_at TEXT NOT NULL,
                PRIMARY KEY (task_id, command_seq)
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            """
        )
        self._connection.commit()

    def _task_from_row(self, row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=str(row["task_id"]),
            plan_version=int(row["plan_version"]),
            command_seq=int(row["command_seq"]),
            state=str(row["state"]),
            contract_json=str(row["contract_json"]),
            created_at=_from_iso(str(row["created_at"])),
            updated_at=_from_iso(str(row["updated_at"])),
        )

    def _transition_from_row(self, row: sqlite3.Row) -> StateTransitionRecord:
        return StateTransitionRecord(
            task_id=str(row["task_id"]),
            from_state=str(row["from_state"]),
            to_state=str(row["to_state"]),
            reason=str(row["reason"]),
            timestamp=_from_iso(str(row["timestamp"])),
        )

    def _step_from_row(self, row: sqlite3.Row) -> StepExecutionRecord:
        return StepExecutionRecord(
            task_id=str(row["task_id"]),
            step_id=str(row["step_id"]),
            skill=str(row["skill"]),
            attempt=int(row["attempt"]),
            success=bool(row["success"]),
            error_code=row["error_code"],
            duration_ms=int(row["duration_ms"]),
            timestamp=_from_iso(str(row["timestamp"])),
        )

    def _action_from_row(self, row: sqlite3.Row) -> ActionExecutionRecord:
        return ActionExecutionRecord(
            task_id=str(row["task_id"]),
            step_id=str(row["step_id"]),
            action_id=str(row["action_id"]),
            action_type=str(row["action_type"]),
            success=bool(row["success"]),
            error_code=row["error_code"],
            duration_ms=int(row["duration_ms"]),
            timestamp=_from_iso(str(row["timestamp"])),
        )

    def _audit_from_row(self, row: sqlite3.Row) -> AuditEventRecord:
        return AuditEventRecord(
            task_id=str(row["task_id"]),
            event_type=str(row["event_type"]),
            details=json.loads(str(row["details_json"])),
            timestamp=_from_iso(str(row["timestamp"])),
        )
