"""仓储接口或实现，隔离业务服务与底层存储细节。

Persistence for periodic cloud supervision state.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Protocol, runtime_checkable

from cloud_edge_robot_arm.cloud.supervision.models import EdgeStatusSnapshot, SupervisoryDecision
from cloud_edge_robot_arm.contracts import TaskContract


@dataclass(frozen=True)
class SupervisionTaskStatus:
    task_id: str
    running: bool
    last_plan_version: int
    last_command_seq: int
    contract: TaskContract | None = None
    updated_at: datetime | None = None


@runtime_checkable
class SupervisionRepository(Protocol):
    def start_task(self, contract: TaskContract) -> SupervisionTaskStatus: ...

    def stop_task(self, task_id: str) -> SupervisionTaskStatus | None: ...

    def get_status(self, task_id: str) -> SupervisionTaskStatus | None: ...

    def get_contract(self, task_id: str) -> TaskContract | None: ...

    def save_snapshot(self, snapshot: EdgeStatusSnapshot) -> None: ...

    def latest_snapshot(self, task_id: str) -> EdgeStatusSnapshot | None: ...

    def list_snapshots(self, task_id: str) -> list[EdgeStatusSnapshot]: ...

    def save_decision(self, decision: SupervisoryDecision) -> None: ...

    def list_decisions(self, task_id: str) -> list[SupervisoryDecision]: ...

    def record_audit_event(self, task_id: str, event: dict[str, object]) -> None: ...

    def list_audit_events(self, task_id: str) -> list[dict[str, object]]: ...

    def advance_version_if_current(
        self,
        *,
        task_id: str,
        expected_plan_version: int,
        expected_command_seq: int,
        new_plan_version: int,
        new_command_seq: int,
    ) -> bool: ...

    def close(self) -> None: ...


class InMemorySupervisionRepository:
    def __init__(self) -> None:
        self._statuses: dict[str, SupervisionTaskStatus] = {}
        self._snapshots: dict[str, list[EdgeStatusSnapshot]] = {}
        self._decisions: dict[str, list[SupervisoryDecision]] = {}
        self._audit_events: dict[str, list[dict[str, object]]] = {}
        self._lock = Lock()

    def start_task(self, contract: TaskContract) -> SupervisionTaskStatus:
        with self._lock:
            existing = self._statuses.get(contract.task_id)
            status = SupervisionTaskStatus(
                task_id=contract.task_id,
                running=True,
                last_plan_version=contract.plan_version
                if existing is None
                else max(existing.last_plan_version, contract.plan_version),
                last_command_seq=contract.command_seq
                if existing is None
                else max(existing.last_command_seq, contract.command_seq),
                contract=contract,
            )
            self._statuses[contract.task_id] = status
            return status

    def stop_task(self, task_id: str) -> SupervisionTaskStatus | None:
        with self._lock:
            existing = self._statuses.get(task_id)
            if existing is None:
                return None
            status = replace(existing, running=False)
            self._statuses[task_id] = status
            return status

    def get_status(self, task_id: str) -> SupervisionTaskStatus | None:
        return self._statuses.get(task_id)

    def get_contract(self, task_id: str) -> TaskContract | None:
        status = self._statuses.get(task_id)
        return status.contract if status is not None else None

    def save_snapshot(self, snapshot: EdgeStatusSnapshot) -> None:
        with self._lock:
            self._snapshots.setdefault(snapshot.task_id, []).append(snapshot)

    def latest_snapshot(self, task_id: str) -> EdgeStatusSnapshot | None:
        snapshots = self._snapshots.get(task_id, [])
        return snapshots[-1] if snapshots else None

    def list_snapshots(self, task_id: str) -> list[EdgeStatusSnapshot]:
        return list(self._snapshots.get(task_id, []))

    def save_decision(self, decision: SupervisoryDecision) -> None:
        with self._lock:
            self._decisions.setdefault(decision.task_id, []).append(decision)
            existing = self._statuses.get(decision.task_id)
            if existing is not None:
                self._statuses[decision.task_id] = replace(
                    existing,
                    last_plan_version=decision.resulting_plan_version,
                    last_command_seq=decision.command_seq,
                )

    def list_decisions(self, task_id: str) -> list[SupervisoryDecision]:
        return list(self._decisions.get(task_id, []))

    def record_audit_event(self, task_id: str, event: dict[str, object]) -> None:
        with self._lock:
            self._audit_events.setdefault(task_id, []).append(dict(event))

    def list_audit_events(self, task_id: str) -> list[dict[str, object]]:
        return list(self._audit_events.get(task_id, []))

    def advance_version_if_current(
        self,
        *,
        task_id: str,
        expected_plan_version: int,
        expected_command_seq: int,
        new_plan_version: int,
        new_command_seq: int,
    ) -> bool:
        with self._lock:
            existing = self._statuses.get(task_id)
            if existing is None:
                return False
            if (
                existing.last_plan_version != expected_plan_version
                or existing.last_command_seq != expected_command_seq
            ):
                return False
            self._statuses[task_id] = replace(
                existing,
                last_plan_version=new_plan_version,
                last_command_seq=new_command_seq,
            )
            return True

    def close(self) -> None:
        return None


class SQLiteSupervisionRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._create_schema()

    def start_task(self, contract: TaskContract) -> SupervisionTaskStatus:
        payload = contract.model_dump_json()
        self._connection.execute(
            """
            INSERT INTO supervision_tasks (
                task_id, running, last_plan_version, last_command_seq, contract_json, updated_at
            )
            VALUES (?, 1, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                running = 1,
                last_plan_version = MAX(last_plan_version, excluded.last_plan_version),
                last_command_seq = MAX(last_command_seq, excluded.last_command_seq),
                contract_json = excluded.contract_json,
                updated_at = excluded.updated_at
            """,
            (
                contract.task_id,
                contract.plan_version,
                contract.command_seq,
                payload,
                _iso_now(),
            ),
        )
        self._connection.commit()
        status = self.get_status(contract.task_id)
        assert status is not None
        return status

    def stop_task(self, task_id: str) -> SupervisionTaskStatus | None:
        self._connection.execute(
            "UPDATE supervision_tasks SET running = 0, updated_at = ? WHERE task_id = ?",
            (_iso_now(), task_id),
        )
        self._connection.commit()
        return self.get_status(task_id)

    def get_status(self, task_id: str) -> SupervisionTaskStatus | None:
        row = self._connection.execute(
            "SELECT * FROM supervision_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        return None if row is None else _status_from_row(row)

    def get_contract(self, task_id: str) -> TaskContract | None:
        status = self.get_status(task_id)
        return None if status is None else status.contract

    def save_snapshot(self, snapshot: EdgeStatusSnapshot) -> None:
        self._connection.execute(
            """
            INSERT INTO supervision_snapshots (task_id, robot_id, scene_version, payload_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                snapshot.task_id,
                snapshot.robot_id,
                snapshot.scene_version,
                snapshot.model_dump_json(),
            ),
        )
        self._connection.commit()

    def latest_snapshot(self, task_id: str) -> EdgeStatusSnapshot | None:
        row = self._connection.execute(
            """
            SELECT payload_json FROM supervision_snapshots
            WHERE task_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        return None if row is None else EdgeStatusSnapshot.model_validate_json(row["payload_json"])

    def list_snapshots(self, task_id: str) -> list[EdgeStatusSnapshot]:
        rows = self._connection.execute(
            """
            SELECT payload_json FROM supervision_snapshots
            WHERE task_id = ?
            ORDER BY id
            """,
            (task_id,),
        ).fetchall()
        return [EdgeStatusSnapshot.model_validate_json(row["payload_json"]) for row in rows]

    def save_decision(self, decision: SupervisoryDecision) -> None:
        self._connection.execute(
            """
            INSERT OR IGNORE INTO supervision_decisions (
                decision_id, task_id, robot_id, input_state_hash, command_seq, payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.task_id,
                decision.robot_id,
                decision.input_state_hash,
                decision.command_seq,
                decision.model_dump_json(),
            ),
        )
        self._connection.execute(
            """
            UPDATE supervision_tasks
            SET last_plan_version = ?, last_command_seq = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (
                decision.resulting_plan_version,
                decision.command_seq,
                _iso_now(),
                decision.task_id,
            ),
        )
        self._connection.commit()

    def list_decisions(self, task_id: str) -> list[SupervisoryDecision]:
        rows = self._connection.execute(
            """
            SELECT payload_json FROM supervision_decisions
            WHERE task_id = ?
            ORDER BY id
            """,
            (task_id,),
        ).fetchall()
        return [SupervisoryDecision.model_validate_json(row["payload_json"]) for row in rows]

    def record_audit_event(self, task_id: str, event: dict[str, object]) -> None:
        self._connection.execute(
            """
            INSERT INTO supervision_audit_events (task_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                task_id,
                str(event.get("event_type", "")),
                json.dumps(event, default=str, sort_keys=True),
                _iso_now(),
            ),
        )
        self._connection.commit()

    def list_audit_events(self, task_id: str) -> list[dict[str, object]]:
        rows = self._connection.execute(
            """
            SELECT payload_json FROM supervision_audit_events
            WHERE task_id = ?
            ORDER BY id
            """,
            (task_id,),
        ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def advance_version_if_current(
        self,
        *,
        task_id: str,
        expected_plan_version: int,
        expected_command_seq: int,
        new_plan_version: int,
        new_command_seq: int,
    ) -> bool:
        cursor = self._connection.execute(
            """
            UPDATE supervision_tasks
            SET last_plan_version = ?, last_command_seq = ?, updated_at = ?
            WHERE task_id = ?
              AND last_plan_version = ?
              AND last_command_seq = ?
            """,
            (
                new_plan_version,
                new_command_seq,
                _iso_now(),
                task_id,
                expected_plan_version,
                expected_command_seq,
            ),
        )
        self._connection.commit()
        return cursor.rowcount == 1

    def close(self) -> None:
        self._connection.close()

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS supervision_tasks (
                task_id TEXT PRIMARY KEY,
                running INTEGER NOT NULL,
                last_plan_version INTEGER NOT NULL,
                last_command_seq INTEGER NOT NULL,
                contract_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supervision_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                scene_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supervision_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id TEXT NOT NULL UNIQUE,
                task_id TEXT NOT NULL,
                robot_id TEXT NOT NULL,
                input_state_hash TEXT NOT NULL,
                command_seq INTEGER NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS supervision_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_supervision_snapshots_task
                ON supervision_snapshots(task_id, id);
            CREATE INDEX IF NOT EXISTS idx_supervision_decisions_task
                ON supervision_decisions(task_id, id);
            CREATE INDEX IF NOT EXISTS idx_supervision_audit_task
                ON supervision_audit_events(task_id, id);
            """
        )
        self._connection.commit()


def _status_from_row(row: sqlite3.Row) -> SupervisionTaskStatus:
    return SupervisionTaskStatus(
        task_id=str(row["task_id"]),
        running=bool(row["running"]),
        last_plan_version=int(row["last_plan_version"]),
        last_command_seq=int(row["last_command_seq"]),
        contract=TaskContract.model_validate_json(row["contract_json"]),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _iso_now() -> str:
    return datetime.now().astimezone().isoformat()
