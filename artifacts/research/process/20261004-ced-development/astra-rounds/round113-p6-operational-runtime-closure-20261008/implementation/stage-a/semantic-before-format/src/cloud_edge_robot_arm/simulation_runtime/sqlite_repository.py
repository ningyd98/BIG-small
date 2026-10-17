"""SQLite 持久化仓库。

该仓库是仿真运行时的默认真源：job 状态、事件序列、租约、attempt、metrics 和
artifact 索引都写入事务。状态推进使用 CAS，避免多个 worker 或服务实例重复消费
同一任务。
"""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import threading
from _thread import RLock
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ParamSpec, TypeVar, cast
from uuid import uuid4
from functools import wraps

from cloud_edge_robot_arm.simulation_runtime.operational_lease import (
    OperationalLeaseError, OperationalLeaseSession, LockedLeaseView, LeaseProposal,
    LeaseCommitAck, _canonical, _digest, _current_session, _issue_view, _make_ack,
    _close_view, _invalidate_view, _epoch_has_ended, _revoke_epoch,
)

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
_PUBLICATION_REGISTRY_LOCK = threading.Lock()
_PUBLICATION_LOCKS: dict[tuple[int, str], RLock] = {}
_PUBLICATION_LOCAL = threading.local()


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _job_writer(function: Callable[_P, _R]) -> Callable[_P, _R]:
    """Every public writer joins one guarded connection; nested helpers cannot bypass it."""
    @wraps(function)
    def guarded(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        repository = cast(SQLiteSimulationJobRepository, args[0])
        return cast(_R, repository._writer_call(function, args, kwargs))
    return guarded


class SQLiteSimulationJobRepository:
    """SQLite 版 SimulationJobRepository。

    方法内多次调用 _initialize 是刻意设计：测试和本地运行可能删除数据库文件，
    每次访问前确保 schema 存在，避免后台线程在重启恢复场景中崩溃。
    """

    def __init__(self, database_path: Path) -> None:
        self._transactions = threading.local()
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def publication_guard(self) -> Iterator[None]:
        """Brief cross-process exclusion for ownership changes and final evidence.

        Same-thread nested calls across repository instances share one flock;
        other threads serialize before opening their own descriptor. PID keys
        prevent a forked child from inheriting a false reentrant ownership claim.
        """
        key = (os.getpid(), str(self.database_path.resolve()))
        with _PUBLICATION_REGISTRY_LOCK:
            lock = _PUBLICATION_LOCKS.setdefault(key, RLock())
        with lock:
            held = getattr(_PUBLICATION_LOCAL, "held", None)
            if held is None:
                held = set()
                _PUBLICATION_LOCAL.held = held
            if key in held:
                yield
                return
            lock_path = self.database_path.with_name(self.database_path.name + ".publication.lock")
            with lock_path.open("a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                held.add(key)
                try:
                    yield
                finally:
                    held.remove(key)
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @_job_writer
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

    @_job_writer
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
        expected_lease_id: str | None = None,
        expected_worker_id: str | None = None,
        lease_expired_before: datetime | None = None,
    ) -> SimulationJobRecord | None:
        with self.publication_guard():
            return self._update_status_cas_unlocked(
                job_id,
                expected=expected,
                next_status=next_status,
                reason_code=reason_code,
                worker_id=worker_id,
                lease_id=lease_id,
                error_code=error_code,
                error_message=error_message,
                expected_lease_id=expected_lease_id,
                expected_worker_id=expected_worker_id,
                lease_expired_before=lease_expired_before,
            )

    def _update_status_cas_unlocked(
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
        expected_lease_id: str | None = None,
        expected_worker_id: str | None = None,
        lease_expired_before: datetime | None = None,
    ) -> SimulationJobRecord | None:
        self._require_active_writer()
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
        ownership_sql = ""
        if expected_lease_id is not None:
            ownership_sql += " AND lease_id = ?"
            params.append(expected_lease_id)
        if expected_worker_id is not None:
            ownership_sql += " AND worker_id = ?"
            params.append(expected_worker_id)
        if lease_expired_before is not None:
            ownership_sql += " AND lease_expires_at != '' AND lease_expires_at <= ?"
            params.append(_dt(lease_expired_before))
        with self._connect() as conn:
            # CAS 条件同时检查 job_id 和 previous status；如果状态已被取消、
            # 超时或其他 worker 推进，本次更新必须失败，避免覆盖真实状态。
            cursor = conn.execute(
                f"""
                UPDATE simulation_jobs SET {", ".join(updates)}
                WHERE job_id = ? AND status = ?{ownership_sql}
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

    @_job_writer
    def request_cancel(self, job_id: str) -> SimulationJobRecord:
        with self.publication_guard():
            return self._request_cancel_unlocked(job_id)

    def _request_cancel_unlocked(self, job_id: str) -> SimulationJobRecord:
        self._require_active_writer()
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
        for _ in range(8):
            refreshed = self.get_job(job_id)
            if refreshed.status == RuntimeJobStatus.QUEUED:
                next_status = RuntimeJobStatus.CANCELLED
            elif refreshed.status in {
                RuntimeJobStatus.VALIDATING,
                RuntimeJobStatus.LEASED,
                RuntimeJobStatus.STARTING,
                RuntimeJobStatus.RUNNING,
            }:
                next_status = RuntimeJobStatus.CANCEL_REQUESTED
            else:
                return refreshed
            updated = self.update_status_cas(
                job_id,
                expected=refreshed.status,
                next_status=next_status,
                reason_code="cancelled_before_start"
                if next_status == RuntimeJobStatus.CANCELLED
                else "operator_cancel",
                # Cancellation applies to the current job, never restores an owner.
                worker_id="",
                lease_id="",
                expected_lease_id=refreshed.lease_id,
                expected_worker_id=refreshed.worker_id,
            )
            if updated is not None:
                return updated
        # Return persisted truth if a competing transition won; never fabricate
        # CANCEL_REQUESTED solely in the response object.
        return self.get_job(job_id)

    def acquire_lease(
        self, *, worker_id: str, backend: str, lease_ttl_seconds: int
    ) -> SimulationJobLease | None:
        with self.publication_guard():
            session = _current_session(self)
            if session is not None:
                return self._acquire_operational(session, worker_id=worker_id, backend=backend,
                                                 lease_ttl_seconds=lease_ttl_seconds)
            with self._legacy_write_transaction():
                return self._acquire_lease_unlocked(
                worker_id=worker_id,
                backend=backend,
                lease_ttl_seconds=lease_ttl_seconds,
            )

    def _acquire_lease_unlocked(
        self, *, worker_id: str, backend: str, lease_ttl_seconds: int
    ) -> SimulationJobLease | None:
        self._require_active_writer()
        self._initialize()
        now = _now()
        expires_at = now + timedelta(seconds=lease_ttl_seconds)
        lease_id = "lease-" + uuid4().hex[:16]
        with self._connect() as conn:
            # SQLite 没有 SKIP LOCKED；这里在同一事务里选择并更新 QUEUED job，
            # 状态条件就是防止重复消费的主要防线。
            row = conn.execute(
                """
                SELECT * FROM simulation_jobs
                WHERE backend = ? AND status = ?
                AND NOT EXISTS (SELECT 1 FROM simulation_operational_leases_v1 AS op
                                WHERE op.job_id = simulation_jobs.job_id)
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (backend, RuntimeJobStatus.QUEUED.value),
            ).fetchone()
            if row is None:
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

    @_job_writer
    def heartbeat_lease(self, lease_id: str, *, lease_ttl_seconds: int) -> None:
        self._initialize()
        if type(lease_ttl_seconds) is not int or lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds must be a positive integer")
        with self._connect() as conn:
            # Measure after lock acquisition: lock waits cannot revive expiry.
            now = _now()
            expires_at = now + timedelta(seconds=lease_ttl_seconds)
            # Keep lease and job expiry in one transaction. Expiry, release,
            # cancellation and ownership changes are irreversible to a heartbeat.
            cursor = conn.execute(
                """
                UPDATE simulation_job_leases SET heartbeat_at = ?, expires_at = ?
                WHERE lease_id = ? AND released_at = '' AND expires_at > ?
                AND EXISTS (
                    SELECT 1 FROM simulation_jobs AS job
                    WHERE job.job_id = simulation_job_leases.job_id
                    AND job.lease_id = simulation_job_leases.lease_id
                    AND job.worker_id = simulation_job_leases.worker_id
                    AND job.lease_expires_at > ? AND job.cancel_requested = 0
                    AND job.status IN (?, ?, ?)
                )
                """,
                (
                    _dt(now),
                    _dt(expires_at),
                    lease_id,
                    _dt(now),
                    _dt(now),
                    RuntimeJobStatus.LEASED.value,
                    RuntimeJobStatus.STARTING.value,
                    RuntimeJobStatus.RUNNING.value,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("lease is expired, released or no longer actively owned")
            conn.execute(
                """
                UPDATE simulation_jobs SET lease_expires_at = ?, updated_at = ?
                WHERE lease_id = ?
                """,
                (_dt(expires_at), _dt(now), lease_id),
            )

    @_job_writer
    def release_lease(self, lease_id: str) -> None:
        self._initialize()
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE simulation_job_leases SET released_at = ? WHERE lease_id = ?",
                (_dt(now), lease_id),
            )

    def list_leases(self, run_id: str) -> list[SimulationJobLease]:
        self._initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT leases.* FROM simulation_job_leases AS leases
                JOIN simulation_jobs AS jobs ON jobs.job_id = leases.job_id
                WHERE jobs.run_id = ?
                ORDER BY leases.acquired_at ASC
                """,
                (run_id,),
            ).fetchall()
        return [_lease_from_row(row) for row in rows]

    @_job_writer
    def expire_leases(self) -> list[str]:
        self._initialize()
        cutoff = _now()
        now = _dt(cutoff)
        expired: list[str] = []
        with self._connect() as conn:
            # 租约过期只标记 INTERRUPTED，不自动重跑；恢复策略之后再判断
            # artifact 是否完整，避免重复执行已经完成的任务。
            rows = conn.execute(
                """
                SELECT job_id, status, lease_id, worker_id FROM simulation_jobs
                WHERE lease_expires_at IS NOT NULL
                AND lease_expires_at != ''
                AND lease_expires_at <= ?
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
                expected_lease_id=str(row["lease_id"]),
                expected_worker_id=str(row["worker_id"]),
                lease_expired_before=cutoff,
            )
            if updated is not None:
                expired.append(job_id)
        return expired

    @_job_writer
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
            job = conn.execute(
                "SELECT run_id FROM simulation_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if job is None:
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
            # run 内 sequence 和全局 stream_sequence 都在事务中递增，
            # WebSocket replay 因而不依赖进程内队列。
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

    @_job_writer
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

    @_job_writer
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

    @_job_writer
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

    @_job_writer
    def start_attempt(self, job_id: str, *, worker_id: str) -> SimulationJobAttempt:
        self._initialize()
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT run_id, attempt, worker_id, lease_id FROM simulation_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                raise KeyError(job_id)
            attempt = int(row["attempt"]) + 1
            cursor = conn.execute(
                """
                UPDATE simulation_jobs
                SET attempt = ?, worker_id = ?, updated_at = ?
                WHERE job_id = ? AND attempt = ? AND worker_id = ? AND lease_id = ?
                """,
                (attempt, worker_id, _dt(now), job_id, int(row["attempt"]),
                 str(row["worker_id"]), str(row["lease_id"])),
            )
            if cursor.rowcount != 1:
                raise OperationalLeaseError("actual start_attempt CAS0")
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

    @_job_writer
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

    @_job_writer
    def finish_open_attempts(self, job_id: str, *, result: str, error: str) -> None:
        self._initialize()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE simulation_job_attempts
                SET ended_at = ?, result = ?, error = ?
                WHERE job_id = ? AND ended_at = ''
                """,
                (_dt(_now()), result, error, job_id),
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
                AND NOT EXISTS (SELECT 1 FROM simulation_operational_leases_v1 AS op
                                WHERE op.job_id=simulation_jobs.job_id)
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

    @_job_writer
    def retry_job(self, job_id: str) -> SimulationJobRecord:
        with self.publication_guard():
            return self._retry_job_unlocked(job_id)

    def _retry_job_unlocked(self, job_id: str) -> SimulationJobRecord:
        self._require_active_writer()
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
            # retry 只重置运行时字段，不改变 manifest/reproducibility hash；
            # 因此重试仍指向同一个实验定义。
            cursor = conn.execute(
                """
                UPDATE simulation_jobs
                SET status = ?, cancel_requested = 0, completed_at = NULL,
                    queued_at = ?, updated_at = ?,
                    worker_id = '', lease_id = '', lease_expires_at = NULL,
                    error_code = '', error_message = ''
                WHERE job_id = ? AND status = ? AND lease_id = ? AND worker_id = ?
                """,
                (
                    RuntimeJobStatus.QUEUED.value, _dt(queued_at), _dt(queued_at),
                    job_id, job.status.value, job.lease_id, job.worker_id,
                ),
            )
            if cursor.rowcount != 1:
                raise ValueError("job_not_retryable")
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

    def _require_active_writer(self) -> None:
        if getattr(self._transactions, "connection", None) is None:
            raise OperationalLeaseError("unlocked helper requires actual guarded writer")

    def _txn_is_current(self, connection: sqlite3.Connection, nonce: str) -> bool:
        return (getattr(self._transactions, "connection", None) is connection
                and getattr(self._transactions, "nonce", None) == nonce)

    def _view_is_current(self, view: LockedLeaseView) -> bool:
        return self._txn_is_current(view._connection, view._nonce)

    def _commit_is_recorded(self, view: LockedLeaseView, identity: str) -> bool:
        return self._view_is_current(view) and getattr(self._transactions, "commit", None) == identity

    @contextmanager
    def _legacy_write_transaction(self) -> Iterator[sqlite3.Connection]:
        self._initialize()
        if getattr(self._transactions, "connection", None) is not None:
            yield self._transactions.connection
            return
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._transactions.connection = connection
            self._transactions.nonce = uuid4().hex
            self._transactions.commit = None
            try:
                yield connection
                connection.execute("COMMIT")
            except BaseException:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
            finally:
                self._transactions.connection = None
                self._transactions.nonce = None
                self._transactions.commit = None

    def _operational_row(self, conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM simulation_operational_leases_v1 WHERE job_id=?",
                           (job_id,)).fetchone()
        return dict(row) if row is not None else None

    def _job_snapshot(self, conn: sqlite3.Connection, job_id: str) -> str:
        row = conn.execute("SELECT * FROM simulation_jobs WHERE job_id=?", (job_id,)).fetchone()
        attempts = conn.execute("SELECT * FROM simulation_job_attempts WHERE job_id=? ORDER BY attempt",
                                (job_id,)).fetchall()
        if row is None:
            raise KeyError(job_id)
        return json.dumps({"job": dict(row), "attempts": [dict(a) for a in attempts]},
                          sort_keys=True, allow_nan=False)

    @contextmanager
    def _operational_transaction(self, session: OperationalLeaseSession, *, job_id: str | None,
                                 purpose: str, operation_sha256: str) -> Iterator[LockedLeaseView]:
        session._check_ingress(purpose)
        if session.repository is not self or job_id != session.job_id:
            raise OperationalLeaseError("session requires exact concrete repository/job")
        with self.publication_guard():
            self._initialize()
            if getattr(self._transactions, "connection", None) is not None:
                raise OperationalLeaseError("cannot issue nested/reused operational transaction")
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                nonce = uuid4().hex
                self._transactions.connection = conn
                self._transactions.nonce = nonce
                self._transactions.commit = None
                view: LockedLeaseView | None = None
                try:
                    row = self._operational_row(conn, str(job_id))
                    if row is None:
                        raise OperationalLeaseError("missing actual operational row")
                    self._validate_operational_row(conn, session, row)
                    view = _issue_view(session, self, conn, nonce, row, purpose, operation_sha256)
                    yield view
                except BaseException:
                    if view is not None:
                        _invalidate_view(view, "operational transaction exception")
                    raise
                finally:
                    try:
                        if conn.in_transaction:
                            conn.execute("ROLLBACK")
                    except sqlite3.Error:
                        if view is not None:
                            _invalidate_view(view, "real connection closed")
                    if view is not None:
                        _close_view(view)
                    self._transactions.connection = None
                    self._transactions.nonce = None
                    self._transactions.commit = None

    def _validate_operational_row(self, conn: sqlite3.Connection, session: OperationalLeaseSession,
                                  row: dict[str, Any]) -> None:
        if (row["epoch"], row["lease_id"], row["worker_id"]) != (
            session.epoch, session.lease_id, session.worker_id
        ):
            raise OperationalLeaseError("actual epoch/lease/worker mismatch")
        if row["job_snapshot_json"] != self._job_snapshot(conn, row["job_id"]):
            raise OperationalLeaseError("actual job/attempt snapshot drift")
        snapshot = json.loads(row["job_snapshot_json"])
        job = snapshot["job"]
        if job["cancel_requested"] or job["lease_id"] != row["lease_id"] or job["worker_id"] != row["worker_id"]:
            raise OperationalLeaseError("actual cancel/reassignment veto")
        open_attempts = [a for a in snapshot["attempts"] if a["ended_at"] == ""]
        if row["lifecycle"] == "ACQUIRED":
            if row["attempt"] is not None or open_attempts:
                raise OperationalLeaseError("ACQUIRED cannot invent an open attempt")
        elif row["lifecycle"] == "ATTEMPT_BOUND":
            if len(open_attempts) != 1 or open_attempts[0]["attempt"] != row["attempt"]:
                raise OperationalLeaseError("exact unique actual open attempt required")
        else:
            raise OperationalLeaseError("terminal operational lifecycle")

    def _commit_operational_proposal(self, view: LockedLeaseView,
                                     proposal: LeaseProposal) -> LeaseCommitAck:
        session = view._session
        session._check_ingress(view.purpose)
        if not self._view_is_current(view) or view.state != "CONSUMED" or proposal._view is not view:
            raise OperationalLeaseError("unregistered consumed transaction/proposal")
        conn = view._connection
        try:
            if not conn.in_transaction:
                raise OperationalLeaseError("commit requires original still-open transaction")
            target = dict(proposal.target)
            if view.purpose == "acquire":
                columns = list(target)
                conn.execute(
                    f"INSERT INTO simulation_operational_leases_v1 ({','.join(columns)}) "
                    f"VALUES ({','.join('?' for _ in columns)})", tuple(target[c] for c in columns),
                )
            else:
                columns = [key for key in target if key != "lease_id"]
                before = view.snapshot
                cursor = conn.execute(
                    "UPDATE simulation_operational_leases_v1 SET " + ",".join(c + "=?" for c in columns)
                    + " WHERE lease_id=? AND generation=? AND row_revision=? AND proposed_row_digest=?",
                    tuple(target[c] for c in columns) + (before["lease_id"], before["generation"],
                                                        before["row_revision"], before["proposed_row_digest"]),
                )
                if cursor.rowcount != 1:
                    raise OperationalLeaseError("actual operational CAS rowcount is not one")
            conn.execute("COMMIT")  # exactly one activation commit, no SQL ACTIVE phase
            commit_identity = uuid4().hex
            self._transactions.commit = commit_identity
            row = self._operational_row(conn, target["job_id"])
            if row is None:
                raise OperationalLeaseError("successful commit reread missing")
            return _make_ack(view, proposal, commit_identity, row)
        except (sqlite3.Error, OperationalLeaseError) as error:
            _invalidate_view(view, "CAS/commit/connection failed")
            try:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise OperationalLeaseError("operational CAS/commit failed") from error

    def _acquire_operational(self, session: OperationalLeaseSession, *, worker_id: str,
                             backend: str, lease_ttl_seconds: int) -> SimulationJobLease | None:
        session._check_ingress("acquire")
        if worker_id != session.worker_id or backend != "MUJOCO" or lease_ttl_seconds * 1_000_000_000 != session.ttl_ns:
            raise OperationalLeaseError("acquisition differs from frozen worker policy")
        self._initialize()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._transactions.connection = conn
            self._transactions.nonce = uuid4().hex
            self._transactions.commit = None
            view: LockedLeaseView | None = None
            try:
                row = conn.execute("SELECT * FROM simulation_jobs WHERE backend=? AND status=? "
                                   "ORDER BY priority DESC, created_at ASC LIMIT 1",
                                   (backend, RuntimeJobStatus.QUEUED.value)).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    return None
                job = _job_from_row(row)
                from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft
                draft = ExperimentDraft.model_validate(job.draft)
                if (job.scenario_id != "S01_NORMAL_STATIC" or draft.input_mode != "RGBD"
                    or draft.execution_scope != "VISION_CLOSED_LOOP" or draft.job_type == "DATASET_GENERATION"):
                    raise OperationalLeaseError("unsupported job remains on explicitly selected legacy route")
                if self._operational_row(conn, job.job_id) is not None:
                    raise OperationalLeaseError("same operational job cannot reacquire/reissue original")
                lease_id = "lease-" + uuid4().hex[:16]
                session.job_id, session.lease_id = job.job_id, lease_id
                domain = session.domain
                binding = session.worker.visual_role_binding
                if binding is None:
                    raise OperationalLeaseError("actual binding unavailable")
                original_job = _digest({key: dict(row)[key] for key in (
                    "job_id", "run_id", "backend", "scenario_id", "draft_json", "timeout_seconds",
                    "max_attempts", "source_commit", "source_tree_hash", "reproducibility_hash",
                )})
                snapshot = {"lease_id": lease_id, "schema": "simulation.operational-leases.v1",
                    "job_id": job.job_id, "run_id": job.run_id, "worker_id": worker_id,
                    "attempt": None, "lifecycle": "ACQUIRED", "pid": domain.pid,
                    "boot_id": domain.boot_id, "process_start_ticks": domain.process_start_ticks,
                    "epoch": session.epoch, "generation": 0, "row_revision": 0,
                    "original_job_digest": original_job,
                    "original_policy_digest": _digest({"job": original_job, "binding": binding.evidence(),
                                                       "ttl_ns": session.ttl_ns}),
                    "original_acquisition_json": "{}", "segment_json": "{}", "proposal_id": "",
                    "operation_sha256": "", "job_snapshot_json": self._job_snapshot(conn, job.job_id),
                    "proposed_row_digest": "", "durable_phase": "COMMITTED", "terminal_reason": ""}
                view = _issue_view(session, self, conn, self._transactions.nonce, snapshot, "acquire",
                                   _digest({"operation": "acquire", "job_id": job.job_id, "lease": lease_id}))
                now = _now()  # legacy UTC diagnostic/extra veto only, post-guard/BEGIN
                expires = now + timedelta(seconds=lease_ttl_seconds)
                cursor = conn.execute("UPDATE simulation_jobs SET status=?, updated_at=?, worker_id=?, "
                                      "lease_id=?, lease_expires_at=? WHERE job_id=? AND status=?",
                                      (RuntimeJobStatus.LEASED.value, _dt(now), worker_id, lease_id,
                                       _dt(expires), job.job_id, RuntimeJobStatus.QUEUED.value))
                if cursor.rowcount != 1:
                    raise OperationalLeaseError("actual acquisition job CAS0")
                conn.execute("INSERT INTO simulation_job_leases(lease_id, job_id, worker_id, acquired_at, "
                             "expires_at, heartbeat_at, released_at) VALUES(?,?,?,?,?,?,'')",
                             (lease_id, job.job_id, worker_id, _dt(now), _dt(expires), _dt(now)))
                self.append_event(job.job_id, event_type="job_leased", source="simulation_runtime",
                                  payload={"worker_id": worker_id, "lease_id": lease_id},
                                  previous_status=RuntimeJobStatus.QUEUED.value,
                                  next_status=RuntimeJobStatus.LEASED.value, reason_code="lease_acquired")
                view._repository_target = {"job_snapshot_json": self._job_snapshot(conn, job.job_id)}
                proposal = session.propose_locked(view, ttl_ns=session.ttl_ns)
                ack = self._commit_operational_proposal(view, proposal)
                session.confirm_committed(ack)
                return SimulationJobLease(lease_id=lease_id, job_id=job.job_id, worker_id=worker_id,
                                          acquired_at=now, expires_at=expires, heartbeat_at=now)
            finally:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                if view is not None:
                    _close_view(view)
                self._transactions.connection = None
                self._transactions.nonce = None
                self._transactions.commit = None

    def _writer_call(self, function: Callable[..., Any], args: tuple[Any, ...],
                     kwargs: dict[str, Any]) -> Any:
        with self.publication_guard():
            if getattr(self._transactions, "connection", None) is not None:
                return function(*args, **kwargs)  # genuine same-transaction internal nested writer
            self._initialize()
            name = function.__name__
            job_id = str(args[1]) if len(args) > 1 else str(kwargs.get("job_id", ""))
            with self._connect() as lookup:
                if name in {"heartbeat_lease", "release_lease"}:
                    lease = lookup.execute("SELECT job_id FROM simulation_job_leases WHERE lease_id=?",
                                           (job_id,)).fetchone()
                    job_id = str(lease["job_id"]) if lease is not None else ""
                row = self._operational_row(lookup, job_id) if job_id else None
            if row is None:
                with self._legacy_write_transaction() as connection:
                    value = function(*args, **kwargs)
                    if name == "expire_leases":
                        for expired_job in value:
                            operational = self._operational_row(connection, expired_job)
                            if operational is not None:
                                self._terminalize_operational(connection, operational, "legacy UTC expiry veto")
                    return value
            if name == "retry_job":
                raise ValueError("operational_job_not_retryable")
            if name == "update_status_cas" and kwargs["next_status"] == RuntimeJobStatus.QUEUED:
                return None
            session = _current_session(self)
            safe = name in {"request_cancel", "release_lease"}
            if name == "finish_open_attempts":
                safe = kwargs.get("result") in {"INTERRUPTED", "CANCELLED", "TIMED_OUT", "FAILED"}
            if name == "update_status_cas":
                safe = kwargs["next_status"] in {
                    RuntimeJobStatus.CANCEL_REQUESTED, RuntimeJobStatus.CANCELLING,
                    RuntimeJobStatus.CANCELLED, RuntimeJobStatus.INTERRUPTED, RuntimeJobStatus.FAILED,
                    RuntimeJobStatus.TIMED_OUT,
                } or (kwargs.get("worker_id", "") not in {"", row["worker_id"]}
                      or kwargs.get("lease_id", "") not in {"", row["lease_id"]})
            cleanup = (session is not None and getattr(session, "main_thread", None) == threading.get_ident()
                       and session.epoch == row["epoch"] and name in {
                           "append_event", "save_metrics", "save_artifacts", "finish_attempt",
                           "update_status_cas", "finish_open_attempts",
                       } and (row["lifecycle"] == "TERMINAL" or row["durable_phase"] != "COMMITTED"))
            if safe or cleanup:
                with self._legacy_write_transaction() as conn:
                    value = function(*args, **kwargs)
                    self._terminalize_operational(conn, row, name)
                    return value
            if session is None:
                raise OperationalLeaseError("legacy/generic caller cannot mutate operational job")
            if name == "heartbeat_lease" and kwargs["lease_ttl_seconds"] * 1_000_000_000 != session.ttl_ns:
                raise OperationalLeaseError("heartbeat cannot change original TTL policy")
            purpose = "heartbeat" if name == "heartbeat_lease" else name
            with self._operational_transaction(session, job_id=job_id, purpose=purpose,
                                               operation_sha256=_digest({"name": name, "job": job_id})) as view:
                session.evaluate_locked(view)
                if name == "start_attempt" and row["lifecycle"] != "ACQUIRED":
                    raise OperationalLeaseError("second attempt bind cannot reset lifecycle")
                value = function(*args, **kwargs)
                if name == "update_status_cas" and value is None:
                    raise OperationalLeaseError("actual job status CAS0")
                conn = view._connection
                target: dict[str, Any] = {"job_snapshot_json": self._job_snapshot(conn, job_id)}
                if name == "start_attempt":
                    target.update(attempt=value.attempt, lifecycle="ATTEMPT_BOUND")
                elif name == "finish_attempt":
                    target.update(lifecycle="TERMINAL", terminal_reason="attempt finished")
                view._repository_target = target
                proposal = session.propose_locked(view, ttl_ns=session.ttl_ns)
                ack = self._commit_operational_proposal(view, proposal)
                session.confirm_committed(ack)
                return value

    def _terminalize_operational(self, conn: sqlite3.Connection, before: dict[str, Any],
                                 reason: str) -> None:
        target = dict(before)
        target.update(durable_phase="REVOKED", lifecycle="TERMINAL", terminal_reason=reason,
                      row_revision=int(before["row_revision"]) + 1,
                      generation=int(before["generation"]) + 1,
                      job_snapshot_json=self._job_snapshot(conn, before["job_id"]))
        target["proposed_row_digest"] = _canonical(target)
        columns = [key for key in target if key != "lease_id"]
        cursor = conn.execute("UPDATE simulation_operational_leases_v1 SET "
                              + ",".join(c + "=?" for c in columns)
                              + " WHERE lease_id=? AND row_revision=? AND generation=?",
                              tuple(target[c] for c in columns)
                              + (before["lease_id"], before["row_revision"], before["generation"]))
        if cursor.rowcount != 1:
            raise OperationalLeaseError("terminal mutation lost exact generation CAS")
        _revoke_epoch(before["epoch"], reason)

    @_job_writer
    def terminate_orphaned_operational_attempts(self) -> list[str]:
        """Unknown live foreign process is never proof that an epoch is orphaned."""
        self._require_active_writer()
        conn = self._transactions.connection
        rows = conn.execute("SELECT * FROM simulation_operational_leases_v1 WHERE durable_phase='COMMITTED'").fetchall()
        terminated: list[str] = []
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        from cloud_edge_robot_arm.research.operational_time_v1 import _parse_process_start_ticks
        for original in rows:
            row = dict(original)
            pid = int(row["pid"])
            orphan = _epoch_has_ended(row["epoch"]) if pid == os.getpid() else False
            if not orphan and pid != os.getpid():
                try:
                    stat = Path(f"/proc/{pid}/stat").read_text()
                except FileNotFoundError:
                    orphan = True
                except OSError:
                    continue
                else:
                    # Fixture identities can be CPU-typed; matching live PID alone remains UNKNOWN.
                    if row["boot_id"] == boot:
                        orphan = _parse_process_start_ticks(stat, expected_pid=pid) != int(row["process_start_ticks"])
            if not orphan:
                continue
            job = conn.execute("SELECT status FROM simulation_jobs WHERE job_id=?", (row["job_id"],)).fetchone()
            if job is None:
                continue
            conn.execute("UPDATE simulation_job_attempts SET ended_at=?, result='INTERRUPTED', error=? "
                         "WHERE job_id=? AND ended_at=''",
                         (_dt(_now()), "operational epoch ended", row["job_id"]))
            conn.execute("UPDATE simulation_jobs SET status=?, updated_at=?, error_code=? WHERE job_id=? "
                         "AND status IN (?,?,?)",
                         (RuntimeJobStatus.INTERRUPTED.value, _dt(_now()), "operational_epoch_ended", row["job_id"],
                          RuntimeJobStatus.LEASED.value, RuntimeJobStatus.STARTING.value, RuntimeJobStatus.RUNNING.value))
            self._terminalize_operational(conn, row, "orphaned epoch ended")
            conn.execute("UPDATE simulation_operational_leases_v1 SET durable_phase='TERMINATED' WHERE lease_id=?",
                         (row["lease_id"],))
            # Exact final durable-phase bytes participate in the canonical row digest.
            final = self._operational_row(conn, row["job_id"])
            if final is not None:
                conn.execute("UPDATE simulation_operational_leases_v1 SET proposed_row_digest=? WHERE lease_id=?",
                             (_canonical(final), row["lease_id"]))
            terminated.append(row["job_id"])
        return terminated

    def _count_status(self, statuses: set[RuntimeJobStatus]) -> int:
        self._initialize()
        placeholders = ",".join("?" for _ in statuses)
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS count FROM simulation_jobs WHERE status IN ({placeholders})",
                tuple(status.value for status in statuses),
            ).fetchone()
        return int(row["count"]) if row else 0

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        active = getattr(self._transactions, "connection", None)
        if active is not None:
            yield active
            return
        conn = sqlite3.connect(self.database_path, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            # sqlite3.Connection 的 context manager 不会关闭连接；repository 方法必须
            # 主动 close，避免长 validation 运行后堆积大量 DB/WAL/SHM fd。
            conn.close()

    def _fetch_one(self, query: str, params: tuple[object, ...]) -> sqlite3.Row | None:
        self._initialize()
        with self._connect() as conn:
            row = conn.execute(query, params).fetchone()
        return cast(sqlite3.Row | None, row)

    def _initialize(self) -> None:
        if getattr(self._transactions, "connection", None) is not None:
            return
        with self.publication_guard(), self._connect() as conn:
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
                CREATE TABLE IF NOT EXISTS simulation_operational_leases_v1 (
                    lease_id TEXT PRIMARY KEY, schema TEXT NOT NULL,
                    job_id TEXT NOT NULL UNIQUE, run_id TEXT NOT NULL, worker_id TEXT NOT NULL,
                    attempt INTEGER, lifecycle TEXT NOT NULL,
                    pid INTEGER NOT NULL, boot_id TEXT NOT NULL, process_start_ticks INTEGER NOT NULL,
                    epoch TEXT NOT NULL, generation INTEGER NOT NULL, row_revision INTEGER NOT NULL,
                    original_job_digest TEXT NOT NULL, original_policy_digest TEXT NOT NULL,
                    original_acquisition_json TEXT NOT NULL, segment_json TEXT NOT NULL,
                    proposal_id TEXT NOT NULL, operation_sha256 TEXT NOT NULL,
                    job_snapshot_json TEXT NOT NULL, proposed_row_digest TEXT NOT NULL,
                    durable_phase TEXT NOT NULL, terminal_reason TEXT NOT NULL,
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


def _lease_from_row(row: sqlite3.Row) -> SimulationJobLease:
    return SimulationJobLease(
        lease_id=str(row["lease_id"]),
        job_id=str(row["job_id"]),
        worker_id=str(row["worker_id"]),
        acquired_at=_parse_dt(row["acquired_at"]),
        expires_at=_parse_dt(row["expires_at"]),
        heartbeat_at=_parse_dt(row["heartbeat_at"]),
        released_at=_parse_optional_dt(row["released_at"]),
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
