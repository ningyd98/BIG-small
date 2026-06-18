from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from cloud_edge_robot_arm.simulation_runtime.models import (
    RuntimeJobStatus,
    SimulationBatchRecord,
    SimulationJobAttempt,
    SimulationJobEvent,
    SimulationJobLease,
    SimulationJobRecord,
)
from cloud_edge_robot_arm.simulation_runtime.state_machine import validate_transition

SCHEMA_VERSION = 1


class SQLiteSimulationJobRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_job(
        self,
        *,
        run_id: str,
        batch_id: str,
        backend: str,
        scenario_id: str,
        control_mode: str,
        seed: int,
        manifest_id: str,
        reproducibility_hash: str,
        draft: dict[str, object],
        timeout_seconds: int,
        max_attempts: int,
        artifact_root: str,
        source_commit: str,
        source_tree_hash: str,
        manifest: dict[str, object] | None = None,
        provenance: dict[str, object] | None = None,
    ) -> SimulationJobRecord:
        self._initialize()
        now = _now()
        job_id = "job-" + uuid4().hex[:16]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO simulation_jobs (
                    job_id, run_id, batch_id, backend, scenario_id, control_mode, seed,
                    manifest_id, reproducibility_hash, status, draft_json, manifest_json,
                    attempt, max_attempts, priority, created_at, updated_at, timeout_seconds,
                    cancel_requested, artifact_root, source_commit, source_tree_hash,
                    provenance_json, blocker_codes_json, artifact_paths_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    run_id,
                    batch_id,
                    backend,
                    scenario_id,
                    control_mode,
                    seed,
                    manifest_id,
                    reproducibility_hash,
                    RuntimeJobStatus.CREATED.value,
                    _dumps(draft),
                    _dumps(manifest or {}),
                    max_attempts,
                    _dt(now),
                    _dt(now),
                    timeout_seconds,
                    artifact_root,
                    source_commit,
                    source_tree_hash,
                    _dumps(provenance or {}),
                    _dumps([]),
                    _dumps({}),
                ),
            )
        self.append_event(
            job_id,
            event_type="job_created",
            source="simulation_runtime",
            payload={
                "run_id": run_id,
                "backend": backend,
                "status": RuntimeJobStatus.CREATED.value,
            },
            next_status=RuntimeJobStatus.CREATED.value,
            reason_code="created",
        )
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> SimulationJobRecord:
        self._initialize()
        row = self._fetch_one("SELECT * FROM simulation_jobs WHERE job_id = ?", (job_id,))
        if row is None:
            raise KeyError(job_id)
        return _job_from_row(row)

    def get_job_by_run_id(self, run_id: str) -> SimulationJobRecord:
        self._initialize()
        row = self._fetch_one("SELECT * FROM simulation_jobs WHERE run_id = ?", (run_id,))
        if row is None:
            raise KeyError(run_id)
        return _job_from_row(row)

    def list_jobs(self) -> list[SimulationJobRecord]:
        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM simulation_jobs ORDER BY created_at DESC, run_id ASC"
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def update_status_cas(
        self,
        job_id: str,
        *,
        expected: RuntimeJobStatus,
        next_status: RuntimeJobStatus,
        reason_code: str,
        worker_id: str,
        lease_id: str,
        error_code: str = "",
        error_message: str = "",
    ) -> SimulationJobRecord | None:
        self._initialize()
        validate_transition(expected, next_status)
        now = _now()
        updates = [
            "status = ?",
            "updated_at = ?",
            "worker_id = COALESCE(NULLIF(?, ''), worker_id)",
            "lease_id = COALESCE(NULLIF(?, ''), lease_id)",
            "error_code = ?",
            "error_message = ?",
        ]
        params: list[Any] = [
            next_status.value,
            _dt(now),
            worker_id,
            lease_id,
            error_code,
            error_message,
        ]
        if next_status == RuntimeJobStatus.QUEUED:
            updates.append("queued_at = COALESCE(queued_at, ?)")
            params.append(_dt(now))
        if next_status in {RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING}:
            updates.append("started_at = COALESCE(started_at, ?)")
            params.append(_dt(now))
        if next_status in {
            RuntimeJobStatus.SUCCEEDED,
            RuntimeJobStatus.FAILED,
            RuntimeJobStatus.CANCELLED,
            RuntimeJobStatus.TIMED_OUT,
            RuntimeJobStatus.BLOCKED_BY_ENV,
        }:
            updates.append("completed_at = COALESCE(completed_at, ?)")
            params.append(_dt(now))
        params.extend([job_id, expected.value])
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE simulation_jobs SET {", ".join(updates)}
                WHERE job_id = ? AND status = ?
                """,
                tuple(params),
            )
            if cursor.rowcount != 1:
                return None
        self.append_event(
            job_id,
            event_type=_event_type_for_status(next_status),
            source="simulation_runtime",
            payload={"status": next_status.value, "worker_id": worker_id, "lease_id": lease_id},
            previous_status=expected.value,
            next_status=next_status.value,
            reason_code=reason_code,
        )
        return self.get_job(job_id)

    def request_cancel(self, job_id: str) -> SimulationJobRecord:
        self._initialize()
        job = self.get_job(job_id)
        if job.status in {
            RuntimeJobStatus.SUCCEEDED,
            RuntimeJobStatus.FAILED,
            RuntimeJobStatus.CANCELLED,
            RuntimeJobStatus.TIMED_OUT,
            RuntimeJobStatus.BLOCKED_BY_ENV,
        }:
            return job
        with self._connect() as conn:
            conn.execute(
                "UPDATE simulation_jobs SET cancel_requested = 1, updated_at = ? WHERE job_id = ?",
                (_dt(_now()), job_id),
            )
        self.append_event(
            job_id,
            event_type="cancel_requested",
            source="simulation_runtime",
            payload={"requested_at": _dt(_now())},
            reason_code="operator_cancel",
        )
        refreshed = self.get_job(job_id)
        if refreshed.status == RuntimeJobStatus.QUEUED:
            return self.update_status_cas(
                job_id,
                expected=RuntimeJobStatus.QUEUED,
                next_status=RuntimeJobStatus.CANCELLED,
                reason_code="cancelled_before_start",
                worker_id="",
                lease_id="",
            ) or self.get_job(job_id)
        if refreshed.status in {
            RuntimeJobStatus.VALIDATING,
            RuntimeJobStatus.LEASED,
            RuntimeJobStatus.STARTING,
            RuntimeJobStatus.RUNNING,
        }:
            updated = self.update_status_cas(
                job_id,
                expected=refreshed.status,
                next_status=RuntimeJobStatus.CANCEL_REQUESTED,
                reason_code="operator_cancel",
                worker_id=refreshed.worker_id,
                lease_id=refreshed.lease_id,
            )
            if updated is not None:
                return updated
            latest = self.get_job(job_id)
            if latest.status in {
                RuntimeJobStatus.SUCCEEDED,
                RuntimeJobStatus.FAILED,
                RuntimeJobStatus.CANCELLED,
                RuntimeJobStatus.TIMED_OUT,
                RuntimeJobStatus.BLOCKED_BY_ENV,
                RuntimeJobStatus.CANCEL_REQUESTED,
                RuntimeJobStatus.CANCELLING,
            }:
                return latest
            return replace(latest, status=RuntimeJobStatus.CANCEL_REQUESTED)
        return refreshed

    def acquire_lease(
        self, *, worker_id: str, backend: str, lease_ttl_seconds: int
    ) -> SimulationJobLease | None:
        self._initialize()
        now = _now()
        expires_at = now + timedelta(seconds=lease_ttl_seconds)
        lease_id = "lease-" + uuid4().hex[:16]
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT * FROM simulation_jobs
                WHERE backend = ? AND status = ?
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (backend, RuntimeJobStatus.QUEUED.value),
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            job = _job_from_row(row)
            validate_transition(job.status, RuntimeJobStatus.VALIDATING)
            validate_transition(RuntimeJobStatus.VALIDATING, RuntimeJobStatus.LEASED)
            conn.execute(
                """
                UPDATE simulation_jobs
                SET status = ?, updated_at = ?, worker_id = ?, lease_id = ?, lease_expires_at = ?
                WHERE job_id = ? AND status = ?
                """,
                (
                    RuntimeJobStatus.LEASED.value,
                    _dt(now),
                    worker_id,
                    lease_id,
                    _dt(expires_at),
                    job.job_id,
                    RuntimeJobStatus.QUEUED.value,
                ),
            )
            conn.execute(
                """
                INSERT INTO simulation_job_leases (
                    lease_id, job_id, worker_id, acquired_at, expires_at, heartbeat_at, released_at
                ) VALUES (?, ?, ?, ?, ?, ?, '')
                """,
                (lease_id, job.job_id, worker_id, _dt(now), _dt(expires_at), _dt(now)),
            )
            conn.execute("COMMIT")
        self.append_event(
            job.job_id,
            event_type="job_leased",
            source="simulation_runtime",
            payload={"worker_id": worker_id, "lease_id": lease_id},
            previous_status=RuntimeJobStatus.QUEUED.value,
            next_status=RuntimeJobStatus.LEASED.value,
            reason_code="lease_acquired",
        )
        return SimulationJobLease(
            lease_id=lease_id,
            job_id=job.job_id,
            worker_id=worker_id,
            acquired_at=now,
            expires_at=expires_at,
            heartbeat_at=now,
        )

    def heartbeat_lease(self, lease_id: str, *, lease_ttl_seconds: int) -> None:
        self._initialize()
        now = _now()
        expires_at = now + timedelta(seconds=lease_ttl_seconds)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE simulation_job_leases SET heartbeat_at = ?, expires_at = ?
                WHERE lease_id = ? AND released_at = ''
                """,
                (_dt(now), _dt(expires_at), lease_id),
            )
            conn.execute(
                """
                UPDATE simulation_jobs SET lease_expires_at = ?, updated_at = ?
                WHERE lease_id = ?
                """,
                (_dt(expires_at), _dt(now), lease_id),
            )

    def release_lease(self, lease_id: str) -> None:
        self._initialize()
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE simulation_job_leases SET released_at = ? WHERE lease_id = ?",
                (_dt(now), lease_id),
            )

    def expire_leases(self) -> list[str]:
        self._initialize()
        now = _dt(_now())
        expired: list[str] = []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT job_id, status FROM simulation_jobs
                WHERE lease_expires_at IS NOT NULL
                AND lease_expires_at != ''
                AND lease_expires_at < ?
                AND status IN (?, ?, ?)
                """,
                (
                    now,
                    RuntimeJobStatus.LEASED.value,
                    RuntimeJobStatus.STARTING.value,
                    RuntimeJobStatus.RUNNING.value,
                ),
            ).fetchall()
        for row in rows:
            job_id = str(row["job_id"])
            status = RuntimeJobStatus(str(row["status"]))
            updated = self.update_status_cas(
                job_id,
                expected=status,
                next_status=RuntimeJobStatus.INTERRUPTED,
                reason_code="lease_expired",
                worker_id="",
                lease_id="",
            )
            if updated is not None:
                expired.append(job_id)
        return expired

    def append_event(
        self,
        job_id: str,
        *,
        event_type: str,
        source: str,
        payload: dict[str, object],
        previous_status: str = "",
        next_status: str = "",
        reason_code: str = "",
    ) -> SimulationJobEvent:
        self._initialize()
        event_id = "evt-" + uuid4().hex[:16]
        now = _now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            job = conn.execute(
                "SELECT run_id FROM simulation_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if job is None:
                conn.execute("ROLLBACK")
                raise KeyError(job_id)
            row = conn.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS sequence
                FROM simulation_job_events
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
            stream = conn.execute(
                "SELECT COALESCE(MAX(stream_sequence), 0) AS sequence FROM simulation_job_events"
            ).fetchone()
            sequence = int(row["sequence"]) + 1
            stream_sequence = int(stream["sequence"]) + 1
            conn.execute(
                """
                INSERT INTO simulation_job_events (
                    event_id, job_id, run_id, sequence, stream_sequence, event_type,
                    previous_status, next_status, reason_code, timestamp, source, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    job_id,
                    str(job["run_id"]),
                    sequence,
                    stream_sequence,
                    event_type,
                    previous_status,
                    next_status,
                    reason_code,
                    _dt(now),
                    source,
                    _dumps(payload),
                ),
            )
            conn.execute("COMMIT")
        return SimulationJobEvent(
            event_id=event_id,
            job_id=job_id,
            run_id=str(job["run_id"]),
            sequence=sequence,
            stream_sequence=stream_sequence,
            event_type=event_type,
            previous_status=previous_status,
            next_status=next_status,
            reason_code=reason_code,
            timestamp=now,
            source=source,
            payload=dict(payload),
        )

    def list_events(self, run_id: str) -> list[SimulationJobEvent]:
        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM simulation_job_events WHERE run_id = ? ORDER BY sequence ASC",
                (run_id,),
            ).fetchall()
        return [_event_from_row(row) for row in rows]

    def list_stream_events_after(self, sequence: int) -> list[SimulationJobEvent]:
        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM simulation_job_events
                WHERE stream_sequence > ?
                ORDER BY stream_sequence ASC
                LIMIT 512
                """,
                (sequence,),
            ).fetchall()
        return [_event_from_row(row) for row in rows]

    def save_metrics(self, job_id: str, metrics: list[dict[str, object]]) -> None:
        self._initialize()
        with self._connect() as conn:
            conn.execute("DELETE FROM simulation_metrics WHERE job_id = ?", (job_id,))
            job = conn.execute(
                "SELECT run_id FROM simulation_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if job is None:
                raise KeyError(job_id)
            for index, metric in enumerate(metrics):
                conn.execute(
                    """
                    INSERT INTO simulation_metrics (job_id, run_id, metric_index, metric_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (job_id, str(job["run_id"]), index, _dumps(metric)),
                )

    def get_metrics(self, run_id: str) -> list[dict[str, object]]:
        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT metric_json FROM simulation_metrics
                WHERE run_id = ?
                ORDER BY metric_index ASC
                """,
                (run_id,),
            ).fetchall()
        return [_loads(str(row["metric_json"])) for row in rows]

    def save_artifacts(self, job_id: str, artifact_paths: dict[str, str]) -> None:
        self._initialize()
        with self._connect() as conn:
            job = conn.execute(
                "SELECT run_id FROM simulation_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if job is None:
                raise KeyError(job_id)
            conn.execute(
                """
                UPDATE simulation_jobs
                SET artifact_paths_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (_dumps(artifact_paths), _dt(_now()), job_id),
            )
            conn.execute("DELETE FROM simulation_artifacts WHERE job_id = ?", (job_id,))
            for name, path in artifact_paths.items():
                conn.execute(
                    """
                    INSERT INTO simulation_artifacts (job_id, run_id, name, relative_path)
                    VALUES (?, ?, ?, ?)
                    """,
                    (job_id, str(job["run_id"]), name, path),
                )

    def get_artifacts(self, run_id: str) -> dict[str, str]:
        row = self._fetch_one(
            "SELECT artifact_paths_json FROM simulation_jobs WHERE run_id = ?", (run_id,)
        )
        if row is None:
            raise KeyError(run_id)
        return dict(_loads(str(row["artifact_paths_json"])))

    def create_batch(
        self, *, batch_id: str, manifest: dict[str, object], run_ids: list[str]
    ) -> SimulationBatchRecord:
        self._initialize()
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO simulation_batches (
                    batch_id, manifest_json, run_ids_json, total, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, '')
                """,
                (batch_id, _dumps(manifest), _dumps(run_ids), len(run_ids), _dt(now)),
            )
        return SimulationBatchRecord(
            batch_id=batch_id,
            manifest=dict(manifest),
            run_ids=list(run_ids),
            total=len(run_ids),
            created_at=now,
        )

    def get_batch(self, batch_id: str) -> SimulationBatchRecord:
        row = self._fetch_one("SELECT * FROM simulation_batches WHERE batch_id = ?", (batch_id,))
        if row is None:
            raise KeyError(batch_id)
        return _batch_from_row(row)

    def list_batch_jobs(self, batch_id: str) -> list[SimulationJobRecord]:
        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM simulation_jobs WHERE batch_id = ? ORDER BY created_at ASC",
                (batch_id,),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def list_attempts(self, run_id: str) -> list[SimulationJobAttempt]:
        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM simulation_job_attempts
                WHERE run_id = ?
                ORDER BY attempt ASC
                """,
                (run_id,),
            ).fetchall()
        return [_attempt_from_row(row) for row in rows]

    def start_attempt(self, job_id: str, *, worker_id: str) -> SimulationJobAttempt:
        self._initialize()
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT run_id, attempt FROM simulation_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            attempt = int(row["attempt"]) + 1
            conn.execute(
                """
                UPDATE simulation_jobs
                SET attempt = ?, worker_id = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (attempt, worker_id, _dt(now), job_id),
            )
            conn.execute(
                """
                INSERT INTO simulation_job_attempts (
                    job_id, run_id, attempt, worker_id, started_at, ended_at, result,
                    error, artifact_paths_json
                ) VALUES (?, ?, ?, ?, ?, '', 'RUNNING', '', ?)
                """,
                (job_id, str(row["run_id"]), attempt, worker_id, _dt(now), _dumps({})),
            )
        return SimulationJobAttempt(
            job_id=job_id,
            run_id=str(row["run_id"]),
            attempt=attempt,
            worker_id=worker_id,
            started_at=now,
            ended_at=None,
            result="RUNNING",
            error="",
            artifact_paths={},
        )

    def finish_attempt(
        self,
        job_id: str,
        *,
        attempt: int,
        result: str,
        error: str,
        artifact_paths: dict[str, str],
    ) -> None:
        self._initialize()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE simulation_job_attempts
                SET ended_at = ?, result = ?, error = ?, artifact_paths_json = ?
                WHERE job_id = ? AND attempt = ?
                """,
                (_dt(_now()), result, error, _dumps(artifact_paths), job_id, attempt),
            )

    def find_queued_jobs(self) -> list[SimulationJobRecord]:
        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM simulation_jobs
                WHERE status = ?
                ORDER BY priority DESC, created_at ASC
                """,
                (RuntimeJobStatus.QUEUED.value,),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def find_recoverable_jobs(self) -> list[SimulationJobRecord]:
        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM simulation_jobs WHERE status IN (?, ?, ?, ?)
                ORDER BY updated_at ASC
                """,
                (
                    RuntimeJobStatus.LEASED.value,
                    RuntimeJobStatus.STARTING.value,
                    RuntimeJobStatus.RUNNING.value,
                    RuntimeJobStatus.INTERRUPTED.value,
                ),
            ).fetchall()
        return [_job_from_row(row) for row in rows]

    def queued_count(self) -> int:
        return self._count_status({RuntimeJobStatus.QUEUED})

    def running_count(self) -> int:
        return self._count_status(
            {
                RuntimeJobStatus.VALIDATING,
                RuntimeJobStatus.LEASED,
                RuntimeJobStatus.STARTING,
                RuntimeJobStatus.RUNNING,
                RuntimeJobStatus.CANCEL_REQUESTED,
                RuntimeJobStatus.CANCELLING,
                RuntimeJobStatus.FINALIZING,
            }
        )

    def blocked_count(self) -> int:
        return self._count_status({RuntimeJobStatus.BLOCKED_BY_ENV})

    def retry_job(self, job_id: str) -> SimulationJobRecord:
        job = self.get_job(job_id)
        if job.status not in {
            RuntimeJobStatus.FAILED,
            RuntimeJobStatus.TIMED_OUT,
            RuntimeJobStatus.CANCELLED,
            RuntimeJobStatus.INTERRUPTED,
            RuntimeJobStatus.RECOVERY_PENDING,
        }:
            raise ValueError("job_not_retryable")
        queued_at = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE simulation_jobs
                SET status = ?, cancel_requested = 0, completed_at = NULL,
                    queued_at = ?, updated_at = ?,
                    worker_id = '', lease_id = '', lease_expires_at = NULL,
                    error_code = '', error_message = ''
                WHERE job_id = ?
                """,
                (RuntimeJobStatus.QUEUED.value, _dt(queued_at), _dt(queued_at), job_id),
            )
        self.append_event(
            job_id,
            event_type="job_retried",
            source="simulation_runtime",
            payload={"previous_status": job.status.value},
            previous_status=job.status.value,
            next_status=RuntimeJobStatus.QUEUED.value,
            reason_code="manual_retry",
        )
        return replace(
            job,
            status=RuntimeJobStatus.QUEUED,
            cancel_requested=False,
            completed_at=None,
            queued_at=queued_at,
            updated_at=queued_at,
            worker_id="",
            lease_id="",
            lease_expires_at=None,
            error_code="",
            error_message="",
        )

    def _count_status(self, statuses: set[RuntimeJobStatus]) -> int:
        self._initialize()
        placeholders = ",".join("?" for _ in statuses)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS count FROM simulation_jobs WHERE status IN ({placeholders})",
                tuple(status.value for status in statuses),
            ).fetchone()
        return int(row["count"]) if row else 0

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _fetch_one(self, query: str, params: tuple[object, ...]) -> sqlite3.Row | None:
        self._initialize()
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return cast(sqlite3.Row | None, row)

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS simulation_jobs (
                    job_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    batch_id TEXT NOT NULL DEFAULT '',
                    backend TEXT NOT NULL,
                    scenario_id TEXT NOT NULL,
                    control_mode TEXT NOT NULL,
                    seed INTEGER NOT NULL,
                    manifest_id TEXT NOT NULL,
                    reproducibility_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    draft_json TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    queued_at TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    updated_at TEXT NOT NULL,
                    timeout_seconds INTEGER NOT NULL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    worker_id TEXT NOT NULL DEFAULT '',
                    lease_id TEXT NOT NULL DEFAULT '',
                    lease_expires_at TEXT,
                    blocker_codes_json TEXT NOT NULL DEFAULT '[]',
                    error_code TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    artifact_root TEXT NOT NULL DEFAULT '',
                    artifact_paths_json TEXT NOT NULL DEFAULT '{}',
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    source_commit TEXT NOT NULL DEFAULT '',
                    source_tree_hash TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_sim_jobs_status_backend
                ON simulation_jobs(status, backend, priority, created_at);
                CREATE TABLE IF NOT EXISTS simulation_job_events (
                    event_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    stream_sequence INTEGER NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    previous_status TEXT NOT NULL DEFAULT '',
                    next_status TEXT NOT NULL DEFAULT '',
                    reason_code TEXT NOT NULL DEFAULT '',
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES simulation_jobs(job_id)
                );
                CREATE INDEX IF NOT EXISTS idx_sim_events_run_sequence
                ON simulation_job_events(run_id, sequence);
                CREATE TABLE IF NOT EXISTS simulation_job_leases (
                    lease_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    released_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(job_id) REFERENCES simulation_jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS simulation_job_attempts (
                    job_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL,
                    worker_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    artifact_paths_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(job_id, attempt),
                    FOREIGN KEY(job_id) REFERENCES simulation_jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS simulation_metrics (
                    job_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    metric_index INTEGER NOT NULL,
                    metric_json TEXT NOT NULL,
                    PRIMARY KEY(job_id, metric_index),
                    FOREIGN KEY(job_id) REFERENCES simulation_jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS simulation_artifacts (
                    job_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    PRIMARY KEY(job_id, name),
                    FOREIGN KEY(job_id) REFERENCES simulation_jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS simulation_batches (
                    batch_id TEXT PRIMARY KEY,
                    manifest_json TEXT NOT NULL,
                    run_ids_json TEXT NOT NULL,
                    total INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT ''
                );
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, _dt(_now())),
            )


def _job_from_row(row: sqlite3.Row) -> SimulationJobRecord:
    return SimulationJobRecord(
        job_id=str(row["job_id"]),
        run_id=str(row["run_id"]),
        batch_id=str(row["batch_id"]),
        backend=str(row["backend"]),
        scenario_id=str(row["scenario_id"]),
        control_mode=str(row["control_mode"]),
        seed=int(row["seed"]),
        manifest_id=str(row["manifest_id"]),
        reproducibility_hash=str(row["reproducibility_hash"]),
        status=RuntimeJobStatus(str(row["status"])),
        draft=_loads(str(row["draft_json"])),
        manifest=_loads(str(row["manifest_json"])),
        attempt=int(row["attempt"]),
        max_attempts=int(row["max_attempts"]),
        priority=int(row["priority"]),
        created_at=_parse_dt(row["created_at"]),
        queued_at=_parse_optional_dt(row["queued_at"]),
        started_at=_parse_optional_dt(row["started_at"]),
        completed_at=_parse_optional_dt(row["completed_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        timeout_seconds=int(row["timeout_seconds"]),
        cancel_requested=bool(row["cancel_requested"]),
        worker_id=str(row["worker_id"]),
        lease_id=str(row["lease_id"]),
        lease_expires_at=_parse_optional_dt(row["lease_expires_at"]),
        blocker_codes=list(_loads(str(row["blocker_codes_json"]))),
        error_code=str(row["error_code"]),
        error_message=str(row["error_message"]),
        artifact_root=str(row["artifact_root"]),
        artifact_paths=dict(_loads(str(row["artifact_paths_json"]))),
        provenance=_loads(str(row["provenance_json"])),
        source_commit=str(row["source_commit"]),
        source_tree_hash=str(row["source_tree_hash"]),
    )


def _event_from_row(row: sqlite3.Row) -> SimulationJobEvent:
    return SimulationJobEvent(
        event_id=str(row["event_id"]),
        job_id=str(row["job_id"]),
        run_id=str(row["run_id"]),
        sequence=int(row["sequence"]),
        stream_sequence=int(row["stream_sequence"]),
        event_type=str(row["event_type"]),
        previous_status=str(row["previous_status"]),
        next_status=str(row["next_status"]),
        reason_code=str(row["reason_code"]),
        timestamp=_parse_dt(row["timestamp"]),
        source=str(row["source"]),
        payload=_loads(str(row["payload_json"])),
    )


def _attempt_from_row(row: sqlite3.Row) -> SimulationJobAttempt:
    return SimulationJobAttempt(
        job_id=str(row["job_id"]),
        run_id=str(row["run_id"]),
        attempt=int(row["attempt"]),
        worker_id=str(row["worker_id"]),
        started_at=_parse_dt(row["started_at"]),
        ended_at=_parse_optional_dt(row["ended_at"]),
        result=str(row["result"]),
        error=str(row["error"]),
        artifact_paths=dict(_loads(str(row["artifact_paths_json"]))),
    )


def _batch_from_row(row: sqlite3.Row) -> SimulationBatchRecord:
    return SimulationBatchRecord(
        batch_id=str(row["batch_id"]),
        manifest=_loads(str(row["manifest_json"])),
        run_ids=list(_loads(str(row["run_ids_json"]))),
        total=int(row["total"]),
        created_at=_parse_dt(row["created_at"]),
        completed_at=_parse_optional_dt(row["completed_at"]),
    )


def _event_type_for_status(status: RuntimeJobStatus) -> str:
    return {
        RuntimeJobStatus.QUEUED: "job_queued",
        RuntimeJobStatus.VALIDATING: "job_validating",
        RuntimeJobStatus.LEASED: "job_leased",
        RuntimeJobStatus.STARTING: "job_started",
        RuntimeJobStatus.RUNNING: "job_started",
        RuntimeJobStatus.CANCEL_REQUESTED: "cancel_requested",
        RuntimeJobStatus.CANCELLING: "job_cancelling",
        RuntimeJobStatus.CANCELLED: "job_cancelled",
        RuntimeJobStatus.TIMED_OUT: "job_timed_out",
        RuntimeJobStatus.FAILED: "job_failed",
        RuntimeJobStatus.INTERRUPTED: "job_interrupted",
        RuntimeJobStatus.RECOVERY_PENDING: "job_recovered",
        RuntimeJobStatus.FINALIZING: "job_finalizing",
        RuntimeJobStatus.SUCCEEDED: "job_completed",
        RuntimeJobStatus.BLOCKED_BY_ENV: "backend_blocked",
    }.get(status, "job_state")


def _dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _loads(payload: str) -> Any:
    if not payload:
        return {}
    return json.loads(payload)


def _now() -> datetime:
    return datetime.now(UTC)


def _dt(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_dt(value: object) -> datetime:
    return datetime.fromisoformat(str(value)).astimezone(UTC)


def _parse_optional_dt(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    return _parse_dt(value)
