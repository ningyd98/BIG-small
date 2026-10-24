"""SQLite 持久化仓库。

该仓库是仿真运行时的默认真源：job 状态、事件序列、租约、attempt、metrics 和
artifact 索引都写入事务。状态推进使用 CAS，避免多个 worker 或服务实例重复消费
同一任务。
"""

from __future__ import annotations

import fcntl
import json
import os
import stat
import sqlite3
import sys
import threading
from _thread import RLock
from collections.abc import Callable, Iterator
from contextlib import contextmanager, closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import Path
from types import FunctionType
from typing import Any, Protocol, cast
from uuid import uuid4

from cloud_edge_robot_arm.simulation_runtime.models import (
    RuntimeJobStatus,
    SimulationBatchRecord,
    SimulationJobAttempt,
    SimulationJobEvent,
    SimulationJobLease,
    SimulationJobRecord,
    PublicationSummary,
)
from cloud_edge_robot_arm.simulation_runtime.operational_lease import (
    LeaseCommitAck,
    LeaseProposal,
    LockedLeaseView,
    OperationalLeaseError,
    OperationalLeaseSession,
    _canonical,
    _close_view,
    _current_session,
    _digest,
    _epoch_has_ended,
    _invalidate_view,
    _issue_view,
    _make_ack,
    _proposal_record,
    _revoke_epoch,
    _seal_repository_target,
    _view_record,
    _take_final_confirmation,
    _ConsumedFinalConfirmation,
)
from cloud_edge_robot_arm.simulation_runtime.state_machine import validate_transition

SCHEMA_VERSION = 1
_PUBLICATION_REGISTRY_LOCK = threading.Lock()
_PUBLICATION_LOCKS: dict[tuple[int, str], RLock] = {}
_PUBLICATION_LOCAL = threading.local()
_WRITER_REGISTRY_LOCK = threading.RLock()
_WRITER_OWNERS: dict[str, _WriterOwner] = {}
_WRITER_STACKS: dict[str, list[Callable[..., Any]]] = {}
_DISPATCH_OWNERS: dict[int, _DispatchOwner] = {}
_WRITER_FUNCTIONS: dict[str, Callable[..., Any]] = {}
_DISPATCH_CODES: set[Any] = set()


class _ContextManagerFunction(Protocol):
    __wrapped__: FunctionType


@dataclass(frozen=True)
class _DispatchOwner:
    repository: SQLiteSimulationJobRepository
    function: Callable[..., Any]
    job_id: str
    pid: int
    thread_id: int
    native_thread_id: int


@dataclass(frozen=True)
class _WriterOwner:
    repository: SQLiteSimulationJobRepository
    database: Path
    connection: sqlite3.Connection
    nonce: str
    pid: int
    thread_id: int
    native_thread_id: int
    job_id: str
    operation: str
    dispatch: _DispatchOwner | None


def _job_writer[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    """Every public writer joins one guarded connection; nested helpers cannot bypass it."""

    @wraps(function)
    def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
        repository = cast(SQLiteSimulationJobRepository, args[0])
        return cast(R, repository._writer_call(function, args, kwargs))

    _WRITER_FUNCTIONS[function.__name__] = function
    _DISPATCH_CODES.add(cast(FunctionType, guarded).__code__)
    return guarded


class SQLiteSimulationJobRepository:
    """SQLite 版 SimulationJobRepository。

    方法内多次调用 _initialize 是刻意设计：测试和本地运行可能删除数据库文件，
    每次访问前确保 schema 存在，避免后台线程在重启恢复场景中崩溃。
    """

    def __init__(self, database_path: Path, *, artifact_root: Path | None = None) -> None:
        self._transactions = threading.local()
        self.database_path = database_path
        self._artifact_root = None if artifact_root is None else Path(artifact_root).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def _publication_manifest(root: Path, paths: dict[str, str]) -> dict[str, dict[str, Any]]:
        """Hash regular exact files under a configured root without following links."""
        root = root.resolve(strict=True)
        manifest = {}
        for name, relative in sorted(paths.items()):
            if type(name) is not str or type(relative) is not str or not name or not relative:
                raise ValueError("exact named artifact paths required")
            rel = Path(relative)
            path = root / rel
            if (rel.is_absolute() or relative != rel.as_posix() or ".." in rel.parts
                    or path.resolve(strict=True) != path or not path.is_relative_to(root)):
                raise ValueError("publication artifact path escapes configured root or follows a link")
            initial = path.lstat()
            if not stat.S_ISREG(initial.st_mode):
                raise ValueError("publication requires regular artifact files")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                identity = lambda row: (row.st_dev, row.st_ino, row.st_mode, row.st_size,
                                         row.st_mtime_ns, row.st_ctime_ns)
                opened = os.fstat(descriptor)
                if identity(initial) != identity(opened):
                    raise ValueError("publication file changed before read")
                import hashlib

                digest = hashlib.sha256()
                size = 0
                with os.fdopen(descriptor, "rb", closefd=False) as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                        size += len(chunk)
                if (identity(opened) != identity(os.fstat(descriptor))
                        or identity(opened) != identity(path.lstat()) or size != opened.st_size):
                    raise ValueError("publication file changed during read")
                manifest[name] = {"relative_path": relative, "bytes": size, "sha256": digest.hexdigest()}
            finally:
                os.close(descriptor)
        if not manifest:
            raise ValueError("publication requires a nonempty artifact manifest")
        return manifest

    def _final_publication_mode(self, view: LockedLeaseView) -> str:
        """Classify only the genuine private finalizer session after ingress checks."""
        issued = _view_record(view)
        session = issued.session
        if (_current_session(self) is not session or session.repository is not self
                or session.worker.repository is not self
                or session.worker._operational_lease_session is not session
                or view.purpose != "finalize_operational_publication"):
            raise OperationalLeaseError("final publication requires the exact current private session")
        session._check_ingress(view.purpose)
        mode = session._mode
        if mode not in {"LOCAL_TEMPORAL_PUBLICATION_V1", "OPERATIONAL_LEASE_FOUNDATION_V1"}:
            raise OperationalLeaseError("unknown final publication authority mode")
        return mode

    def _final_publication_sources(self, view: LockedLeaseView, paths: dict[str, str], frozen) -> dict[str, Any]:
        from cloud_edge_robot_arm.vision.operational_windows import _OWNERS, _LOCAL_RUNTIMES
        from cloud_edge_robot_arm.repositories.event_autonomy import SQLiteEventAutonomyRepository, InMemoryEventAutonomyRepository

        if sys._getframe(1).f_code is not _WRITER_FUNCTIONS["finalize_operational_publication"].__code__:
            raise OperationalLeaseError("actual finalizer alone binds publication sources")
        if self._final_publication_mode(view) != "LOCAL_TEMPORAL_PUBLICATION_V1":
            raise OperationalLeaseError("local final source audit requires local mode")
        session = _view_record(view).session
        worker = session.worker
        owner = _OWNERS.get(worker)
        if owner is None or owner._startup.repository is not self:
            raise OperationalLeaseError("final publication lacks original app owner")
        owner._check_app_live()
        root = Path(worker.artifact_root).resolve()
        if self._artifact_root is not None and self._artifact_root != root:
            raise OperationalLeaseError("worker artifact root differs from configured repository root")
        self._artifact_root = root  # Bound only inside this genuine private finalizer.
        events = worker.visual_event_repository
        runtime = _LOCAL_RUNTIMES.get(owner)
        if (runtime is None or runtime.source.event_repository is not events
                or runtime.source.job_repository is not self
                or type(events) not in {SQLiteEventAutonomyRepository, InMemoryEventAutonomyRepository}):
            raise OperationalLeaseError("final publication requires the original concrete event repository")
        if getattr(self._transactions, "final_publication_live_sources", None) is not None:
            raise OperationalLeaseError("final publication private source slot already occupied")
        self._transactions.final_publication_live_sources = (owner, runtime, events)
        lock = events._write_lock if type(events) is SQLiteEventAutonomyRepository else events._lock
        with lock:
            owner._check_local_locked(view, purpose=view.purpose, operation_sha256=view.operation_sha256)
            receipts = [dict(row) for row in view._connection.execute(
                "SELECT * FROM simulation_local_publications_v1 WHERE job_id=? ORDER BY operation_id", (session.job_id,))]
            if not receipts:
                raise OperationalLeaseError("final publication has no completed local source receipts")
            for receipt in receipts:
                if (receipt["phase"] != "COMPLETE" or receipt["epoch"] != session.epoch
                        or receipt["attempt"] != view.snapshot["attempt"]):
                    raise OperationalLeaseError("partial or foreign local source receipt cannot confirm terminal publication")
                if type(events) is SQLiteEventAutonomyRepository:
                    row = events._conn.execute("SELECT * FROM visual_local_publications_v1 WHERE operation_id=?",
                                               (receipt["operation_id"],)).fetchone()
                    actual = None if row is None else dict(row)
                else:
                    raw = events._local_publications.get(receipt["operation_id"])
                    actual = None if raw is None else json.loads(raw)
                if actual != receipt:
                    raise OperationalLeaseError("actual job/event completion receipts do not join")
            owner._check_app_live()
        return {
            "artifact_root": str(root), "manifest": self._publication_manifest(root, paths),
            "event_receipts": receipts,
            "event_database": str(events.path.resolve()) if type(events) is SQLiteEventAutonomyRepository else None,
            "event_kind": "sqlite" if type(events) is SQLiteEventAutonomyRepository else "memory",
            "original_time": owner._local_original,
            "original_app_reference": owner.export_record(owner.task_window), "rows": frozen,
        }

    def _stage_final_confirmation(self, view: LockedLeaseView, proposal: LeaseProposal) -> dict[str, Any]:
        if sys._getframe(1).f_code is not self._dispatch_writer.__code__:
            raise OperationalLeaseError("actual finalizer dispatch stages terminal confirmation")
        if self._final_publication_mode(view) != "LOCAL_TEMPORAL_PUBLICATION_V1":
            raise OperationalLeaseError("local pending audit requires local mode")
        context = getattr(self._transactions, "final_publication", None)
        target = dict(proposal.target)
        if context is None or view.purpose != "finalize_operational_publication" or target["lifecycle"] != "TERMINAL":
            raise OperationalLeaseError("exact final publication sources required")
        job = self.get_job(target["job_id"])
        payload = {**context, "target": target, "run_id": job.run_id,
                   "attempt": job.attempt, "epoch": target["epoch"],
                   "generation": target["generation"], "proof": None}
        row = {"run_id": job.run_id, "job_id": job.job_id, "attempt": job.attempt,
               "epoch": target["epoch"], "operation_id": _digest(["terminal-publication", job.run_id, job.attempt, target["epoch"]]),
               "generation": target["generation"], "state": "PENDING",
               "job_receipt_hash": _canonical(target),
               "event_receipt_hash": _digest(context["event_receipts"]),
               "artifact_manifest_sha256": _digest(context["manifest"]),
               "payload_json": json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False),
               "confirmation_hash": ""}
        columns = tuple(row)
        view._connection.execute("INSERT INTO simulation_publication_confirmations_v1 (" + ",".join(columns)
            + ") VALUES (" + ",".join("?" for _ in columns) + ")", tuple(row[name] for name in columns))
        return row

    def _record_final_confirmation(self, view: LockedLeaseView, proof: _ConsumedFinalConfirmation,
                                   pending: dict[str, Any]) -> None:
        """Audit only; this path cannot renew a lease or modify historical outcomes."""
        from cloud_edge_robot_arm.vision.operational_windows import (
            OperationalWindowOwner, _OWNERS, _LOCAL_RUNTIMES, _LOCAL_ORIGINALS,
            _json as _window_json,
        )
        from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime
        from cloud_edge_robot_arm.repositories.event_autonomy import SQLiteEventAutonomyRepository, InMemoryEventAutonomyRepository

        if (sys._getframe(1).f_code is not self._dispatch_writer.__code__
                or type(proof) is not _ConsumedFinalConfirmation or proof.session.repository is not self
                or proof.reply.view.view is not view or proof.pid != os.getpid()
                or proof.thread_id != threading.get_ident() or proof.native_thread_id != threading.get_native_id()):
            raise OperationalLeaseError("private consumed one-use final confirmation proof required")
        if self._final_publication_mode(view) != "LOCAL_TEMPORAL_PUBLICATION_V1":
            raise OperationalLeaseError("local consumed audit requires local mode")
        sources = getattr(self._transactions, "final_publication_live_sources", None)
        if type(sources) is not tuple or len(sources) != 3:
            raise OperationalLeaseError("final confirmation lost private original source references")
        owner, runtime, events = sources
        payload = json.loads(pending["payload_json"])
        target = dict(proof.reply.proposal.proposal.target)
        session, worker = proof.session, proof.session.worker

        def check_sources() -> None:
            if (type(owner) is not OperationalWindowOwner or type(runtime) is not VisualWorkerRuntime
                    or _OWNERS.get(worker) is not owner or _LOCAL_RUNTIMES.get(owner) is not runtime
                    or runtime._operational_owner is not owner or owner._closed
                    or worker.visual_event_repository is not events
                    or runtime.source.event_repository is not events
                    or runtime.source.job_repository is not self or worker.repository is not self
                    or runtime._local_session is not session or worker._operational_lease_session is not session
                    or type(events) not in {SQLiteEventAutonomyRepository, InMemoryEventAutonomyRepository}):
                raise OperationalLeaseError("final confirmation actual private source identities changed")
            startup = owner._startup
            sealed = _LOCAL_ORIGINALS.get(owner)
            if (startup.worker is not worker or startup.repository is not self
                    or startup.mode != "LOCAL_TEMPORAL_PUBLICATION_V1"
                    or startup.thread_id != threading.get_ident()
                    or startup.binding is not runtime.role_binding or startup.binding is not worker.visual_role_binding
                    or (startup.job_id, startup.run_id, startup.attempt, startup.lease_id)
                    != (session.job_id, pending["run_id"], pending["attempt"], session.lease_id)
                    or (runtime.source.job_id, runtime.source.run_id, runtime.source.worker_id, runtime.source.lease_id)
                    != (session.job_id, startup.run_id, session.worker_id, session.lease_id)
                    or sealed is None or _window_json(owner._local_original) != sealed
                    or _window_json(runtime._local_original) != sealed
                    or _window_json(payload["original_time"]) != sealed
                    or dict(runtime.source.source_hashes) != dict(owner._source_hashes)
                    or dict(runtime.source.source_hashes) != payload["original_time"]["source_hashes"]
                    or payload["original_time"]["lease_identity"]["source_identity"] != owner._source_identity):
                raise OperationalLeaseError("final confirmation original startup/description/source changed")
            owner._check_app_live()
            if _window_json(owner.export_record(owner.task_window)) != _window_json(payload["original_app_reference"]):
                raise OperationalLeaseError("final confirmation original app reference changed")
            expected_kind = "sqlite" if type(events) is SQLiteEventAutonomyRepository else "memory"
            expected_database = str(events.path.resolve()) if expected_kind == "sqlite" else None
            if payload["event_kind"] != expected_kind or payload["event_database"] != expected_database:
                raise OperationalLeaseError("archived event description differs from actual private source")

        check_sources()
        conn = view._connection
        if (self._writer_binding().connection is not conn or not self._view_is_current(view)
                or conn.in_transaction):
            raise OperationalLeaseError("separate audit requires the genuine completed writer transaction")
        event_lock = events._write_lock if type(events) is SQLiteEventAutonomyRepository else events._lock
        audit_owned = False
        try:
            audit_owned = True  # The connection had no transaction before our BEGIN.
            conn.execute("BEGIN IMMEDIATE")
            with event_lock:
                event_owned = False
                try:
                    if type(events) is SQLiteEventAutonomyRepository:
                        if events._conn.in_transaction:
                            raise OperationalLeaseError("audit cannot use a foreign event transaction")
                        event_owned = True
                        events._conn.execute("BEGIN IMMEDIATE")
                    check_sources()
                    receipts = [dict(row) for row in conn.execute(
                        "SELECT * FROM simulation_local_publications_v1 WHERE job_id=? ORDER BY operation_id",
                        (session.job_id,)).fetchall()]
                    if (not receipts or receipts != payload["event_receipts"]
                            or _digest(receipts) != pending["event_receipt_hash"]
                            or any(row["phase"] != "COMPLETE"
                                   or (row["job_id"], row["attempt"], row["lease_id"], row["epoch"])
                                   != (session.job_id, pending["attempt"], session.lease_id, session.epoch)
                                   for row in receipts)):
                        raise OperationalLeaseError("current job COMPLETE receipt join changed after consumption")
                    for receipt in receipts:
                        if type(events) is SQLiteEventAutonomyRepository:
                            row = events._conn.execute("SELECT * FROM visual_local_publications_v1 WHERE operation_id=?",
                                                       (receipt["operation_id"],)).fetchone()
                            actual = None if row is None else dict(row)
                        else:
                            value = events._local_publications.get(receipt["operation_id"])
                            actual = None if value is None else json.loads(value)
                        if actual != receipt:
                            raise OperationalLeaseError("current event COMPLETE receipt join changed after consumption")
                    if (payload["target"] != target or pending["job_receipt_hash"] != _canonical(target)
                            or self._operational_row(conn, pending["job_id"]) != target
                            or self._job_snapshot(conn, pending["job_id"]) != target["job_snapshot_json"]
                            or self._publication_manifest(self._artifact_root, self.get_artifacts(pending["run_id"])) != payload["manifest"]):
                        raise OperationalLeaseError("final proof/real commit/manifest join changed")
                    row = conn.execute("SELECT * FROM simulation_publication_confirmations_v1 WHERE operation_id=?",
                                       (pending["operation_id"],)).fetchone()
                    if row is None or dict(row) != pending:
                        raise OperationalLeaseError("final confirmation pending receipt changed")
                    payload["proof"] = {"commit_identity": proof.ack._commit_identity,
                        "committed_row_digest": proof.ack._row_digest, "response_consumed": True,
                        "generation": proof.observation.generation, "epoch": session.epoch, "pid": proof.pid,
                        "thread_id": proof.thread_id, "native_thread_id": proof.native_thread_id,
                        "app_current": {"domain": owner._local_original["app_domain"],
                                        "remaining_seconds": owner._remaining_app_seconds()},
                        "scope": "ARCHIVAL_CONFIRMATION_ONLY_NO_LIVE_AUTHORITY"}
                    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
                    owner._check_app_live()
                    cursor = conn.execute("UPDATE simulation_publication_confirmations_v1 SET state='CONFIRMED',payload_json=?,confirmation_hash=? "
                        "WHERE operation_id=? AND state='PENDING' AND payload_json=?",
                        (raw, _digest(payload), pending["operation_id"], pending["payload_json"]))
                    if cursor.rowcount != 1:
                        raise OperationalLeaseError("one-use final confirmation audit CAS0")
                    conn.execute("COMMIT")
                    audit_owned = False
                finally:
                    primary = sys.exception()
                    try:
                        if event_owned and events._conn.in_transaction:
                            events._conn.execute("ROLLBACK")
                    except BaseException:
                        if primary is None:
                            raise
        except BaseException:
            try:
                if audit_owned and conn.in_transaction:
                    conn.execute("ROLLBACK")
            except BaseException:
                pass  # Preserve the original failure; terminal COMMIT already happened.
            raise

    def get_publication_summary(self, run_id: str, *, attempt: int | None = None) -> PublicationSummary:
        """Rejoin archival SQL, actual receipts and actual files; never resume authority."""
        self._initialize()
        with self.publication_guard(), self._connect() as conn:
            job = self.get_job_by_run_id(run_id)
            selected = job.attempt if attempt is None else attempt
            actual_attempt = conn.execute("SELECT * FROM simulation_job_attempts WHERE job_id=? AND attempt=?",
                                          (job.job_id, selected)).fetchone()
            history = (job.artifact_paths if attempt is None or actual_attempt is None
                       else dict(_loads(str(actual_attempt["artifact_paths_json"]))))
            operational = self._operational_row(conn, job.job_id)
            if operational is None:
                return PublicationSummary(job.status.value, "NOT_APPLICABLE", attempt=selected,
                                          historical_artifact_paths=tuple(sorted(history.items())))
            receipt = conn.execute("SELECT * FROM simulation_publication_confirmations_v1 WHERE run_id=? AND attempt=?",
                                   (run_id, selected)).fetchall()
            row = dict(receipt[0]) if len(receipt) == 1 else None

            def denied(reason: str, *, unknown: bool = False) -> PublicationSummary:
                return PublicationSummary(job.status.value, "UNKNOWN" if row is None or unknown else "UNCONFIRMED",
                    attempt=selected, operation_id=None if row is None else row["operation_id"],
                    epoch=None if row is None else row["epoch"], generation=None if row is None else row["generation"],
                    historical_artifact_paths=tuple(sorted(history.items())), reasons=(reason,))

            if row is None or row["state"] != "CONFIRMED" or actual_attempt is None:
                return denied("missing_or_unconfirmed_terminal_receipt")
            if self._artifact_root is None:
                return denied("configured_artifact_root_unavailable", unknown=True)
            try:
                payload = json.loads(row["payload_json"])
                target = payload["target"]
                proof = payload["proof"]
                if (row["job_id"] != job.job_id or row["attempt"] != selected or payload["run_id"] != run_id
                        or payload["attempt"] != selected or payload["epoch"] != row["epoch"]
                        or payload["generation"] != row["generation"] or operational != target
                        or target["job_snapshot_json"] != self._job_snapshot(conn, job.job_id)
                        or row["job_receipt_hash"] != _canonical(target)
                        or row["event_receipt_hash"] != _digest(payload["event_receipts"])
                        or row["artifact_manifest_sha256"] != _digest(payload["manifest"])
                        or row["confirmation_hash"] != _digest(payload)
                        or proof["response_consumed"] is not True or not proof["commit_identity"]
                        or proof["committed_row_digest"] != row["job_receipt_hash"]
                        or proof["generation"] != row["generation"] or proof["epoch"] != row["epoch"]
                        or actual_attempt["ended_at"] == "" or actual_attempt["result"] != job.status.value
                        or self._artifact_root is None or str(self._artifact_root) != payload["artifact_root"]
                        or self._publication_manifest(self._artifact_root, history) != payload["manifest"]):
                    return denied("terminal_receipt_commit_or_file_join_differs")
                for table, expected in payload["rows"].items():
                    if table not in {"simulation_metrics", "simulation_artifacts", "simulation_job_events",
                                     "simulation_job_attempts", "simulation_job_leases", "simulation_jobs"}:
                        return denied("unsupported_terminal_snapshot_table")
                    actual = [dict(value) for value in conn.execute("SELECT * FROM " + table + " WHERE job_id=?", (job.job_id,))]
                    if actual != expected:
                        return denied("historical_terminal_rows_changed")
                current_receipts = [dict(value) for value in conn.execute(
                    "SELECT * FROM simulation_local_publications_v1 WHERE job_id=? ORDER BY operation_id", (job.job_id,))]
                if current_receipts != payload["event_receipts"] or any(value["phase"] != "COMPLETE" for value in current_receipts):
                    return denied("local_completion_receipt_join_changed")
                if payload["event_kind"] == "sqlite":
                    database = Path(payload["event_database"])
                    if not database.is_file() or database.is_symlink():
                        return denied("event_completion_database_missing")
                    with closing(sqlite3.connect(database)) as event_conn:
                        event_conn.row_factory = sqlite3.Row
                        for expected in current_receipts:
                            actual = event_conn.execute("SELECT * FROM visual_local_publications_v1 WHERE operation_id=?",
                                                        (expected["operation_id"],)).fetchone()
                            if actual is None or dict(actual) != expected:
                                return denied("event_completion_receipt_missing_or_changed")
                elif payload["event_kind"] != "memory":
                    return denied("unknown_event_completion_source")
                return PublicationSummary(job.status.value, "CONFIRMED", True, row["operation_id"], selected,
                    row["epoch"], row["generation"], row["job_receipt_hash"], row["event_receipt_hash"],
                    row["artifact_manifest_sha256"], tuple(sorted(history.items())), tuple(sorted(history.items())))
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
                return denied("publication_join_unavailable_or_malformed")

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

    @_job_writer
    def acquire_lease(
        self, *, worker_id: str, backend: str, lease_ttl_seconds: int
    ) -> SimulationJobLease | None:
        with self.publication_guard():
            session = _current_session(self)
            if session is not None:
                return self._acquire_operational(
                    session,
                    worker_id=worker_id,
                    backend=backend,
                    lease_ttl_seconds=lease_ttl_seconds,
                )
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
            session = _current_session(self)
            if session is not None and session._mode == "LOCAL_TEMPORAL_PUBLICATION_V1":
                # The dispatcher already evaluated the genuine current broker
                # segment in this transaction. UTC columns remain diagnostics.
                cursor = conn.execute(
                    "UPDATE simulation_job_leases SET heartbeat_at=?,expires_at=? WHERE lease_id=? "
                    "AND released_at='' AND EXISTS (SELECT 1 FROM simulation_jobs j "
                    "WHERE j.job_id=simulation_job_leases.job_id AND j.lease_id=simulation_job_leases.lease_id "
                    "AND j.worker_id=simulation_job_leases.worker_id AND j.cancel_requested=0 "
                    "AND j.status IN (?,?,?))",
                    (_dt(now), _dt(expires_at), lease_id, RuntimeJobStatus.LEASED.value,
                     RuntimeJobStatus.STARTING.value, RuntimeJobStatus.RUNNING.value))
                if cursor.rowcount != 1:
                    raise OperationalLeaseError("current local heartbeat ownership/CAS invalid")
                conn.execute("UPDATE simulation_jobs SET lease_expires_at=?,updated_at=? WHERE lease_id=?",
                             (_dt(expires_at), _dt(now), lease_id))
                return
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
                "SELECT run_id, attempt, worker_id, lease_id FROM simulation_jobs WHERE job_id = ?",
                (job_id,),
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
                (
                    attempt,
                    worker_id,
                    _dt(now),
                    job_id,
                    int(row["attempt"]),
                    str(row["worker_id"]),
                    str(row["lease_id"]),
                ),
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
                    RuntimeJobStatus.QUEUED.value,
                    _dt(queued_at),
                    _dt(queued_at),
                    job_id,
                    job.status.value,
                    job.lease_id,
                    job.worker_id,
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

    def _writer_binding(self) -> _WriterOwner:
        owner = getattr(self._transactions, "writer_owner", None)
        with _WRITER_REGISTRY_LOCK:
            if not isinstance(owner, _WriterOwner) or _WRITER_OWNERS.get(owner.nonce) is not owner:
                raise OperationalLeaseError("private transaction owner registration required")
            if (
                owner.repository is not self
                or owner.database != self.database_path.resolve()
                or (owner.pid, owner.thread_id, owner.native_thread_id)
                != (os.getpid(), threading.get_ident(), threading.get_native_id())
                or getattr(self._transactions, "connection", None) is not owner.connection
                or getattr(self._transactions, "nonce", None) != owner.nonce
                or (owner.pid, str(owner.database))
                not in getattr(_PUBLICATION_LOCAL, "held", set())
            ):
                raise OperationalLeaseError(
                    "actual writer/guard/repository/thread binding mismatch"
                )
            if (
                owner.dispatch is not None
                and _DISPATCH_OWNERS.get(id(owner.dispatch)) is not owner.dispatch
            ):
                raise OperationalLeaseError("writer originating dispatcher ended")
            return owner

    def _require_active_writer(self) -> None:
        owner = self._writer_binding()
        if not owner.connection.in_transaction:
            raise OperationalLeaseError("writer requires original real open transaction")
        stack = _WRITER_STACKS.get(owner.nonce, [])
        caller = sys._getframe(1).f_code
        parent = sys._getframe(2).f_code
        if stack and caller is stack[-1].__code__:
            return
        helper_parents = {
            self._update_status_cas_unlocked.__code__: "update_status_cas",
            self._request_cancel_unlocked.__code__: "request_cancel",
            self._retry_job_unlocked.__code__: "retry_job",
            self._acquire_lease_unlocked.__code__: "acquire_lease",
        }
        expected = helper_parents.get(caller)
        if (
            expected
            and stack
            and stack[-1] is _WRITER_FUNCTIONS[expected]
            and parent is stack[-1].__code__
        ):
            return
        if caller is self._terminalize_operational.__code__ and parent in {
            self._dispatch_writer.__code__,
            self._cleanup_operational_row.__code__,
        }:
            return
        if (
            caller is self._cleanup_operational_row.__code__
            and stack
            and stack[-1].__name__
            in {"cleanup_operational_session", "terminate_orphaned_operational_attempts"}
        ):
            return
        raise OperationalLeaseError("private helper was not called by its registered writer")

    def _register_writer(
        self, connection: sqlite3.Connection, nonce: str, job_id: str, operation: str
    ) -> _WriterOwner:
        allowed = {
            cast(_ContextManagerFunction, self._legacy_write_transaction).__wrapped__.__code__,
            cast(_ContextManagerFunction, self._operational_transaction).__wrapped__.__code__,
            self._acquire_operational.__code__,
        }
        if sys._getframe(1).f_code not in allowed:
            raise OperationalLeaseError("only concrete guarded transaction entry registers writer")
        dispatch = getattr(self._transactions, "dispatch", None)
        if dispatch is not None and _DISPATCH_OWNERS.get(id(dispatch)) is not dispatch:
            raise OperationalLeaseError("unregistered originating dispatcher")
        if dispatch is None and operation != "inspect":
            session = _current_session(self)
            if session is None:
                raise OperationalLeaseError("transaction entry lacks actual worker scope")
            session._check_ingress(operation)
        key = (os.getpid(), str(self.database_path.resolve()))
        if key not in getattr(_PUBLICATION_LOCAL, "held", set()) or not connection.in_transaction:
            raise OperationalLeaseError("transaction registration requires true guard then BEGIN")
        if getattr(self._transactions, "writer_owner", None) is not None:
            raise OperationalLeaseError("writer registration cannot replace another transaction")
        owner = _WriterOwner(
            self,
            self.database_path.resolve(),
            connection,
            nonce,
            os.getpid(),
            threading.get_ident(),
            threading.get_native_id(),
            job_id,
            operation,
            dispatch,
        )
        with _WRITER_REGISTRY_LOCK:
            _WRITER_OWNERS[nonce] = owner
            _WRITER_STACKS[nonce] = [dispatch.function] if dispatch is not None else []
        self._transactions.connection = connection
        self._transactions.nonce = nonce
        self._transactions.commit = None
        self._transactions.writer_owner = owner
        return owner

    def _unregister_writer(self, owner: _WriterOwner) -> None:
        with _WRITER_REGISTRY_LOCK:
            if _WRITER_OWNERS.get(owner.nonce) is owner:
                _WRITER_OWNERS.pop(owner.nonce, None)
                _WRITER_STACKS.pop(owner.nonce, None)
            if getattr(self._transactions, "writer_owner", None) is owner:
                self._transactions.connection = None
                self._transactions.nonce = None
                self._transactions.commit = None
                self._transactions.writer_owner = None

    def _finish_writer(self, owner: _WriterOwner, view: LockedLeaseView | None = None) -> None:
        original_error = sys.exception()
        try:
            try:
                if owner.connection.in_transaction:
                    owner.connection.execute("ROLLBACK")
            except sqlite3.Error:
                if view is not None:
                    _invalidate_view(view, "original connection unavailable on transaction exit")
            finally:
                if view is not None:
                    _close_view(view)
        except BaseException:
            if original_error is None:
                raise
            # A secondary view cleanup fault cannot hide the original commit/ack error.
        finally:
            self._unregister_writer(owner)

    def _txn_is_current(self, connection: sqlite3.Connection, nonce: str) -> bool:
        try:
            owner = self._writer_binding()
        except OperationalLeaseError:
            return False
        return owner.connection is connection and owner.nonce == nonce

    def _view_is_current(self, view: LockedLeaseView) -> bool:
        return self._txn_is_current(view._connection, view._nonce)

    def _commit_is_recorded(self, view: LockedLeaseView, identity: str) -> bool:
        return (
            self._view_is_current(view) and getattr(self._transactions, "commit", None) == identity
        )

    @contextmanager
    def _legacy_write_transaction(self) -> Iterator[sqlite3.Connection]:
        dispatch = getattr(self._transactions, "dispatch", None)
        if dispatch is None or _DISPATCH_OWNERS.get(id(dispatch)) is not dispatch:
            raise OperationalLeaseError("private legacy transaction requires actual dispatcher")
        if getattr(self._transactions, "connection", None) is not None:
            owner = self._writer_binding()
            yield owner.connection
            return
        self._initialize()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            owner = self._register_writer(
                connection, uuid4().hex, dispatch.job_id, dispatch.function.__name__
            )
            try:
                yield connection
                connection.execute("COMMIT")
            finally:
                self._finish_writer(owner)

    def _operational_row(self, conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT * FROM simulation_operational_leases_v1 WHERE job_id=?", (job_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def _job_snapshot(self, conn: sqlite3.Connection, job_id: str) -> str:
        row = conn.execute("SELECT * FROM simulation_jobs WHERE job_id=?", (job_id,)).fetchone()
        attempts = conn.execute(
            "SELECT * FROM simulation_job_attempts WHERE job_id=? ORDER BY attempt", (job_id,)
        ).fetchall()
        if row is None:
            raise KeyError(job_id)
        return json.dumps(
            {"job": dict(row), "attempts": [dict(a) for a in attempts]},
            sort_keys=True,
            allow_nan=False,
        )

    @contextmanager
    def _operational_transaction(
        self,
        session: OperationalLeaseSession,
        *,
        job_id: str | None,
        purpose: str,
        operation_sha256: str,
    ) -> Iterator[LockedLeaseView]:
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
                owner = self._register_writer(conn, nonce, str(job_id), purpose)
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
                    self._finish_writer(owner, view)

    def _validate_operational_row(
        self, conn: sqlite3.Connection, session: OperationalLeaseSession, row: dict[str, Any]
    ) -> None:
        if (row["epoch"], row["lease_id"], row["worker_id"]) != (
            session.epoch,
            session.lease_id,
            session.worker_id,
        ):
            raise OperationalLeaseError("actual epoch/lease/worker mismatch")
        if row["job_snapshot_json"] != self._job_snapshot(conn, row["job_id"]):
            raise OperationalLeaseError("actual job/attempt snapshot drift")
        snapshot = json.loads(row["job_snapshot_json"])
        job = snapshot["job"]
        if (
            job["cancel_requested"]
            or job["lease_id"] != row["lease_id"]
            or job["worker_id"] != row["worker_id"]
        ):
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

    @contextmanager
    def _local_read_scope(self, session, *, job_id: str, purpose: str, operation_sha256: str):
        """Issue or join a genuine private read view; descriptors cannot enter."""
        from cloud_edge_robot_arm.vision.operational_windows import OperationalWindowOwner, _prepare_startup
        from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime
        from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

        caller = sys._getframe(2).f_code
        allowed = {
            _prepare_startup.__code__, OperationalWindowOwner._bind_inputs.__code__,
            VisualWorkerRuntime._read_lease.__code__,
            VisualWorkerRuntime._local_publication_scope.__wrapped__.__code__,
            SimulationWorker._owns_artifact_publication.__code__,
        }
        if (type(session) is not OperationalLeaseSession or _current_session(self) is not session
                or session.repository is not self or caller not in allowed
                or session.worker._frozen_operational_time_mode != "LOCAL_TEMPORAL_PUBLICATION_V1"):
            raise OperationalLeaseError("registered private local session/caller required")
        session._check_ingress(purpose)
        active = (getattr(self._transactions, "local_view", None)
                  or getattr(self._transactions, "publication_view", None))
        if active is not None:
            session._view(active)
            if active.snapshot["job_id"] != job_id:
                raise OperationalLeaseError("foreign local read job")
            yield active
            return
        with self._operational_transaction(session, job_id=job_id, purpose=purpose,
                                           operation_sha256=operation_sha256) as view:
            self._transactions.local_view = view
            try:
                yield view
            finally:
                self._transactions.local_view = None

    def _local_publication_receipt(self, view, receipt: dict[str, Any]) -> None:
        from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime

        if sys._getframe(1).f_code is not VisualWorkerRuntime._local_commit.__code__:
            raise OperationalLeaseError("private publication receipt coordinator required")
        session = _view_record(view).session
        session._view(view)
        if receipt["job_id"] != session.job_id or receipt["epoch"] != session.epoch:
            raise OperationalLeaseError("publication receipt original job/fence differs")
        conn = view._connection
        old = conn.execute("SELECT * FROM simulation_local_publications_v1 WHERE operation_id=?",
                           (receipt["operation_id"],)).fetchone()
        if old is not None and (old["operation_sha256"] != receipt["operation_sha256"]
                               or old["event_record_hash"] != receipt["event_record_hash"]):
            raise OperationalLeaseError("publication operation changed hash/source")
        keys = list(receipt)
        conn.execute("INSERT INTO simulation_local_publications_v1 (" + ",".join(keys)
                     + ") VALUES (" + ",".join("?" for _ in keys) + ") ON CONFLICT(operation_id) DO UPDATE SET "
                     + ",".join(k + "=excluded." + k for k in keys if k != "operation_id"),
                     tuple(receipt[k] for k in keys))
        conn.execute("COMMIT")
        # Deliberately access the real connection after COMMIT. A lost acknowledgement
        # is not converted into success, nor rolled back into a refunded debit.
        conn.execute("SELECT 1").fetchone()

    def read_local_publication(self, run_id: str) -> list[dict[str, Any]]:
        self._initialize()
        with self.publication_guard(), self._connect() as conn:
            rows = conn.execute("SELECT p.* FROM simulation_local_publications_v1 p "
                                "JOIN simulation_jobs j ON p.job_id=j.job_id WHERE j.run_id=? "
                                "ORDER BY p.operation_id", (run_id,)).fetchall()
            return [{**dict(row), "live_authority": False, "accepted": False,
                     "confirmation_state": "UNKNOWN", "write_disposition": "HISTORICAL_ONLY"}
                    for row in rows]

    def reconcile_local_publications(self) -> list[dict[str, Any]]:
        """Detached orphan census. Never activate, complete, refund or dispatch."""
        self._initialize()
        with self.publication_guard(), self._connect() as conn:
            return [{**dict(row), "confirmation_state": "UNKNOWN", "accepted": False,
                     "live_authority": False, "reason": "fresh private owner and both receipts required"}
                    for row in conn.execute("SELECT * FROM simulation_local_publications_v1 ORDER BY operation_id")]

    def _commit_operational_proposal(
        self, view: LockedLeaseView, proposal: LeaseProposal
    ) -> LeaseCommitAck:
        issued = _view_record(view)
        _proposal_record(proposal)
        session = issued.session
        session._check_ingress(issued.purpose)
        if (
            not self._view_is_current(view)
            or view.state != "CONSUMED"
            or proposal._view is not view
        ):
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
                    f"VALUES ({','.join('?' for _ in columns)})",
                    tuple(target[c] for c in columns),
                )
            else:
                columns = [key for key in target if key != "lease_id"]
                before = view.snapshot
                cursor = conn.execute(
                    "UPDATE simulation_operational_leases_v1 SET "
                    + ",".join(c + "=?" for c in columns)
                    + " WHERE lease_id=? AND generation=? AND row_revision=? "
                    "AND proposed_row_digest=?",
                    tuple(target[c] for c in columns)
                    + (
                        before["lease_id"],
                        before["generation"],
                        before["row_revision"],
                        before["proposed_row_digest"],
                    ),
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

    def _acquire_operational(
        self,
        session: OperationalLeaseSession,
        *,
        worker_id: str,
        backend: str,
        lease_ttl_seconds: int,
    ) -> SimulationJobLease | None:
        session._check_ingress("acquire")
        if (
            worker_id != session.worker_id
            or backend != "MUJOCO"
            or lease_ttl_seconds * 1_000_000_000 != session.ttl_ns
        ):
            raise OperationalLeaseError("acquisition differs from frozen worker policy")
        self._initialize()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            owner = self._register_writer(conn, uuid4().hex, "", "acquire_lease")
            view: LockedLeaseView | None = None
            try:
                row = conn.execute(
                    "SELECT * FROM simulation_jobs WHERE backend=? AND status=? "
                    "ORDER BY priority DESC, created_at ASC LIMIT 1",
                    (backend, RuntimeJobStatus.QUEUED.value),
                ).fetchone()
                if row is None:
                    conn.execute("ROLLBACK")
                    return None
                job = _job_from_row(row)
                from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft

                draft = ExperimentDraft.model_validate(job.draft)
                if (
                    job.scenario_id != "S01_NORMAL_STATIC"
                    or draft.input_mode != "RGBD"
                    or draft.execution_scope != "VISION_CLOSED_LOOP"
                    or draft.job_type == "DATASET_GENERATION"
                ):
                    raise OperationalLeaseError(
                        "unsupported job remains on explicitly selected legacy route"
                    )
                if self._operational_row(conn, job.job_id) is not None:
                    raise OperationalLeaseError(
                        "same operational job cannot reacquire/reissue original"
                    )
                lease_id = "lease-" + uuid4().hex[:16]
                session.job_id, session.lease_id = job.job_id, lease_id
                bound_owner = replace(owner, job_id=job.job_id)
                with _WRITER_REGISTRY_LOCK:
                    _WRITER_OWNERS[owner.nonce] = bound_owner
                self._transactions.writer_owner = bound_owner
                owner = bound_owner
                domain = session.domain
                binding = session.worker.visual_role_binding
                if binding is None:
                    raise OperationalLeaseError("actual binding unavailable")
                original_job = _digest(
                    {
                        key: dict(row)[key]
                        for key in (
                            "job_id",
                            "run_id",
                            "backend",
                            "scenario_id",
                            "draft_json",
                            "timeout_seconds",
                            "max_attempts",
                            "source_commit",
                            "source_tree_hash",
                            "reproducibility_hash",
                        )
                    }
                )
                snapshot = {
                    "lease_id": lease_id,
                    "schema": "simulation.operational-leases.v1",
                    "job_id": job.job_id,
                    "run_id": job.run_id,
                    "worker_id": worker_id,
                    "attempt": None,
                    "lifecycle": "ACQUIRED",
                    "pid": domain.pid,
                    "boot_id": domain.boot_id,
                    "process_start_ticks": domain.process_start_ticks,
                    "epoch": session.epoch,
                    "generation": 0,
                    "row_revision": 0,
                    "original_job_digest": original_job,
                    "original_policy_digest": _digest(
                        {
                            "job": original_job,
                            "binding": binding.evidence(),
                            "ttl_ns": session.ttl_ns,
                        }
                    ),
                    "original_acquisition_json": "{}",
                    "segment_json": "{}",
                    "proposal_id": "",
                    "operation_sha256": "",
                    "job_snapshot_json": self._job_snapshot(conn, job.job_id),
                    "proposed_row_digest": "",
                    "durable_phase": "COMMITTED",
                    "terminal_reason": "",
                }
                view = _issue_view(
                    session,
                    self,
                    conn,
                    self._transactions.nonce,
                    snapshot,
                    "acquire",
                    _digest({"operation": "acquire", "job_id": job.job_id, "lease": lease_id}),
                )
                now = _now()  # legacy UTC diagnostic/extra veto only, post-guard/BEGIN
                expires = now + timedelta(seconds=lease_ttl_seconds)
                cursor = conn.execute(
                    "UPDATE simulation_jobs SET status=?, updated_at=?, worker_id=?, "
                    "lease_id=?, lease_expires_at=? WHERE job_id=? AND status=?",
                    (
                        RuntimeJobStatus.LEASED.value,
                        _dt(now),
                        worker_id,
                        lease_id,
                        _dt(expires),
                        job.job_id,
                        RuntimeJobStatus.QUEUED.value,
                    ),
                )
                if cursor.rowcount != 1:
                    raise OperationalLeaseError("actual acquisition job CAS0")
                conn.execute(
                    "INSERT INTO simulation_job_leases(lease_id, job_id, worker_id, acquired_at, "
                    "expires_at, heartbeat_at, released_at) VALUES(?,?,?,?,?,?,'')",
                    (lease_id, job.job_id, worker_id, _dt(now), _dt(expires), _dt(now)),
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
                _seal_repository_target(
                    view, {"job_snapshot_json": self._job_snapshot(conn, job.job_id)}
                )
                proposal = session.propose_locked(view, ttl_ns=session.ttl_ns)
                ack = self._commit_operational_proposal(view, proposal)
                session.confirm_committed(ack)
                return SimulationJobLease(
                    lease_id=lease_id,
                    job_id=job.job_id,
                    worker_id=worker_id,
                    acquired_at=now,
                    expires_at=expires,
                    heartbeat_at=now,
                )
            finally:
                self._finish_writer(owner, view)

    def _writer_call(
        self, function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        if (
            sys._getframe(1).f_code not in _DISPATCH_CODES
            or _WRITER_FUNCTIONS.get(function.__name__) is not function
        ):
            raise OperationalLeaseError(
                "private dispatcher requires actual registered public writer"
            )
        name = function.__name__
        job_id = str(args[1]) if len(args) > 1 else str(kwargs.get("job_id", ""))
        with self.publication_guard():
            if getattr(self._transactions, "connection", None) is not None:
                owner = self._writer_binding()
                stack = _WRITER_STACKS[owner.nonce]
                caller = sys._getframe(2).f_code
                actual_parent = stack[-1] if stack else None
                same_job = job_id == owner.job_id or (
                    not owner.job_id
                    and owner.operation
                    in {
                        "create_job",
                        "acquire_lease",
                        "expire_leases",
                        "terminate_orphaned_operational_attempts",
                    }
                )
                event_callers = {f.__code__ for f in stack}
                event_callers.update(
                    {
                        self._update_status_cas_unlocked.__code__,
                        self._request_cancel_unlocked.__code__,
                        self._retry_job_unlocked.__code__,
                        self._acquire_lease_unlocked.__code__,
                        self._acquire_operational.__code__,
                    }
                )
                allowed = name == "append_event" and caller in event_callers and same_job
                if owner.operation == "expire_leases" and name == "update_status_cas":
                    allowed = (
                        caller is _WRITER_FUNCTIONS["expire_leases"].__code__
                        and kwargs.get("next_status") == RuntimeJobStatus.INTERRUPTED
                    )
                if owner.operation == "request_cancel" and name == "update_status_cas":
                    allowed = (
                        same_job
                        and caller is self._request_cancel_unlocked.__code__
                        and kwargs.get("next_status")
                        in {RuntimeJobStatus.CANCEL_REQUESTED, RuntimeJobStatus.CANCELLED}
                    )
                if owner.operation == "finalize_operational_publication":
                    subordinate = (
                        name
                        in {
                            "save_metrics",
                            "save_artifacts",
                            "finish_attempt",
                            "update_status_cas",
                            "release_lease",
                            "append_event",
                        }
                        and caller is _WRITER_FUNCTIONS[owner.operation].__code__
                    )
                    allowed = allowed or subordinate
                    if name == "release_lease":
                        allowed = (
                            allowed
                            and job_id
                            == cast(OperationalLeaseSession, _current_session(self)).lease_id
                        )
                    else:
                        allowed = allowed and same_job
                if not allowed or actual_parent is None:
                    raise OperationalLeaseError(
                        "nested public mutation is not a registered same-job subordinate"
                    )
                if name != "append_event" and owner.operation not in {
                    "expire_leases",
                    "request_cancel",
                    "finalize_operational_publication",
                }:
                    raise OperationalLeaseError("nested writer allowlist is event-only")
                stack.append(function)
                try:
                    return function(*args, **kwargs)
                finally:
                    stack.pop()
            if getattr(self._transactions, "dispatch", None) is not None:
                raise OperationalLeaseError("root dispatcher cannot be recursively replaced")
            dispatch = _DispatchOwner(
                self,
                function,
                job_id,
                os.getpid(),
                threading.get_ident(),
                threading.get_native_id(),
            )
            with _WRITER_REGISTRY_LOCK:
                _DISPATCH_OWNERS[id(dispatch)] = dispatch
            self._transactions.dispatch = dispatch
            try:
                return self._dispatch_writer(function, args, kwargs, job_id)
            finally:
                with _WRITER_REGISTRY_LOCK:
                    _DISPATCH_OWNERS.pop(id(dispatch), None)
                if getattr(self._transactions, "dispatch", None) is dispatch:
                    self._transactions.dispatch = None

    def _dispatch_writer(
        self,
        function: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        job_id: str,
    ) -> Any:
        self._initialize()
        name = function.__name__
        if name == "acquire_lease":
            return function(*args, **kwargs)  # Acquisition itself owns guard -> BEGIN -> selection.
        with self._connect() as lookup:
            if name in {"heartbeat_lease", "release_lease"}:
                lease = lookup.execute(
                    "SELECT job_id FROM simulation_job_leases WHERE lease_id=?", (job_id,)
                ).fetchone()
                job_id = str(lease["job_id"]) if lease is not None else ""
            row = self._operational_row(lookup, job_id) if job_id else None
        dispatch = self._transactions.dispatch
        bound_dispatch = replace(dispatch, job_id=job_id)
        with _WRITER_REGISTRY_LOCK:
            _DISPATCH_OWNERS.pop(id(dispatch), None)
            _DISPATCH_OWNERS[id(bound_dispatch)] = bound_dispatch
        self._transactions.dispatch = bound_dispatch
        try:
            if row is None:
                with self._legacy_write_transaction() as connection:
                    value = function(*args, **kwargs)
                    if name == "expire_leases":
                        for expired_job in value:
                            operational = self._operational_row(connection, expired_job)
                            if operational is not None:
                                self._terminalize_operational(
                                    connection, operational, "legacy UTC expiry veto"
                                )
                    return value
            if name == "retry_job":
                raise ValueError("operational_job_not_retryable")
            if name == "update_status_cas" and kwargs["next_status"] == RuntimeJobStatus.QUEUED:
                return None
            negative_results = {"INTERRUPTED", "CANCELLED", "TIMED_OUT", "FAILED"}
            safe = name in {"request_cancel", "release_lease", "cleanup_operational_session"}
            if name in {"finish_open_attempts", "finish_attempt"}:
                safe = kwargs.get("result") in negative_results and not kwargs.get(
                    "artifact_paths", {}
                )
            if name == "update_status_cas":
                safe = kwargs["next_status"].value in negative_results | {
                    "CANCEL_REQUESTED",
                    "CANCELLING",
                }
            if safe:
                with self._legacy_write_transaction() as conn:
                    before = self._operational_row(conn, job_id)
                    if before != row:
                        raise OperationalLeaseError("negative cleanup original row changed")
                    if name == "release_lease" and str(args[1]) != row["lease_id"]:
                        raise OperationalLeaseError(
                            "negative release requires exact original lease"
                        )
                    if name == "finish_open_attempts":
                        open_attempts = conn.execute(
                            "SELECT * FROM simulation_job_attempts WHERE job_id=? AND ended_at=''",
                            (job_id,),
                        ).fetchall()
                        if any(
                            a["worker_id"] != row["worker_id"] or a["attempt"] != row["attempt"]
                            for a in open_attempts
                        ):
                            raise OperationalLeaseError(
                                "negative finish-open requires only the exact original attempt"
                            )
                    if name == "finish_attempt":
                        attempt_row = conn.execute(
                            "SELECT * FROM simulation_job_attempts WHERE job_id=? AND attempt=?",
                            (job_id, kwargs["attempt"]),
                        ).fetchone()
                        if attempt_row is None or attempt_row["ended_at"]:
                            return None
                        if (
                            attempt_row["worker_id"] != row["worker_id"]
                            or kwargs["attempt"] != row["attempt"]
                        ):
                            raise OperationalLeaseError(
                                "negative finish requires exact original open attempt"
                            )
                    if name == "update_status_cas":
                        current = self.get_job(job_id)
                        if kwargs["expected"] != current.status:
                            return None
                        if (
                            kwargs.get("expected_worker_id", current.worker_id) != current.worker_id
                            or kwargs.get("expected_lease_id", current.lease_id) != current.lease_id
                        ):
                            return None
                        if kwargs.get("worker_id", "") not in {"", current.worker_id} or kwargs.get(
                            "lease_id", ""
                        ) not in {"", current.lease_id}:
                            raise OperationalLeaseError("negative CAS cannot replace actual owner")
                        kwargs = dict(
                            kwargs,
                            expected_worker_id=current.worker_id,
                            expected_lease_id=current.lease_id,
                        )
                    value = function(*args, **kwargs)
                    if name != "cleanup_operational_session" and (
                        name != "update_status_cas" or value is not None
                    ):
                        self._terminalize_operational(conn, row, name)
                    return value
            session = _current_session(self)
            if session is None:
                raise OperationalLeaseError("legacy/generic caller cannot mutate operational job")
            if (
                name == "heartbeat_lease"
                and kwargs["lease_ttl_seconds"] * 1_000_000_000 != session.ttl_ns
            ):
                raise OperationalLeaseError("heartbeat cannot change original TTL policy")
            purpose = "heartbeat" if name == "heartbeat_lease" else name
            with self._operational_transaction(
                session,
                job_id=job_id,
                purpose=purpose,
                operation_sha256=_digest({"name": name, "job": job_id}),
            ) as view:
                session.evaluate_locked(view)
                if name == "start_attempt" and row["lifecycle"] != "ACQUIRED":
                    raise OperationalLeaseError("second attempt bind cannot reset lifecycle")
                if name == "finalize_operational_publication":
                    self._transactions.publication_view = view
                    try:
                        value = function(*args, **kwargs)
                    finally:
                        self._transactions.publication_view = None
                else:
                    value = function(*args, **kwargs)
                if name == "update_status_cas" and value is None:
                    raise OperationalLeaseError("actual job status CAS0")
                target: dict[str, Any] = {
                    "job_snapshot_json": self._job_snapshot(view._connection, job_id)
                }
                if name == "start_attempt":
                    target.update(attempt=value.attempt, lifecycle="ATTEMPT_BOUND")
                elif name in {"finish_attempt", "finalize_operational_publication"}:
                    target.update(
                        lifecycle="TERMINAL",
                        terminal_reason="owned publication completed"
                        if name == "finalize_operational_publication"
                        else "attempt finished",
                    )
                _seal_repository_target(view, target)
                proposal = session.propose_locked(view, ttl_ns=session.ttl_ns)
                local_audit = (name == "finalize_operational_publication"
                               and self._final_publication_mode(view) == "LOCAL_TEMPORAL_PUBLICATION_V1")
                pending = self._stage_final_confirmation(view, proposal) if local_audit else None
                ack = self._commit_operational_proposal(view, proposal)
                session.confirm_committed(ack)
                if pending is not None:
                    proof = _take_final_confirmation(session, ack)
                    self._record_final_confirmation(view, proof, pending)
                return value
        finally:
            self._transactions.final_publication = None
            self._transactions.final_publication_live_sources = None
            with _WRITER_REGISTRY_LOCK:
                _DISPATCH_OWNERS.pop(id(bound_dispatch), None)
            if getattr(self._transactions, "dispatch", None) is bound_dispatch:
                self._transactions.dispatch = dispatch
                with _WRITER_REGISTRY_LOCK:
                    _DISPATCH_OWNERS[id(dispatch)] = dispatch

    @_job_writer
    def finalize_operational_publication(
        self,
        job_id: str,
        *,
        attempt: int,
        terminal: RuntimeJobStatus,
        artifact_paths: dict[str, str],
        metrics: list[dict[str, object]],
        publish: Callable[[SimulationJobRecord, dict[str, Any]], dict[str, str]],
        validate: Callable[[], None],
    ) -> dict[str, str]:
        """Preview exact final rows, write while live, then install that same frozen target."""
        self._require_active_writer()
        owner = self._writer_binding()
        view = self._transactions.publication_view
        issued = _view_record(view)
        session = issued.session
        if owner.operation != "finalize_operational_publication" or owner.job_id != job_id:
            raise OperationalLeaseError("publication requires its actual root writer")
        current = self.get_job(job_id)
        expected = (
            RuntimeJobStatus.RUNNING
            if terminal == RuntimeJobStatus.BLOCKED_BY_ENV
            else RuntimeJobStatus.FINALIZING
        )
        if (
            current.status != expected
            or current.attempt != attempt
            or view.snapshot["attempt"] != attempt
            or terminal
            not in {
                RuntimeJobStatus.SUCCEEDED,
                RuntimeJobStatus.FAILED,
                RuntimeJobStatus.BLOCKED_BY_ENV,
            }
        ):
            raise OperationalLeaseError("publication requires the actual live finalizing attempt")
        validate()
        session.evaluate_locked(view)
        conn = owner.connection
        tables = (
            "simulation_metrics",
            "simulation_artifacts",
            "simulation_job_events",
            "simulation_job_attempts",
            "simulation_job_leases",
            "simulation_jobs",
        )
        conn.execute("SAVEPOINT operational_publication_preview")
        try:
            self.save_metrics(job_id, metrics)
            self.save_artifacts(job_id, artifact_paths)
            self.finish_attempt(
                job_id,
                attempt=attempt,
                result=terminal.value,
                error="",
                artifact_paths=artifact_paths,
            )
            final = self.update_status_cas(
                job_id,
                expected=expected,
                next_status=terminal,
                reason_code=terminal.value.lower(),
                worker_id=current.worker_id,
                lease_id=current.lease_id,
                expected_worker_id=current.worker_id,
                expected_lease_id=current.lease_id,
            )
            if final is None:
                raise OperationalLeaseError("publication preview exact job CAS0")
            self.append_event(
                job_id,
                event_type="artifact_created",
                source="simulation_runtime",
                payload=dict(artifact_paths),
            )
            self.release_lease(current.lease_id)
            frozen = {
                table: tuple(
                    dict(row)
                    for row in conn.execute(
                        "SELECT * FROM " + table + " WHERE job_id=?", (job_id,)
                    ).fetchall()
                )
                for table in tables
            }
            snapshot = {
                "events": self.list_events(current.run_id),
                "attempts": self.list_attempts(current.run_id),
                "leases": self.list_leases(current.run_id),
            }
            expected_snapshot = self._job_snapshot(conn, job_id)
        finally:
            conn.execute("ROLLBACK TO operational_publication_preview")
            conn.execute("RELEASE operational_publication_preview")
        # The preview was never committed. Actual job/attempt/lease are still live here.
        self._validate_operational_row(conn, session, dict(view.snapshot))
        session.evaluate_locked(view)
        validate()
        published = publish(final, snapshot)
        if published != artifact_paths:
            raise OperationalLeaseError(
                "actual artifact paths differ from frozen publication target"
            )
        validate()
        self._validate_operational_row(conn, session, dict(view.snapshot))
        session.evaluate_locked(view)  # Fresh original D_lease bound after the filesystem work.
        if self._final_publication_mode(view) == "LOCAL_TEMPORAL_PUBLICATION_V1":
            self._transactions.final_publication = self._final_publication_sources(view, published, frozen)
        # Positive index/metrics rows precede real attempt close, lease release and terminal job.
        for table in tables:
            if table == "simulation_jobs":
                target = frozen[table][0]
                columns = tuple(key for key in target if key != "job_id")
                cursor = conn.execute(
                    "UPDATE simulation_jobs SET "
                    + ",".join(key + "=?" for key in columns)
                    + " WHERE job_id=? AND status=? AND worker_id=? AND lease_id=?",
                    tuple(target[key] for key in columns)
                    + (job_id, current.status.value, current.worker_id, current.lease_id),
                )
                if cursor.rowcount != 1:
                    raise OperationalLeaseError("publication final exact job CAS0")
            else:
                conn.execute("DELETE FROM " + table + " WHERE job_id=?", (job_id,))
                for target in frozen[table]:
                    columns = tuple(target)
                    conn.execute(
                        "INSERT INTO "
                        + table
                        + "("
                        + ",".join(columns)
                        + ") VALUES("
                        + ",".join("?" for _ in columns)
                        + ")",
                        tuple(target[key] for key in columns),
                    )
        if self._job_snapshot(conn, job_id) != expected_snapshot:
            raise OperationalLeaseError("publication actual final snapshot differs from preview")
        for table in tables:
            actual = tuple(
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM " + table + " WHERE job_id=?", (job_id,)
                ).fetchall()
            )
            if actual != frozen[table]:
                raise OperationalLeaseError(
                    "publication actual final rows differ from frozen target"
                )
        return published

    def _terminalize_operational(
        self,
        conn: sqlite3.Connection,
        before: dict[str, Any],
        reason: str,
        *,
        phase: str = "REVOKED",
    ) -> None:
        self._require_active_writer()
        if conn is not self._writer_binding().connection:
            raise OperationalLeaseError("terminal cleanup connection differs from registered owner")
        if phase not in {"REVOKED", "TERMINATED"}:
            raise OperationalLeaseError("cleanup phase must be non-authoritative")
        target = dict(before)
        target.update(
            durable_phase=phase,
            lifecycle="TERMINAL",
            terminal_reason=reason,
            row_revision=int(before["row_revision"]) + 1,
            generation=int(before["generation"]) + 1,
            job_snapshot_json=self._job_snapshot(conn, before["job_id"]),
        )
        target["proposed_row_digest"] = _canonical(target)
        columns = [key for key in target if key != "lease_id"]
        cursor = conn.execute(
            "UPDATE simulation_operational_leases_v1 SET "
            + ",".join(c + "=?" for c in columns)
            + " WHERE lease_id=? AND row_revision=? AND generation=? AND proposed_row_digest=?",
            tuple(target[c] for c in columns)
            + (
                before["lease_id"],
                before["row_revision"],
                before["generation"],
                before["proposed_row_digest"],
            ),
        )
        if cursor.rowcount != 1:
            raise OperationalLeaseError("terminal mutation lost exact generation CAS")
        _revoke_epoch(before["epoch"], reason)

    def _cleanup_operational_row(
        self, conn: sqlite3.Connection, row: dict[str, Any], reason: str
    ) -> bool:
        """Close only the original owner's residual negative state, under its exact row CAS."""
        self._require_active_writer()
        if (
            conn is not self._writer_binding().connection
            or self._operational_row(conn, row["job_id"]) != row
        ):
            raise OperationalLeaseError("cleanup requires the original registered transaction/row")
        if row["proposed_row_digest"] != _canonical(row):
            raise OperationalLeaseError("cleanup canonical row digest mismatch")
        job = conn.execute(
            "SELECT * FROM simulation_jobs WHERE job_id=?", (row["job_id"],)
        ).fetchone()
        if job is None:
            return False
        owned = job["worker_id"] == row["worker_id"] and job["lease_id"] == row["lease_id"]
        residual = owned and job["status"] in {
            "LEASED",
            "STARTING",
            "RUNNING",
            "CANCEL_REQUESTED",
            "CANCELLING",
            "FINALIZING",
        }
        attempt = conn.execute(
            "SELECT * FROM simulation_job_attempts "
            "WHERE job_id=? AND attempt=? AND worker_id=? AND ended_at=''",
            (row["job_id"], row["attempt"], row["worker_id"]),
        ).fetchone()
        lease = conn.execute(
            "SELECT * FROM simulation_job_leases "
            "WHERE lease_id=? AND job_id=? AND worker_id=? AND released_at=''",
            (row["lease_id"], row["job_id"], row["worker_id"]),
        ).fetchone()
        if not residual and attempt is None and lease is None:
            return False
        now = _dt(_now())
        if attempt is not None:
            conn.execute(
                "UPDATE simulation_job_attempts "
                "SET ended_at=?,result='INTERRUPTED',error=?,artifact_paths_json='{}' "
                "WHERE job_id=? AND attempt=? AND worker_id=? AND ended_at=''",
                (now, reason, row["job_id"], row["attempt"], row["worker_id"]),
            )
        if residual:
            conn.execute(
                "UPDATE simulation_jobs SET status='INTERRUPTED',updated_at=?,"
                "error_code='operational_epoch_ended',error_message=? "
                "WHERE job_id=? AND status=? AND worker_id=? AND lease_id=?",
                (now, reason, row["job_id"], job["status"], row["worker_id"], row["lease_id"]),
            )
        if lease is not None:
            conn.execute(
                "UPDATE simulation_job_leases SET released_at=? "
                "WHERE lease_id=? AND job_id=? AND worker_id=? AND released_at=''",
                (now, row["lease_id"], row["job_id"], row["worker_id"]),
            )
        self._terminalize_operational(conn, row, reason, phase="TERMINATED")
        return True

    @_job_writer
    def cleanup_operational_session(self, job_id: str, *, session: OperationalLeaseSession) -> None:
        self._require_active_writer()
        if (
            _current_session(self) is not session
            or session.worker._operational_lease_session is not session
            or session.job_id != job_id
            or threading.get_ident() != session.main_thread
            or threading.get_native_id() != session.main_native_thread
        ):
            raise OperationalLeaseError(
                "negative cleanup requires the actual original poll session"
            )
        conn = self._writer_binding().connection
        row = self._operational_row(conn, job_id)
        if row is None:
            return  # Acquisition never committed a row.
        domain = session.domain
        if (
            row["epoch"] != session.epoch
            or row["lease_id"] != session.lease_id
            or row["worker_id"] != session.worker_id
            or row["pid"] != domain.pid
            or row["boot_id"] != domain.boot_id
            or row["process_start_ticks"] != domain.process_start_ticks
        ):
            raise OperationalLeaseError("negative cleanup original epoch/lease/process mismatch")
        self._cleanup_operational_row(conn, row, "original worker poll ended")

    @_job_writer
    def terminate_orphaned_operational_attempts(self) -> list[str]:
        """Unknown live foreign process is never proof that an epoch is orphaned."""
        self._require_active_writer()
        conn = self._transactions.connection
        rows = conn.execute(
            "SELECT * FROM simulation_operational_leases_v1 "
            "WHERE durable_phase IN ('COMMITTED','REVOKED','TERMINATED')"
        ).fetchall()
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
                        orphan = _parse_process_start_ticks(stat, expected_pid=pid) != int(
                            row["process_start_ticks"]
                        )
            if not orphan:
                continue
            if self._cleanup_operational_row(conn, row, "orphaned epoch ended"):
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
            self._writer_binding()
            yield active
            return
        conn = sqlite3.connect(self.database_path, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        except BaseException:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass  # Preserve the original fault when the same real connection closed.
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
            conn.execute("CREATE TABLE IF NOT EXISTS simulation_publication_confirmations_v1 ("
                         "operation_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, job_id TEXT NOT NULL, "
                         "attempt INTEGER NOT NULL, epoch TEXT NOT NULL, generation INTEGER NOT NULL, "
                         "state TEXT NOT NULL CHECK(state IN ('PENDING','CONFIRMED')), "
                         "job_receipt_hash TEXT NOT NULL, event_receipt_hash TEXT NOT NULL, "
                         "artifact_manifest_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, "
                         "confirmation_hash TEXT NOT NULL, UNIQUE(run_id,attempt))")
            conn.execute("CREATE TABLE IF NOT EXISTS simulation_local_publications_v1 ("
                         "operation_id TEXT PRIMARY KEY, operation_sha256 TEXT NOT NULL, job_id TEXT NOT NULL, "
                         "attempt INTEGER NOT NULL, lease_id TEXT NOT NULL, epoch TEXT NOT NULL, "
                         "generation INTEGER NOT NULL, row_revision INTEGER NOT NULL, phase TEXT NOT NULL, "
                         "event_record_hash TEXT NOT NULL, event_receipt_hash TEXT NOT NULL, "
                         "job_receipt_hash TEXT NOT NULL, payload_json TEXT NOT NULL)")
            conn.executescript(
                "\n"
                "                CREATE TABLE IF NOT EXISTS schema_migrations (\n"
                "                    version INTEGER PRIMARY KEY,\n"
                "                    applied_at TEXT NOT NULL\n"
                "                );\n"
                "                CREATE TABLE IF NOT EXISTS simulation_jobs (\n"
                "                    job_id TEXT PRIMARY KEY,\n"
                "                    run_id TEXT NOT NULL UNIQUE,\n"
                "                    batch_id TEXT NOT NULL DEFAULT '',\n"
                "                    backend TEXT NOT NULL,\n"
                "                    scenario_id TEXT NOT NULL,\n"
                "                    control_mode TEXT NOT NULL,\n"
                "                    seed INTEGER NOT NULL,\n"
                "                    manifest_id TEXT NOT NULL,\n"
                "                    reproducibility_hash TEXT NOT NULL,\n"
                "                    status TEXT NOT NULL,\n"
                "                    draft_json TEXT NOT NULL,\n"
                "                    manifest_json TEXT NOT NULL,\n"
                "                    attempt INTEGER NOT NULL DEFAULT 0,\n"
                "                    max_attempts INTEGER NOT NULL DEFAULT 1,\n"
                "                    priority INTEGER NOT NULL DEFAULT 0,\n"
                "                    created_at TEXT NOT NULL,\n"
                "                    queued_at TEXT,\n"
                "                    started_at TEXT,\n"
                "                    completed_at TEXT,\n"
                "                    updated_at TEXT NOT NULL,\n"
                "                    timeout_seconds INTEGER NOT NULL,\n"
                "                    cancel_requested INTEGER NOT NULL DEFAULT 0,"
                "\n"
                "                    worker_id TEXT NOT NULL DEFAULT '',\n"
                "                    lease_id TEXT NOT NULL DEFAULT '',\n"
                "                    lease_expires_at TEXT,\n"
                "                    blocker_codes_json TEXT NOT NULL DEFAULT '[]"
                "',\n"
                "                    error_code TEXT NOT NULL DEFAULT '',\n"
                "                    error_message TEXT NOT NULL DEFAULT '',\n"
                "                    artifact_root TEXT NOT NULL DEFAULT '',\n"
                "                    artifact_paths_json TEXT NOT NULL DEFAULT '{"
                "}',\n"
                "                    provenance_json TEXT NOT NULL DEFAULT '{}',\n"
                "                    source_commit TEXT NOT NULL DEFAULT '',\n"
                "                    source_tree_hash TEXT NOT NULL DEFAULT ''\n"
                "                );\n"
                "                CREATE INDEX IF NOT EXISTS idx_sim_jobs_status_b"
                "ackend\n"
                "                ON simulation_jobs(status, backend, priority, cr"
                "eated_at);\n"
                "                CREATE TABLE IF NOT EXISTS simulation_job_events"
                " (\n"
                "                    event_id TEXT PRIMARY KEY,\n"
                "                    job_id TEXT NOT NULL,\n"
                "                    run_id TEXT NOT NULL,\n"
                "                    sequence INTEGER NOT NULL,\n"
                "                    stream_sequence INTEGER NOT NULL UNIQUE,\n"
                "                    event_type TEXT NOT NULL,\n"
                "                    previous_status TEXT NOT NULL DEFAULT '',\n"
                "                    next_status TEXT NOT NULL DEFAULT '',\n"
                "                    reason_code TEXT NOT NULL DEFAULT '',\n"
                "                    timestamp TEXT NOT NULL,\n"
                "                    source TEXT NOT NULL,\n"
                "                    payload_json TEXT NOT NULL,\n"
                "                    FOREIGN KEY(job_id) REFERENCES simulation_jo"
                "bs(job_id)\n"
                "                );\n"
                "                CREATE INDEX IF NOT EXISTS idx_sim_events_run_se"
                "quence\n"
                "                ON simulation_job_events(run_id, sequence);\n"
                "                CREATE TABLE IF NOT EXISTS simulation_job_leases"
                " (\n"
                "                    lease_id TEXT PRIMARY KEY,\n"
                "                    job_id TEXT NOT NULL,\n"
                "                    worker_id TEXT NOT NULL,\n"
                "                    acquired_at TEXT NOT NULL,\n"
                "                    expires_at TEXT NOT NULL,\n"
                "                    heartbeat_at TEXT NOT NULL,\n"
                "                    released_at TEXT NOT NULL DEFAULT '',\n"
                "                    FOREIGN KEY(job_id) REFERENCES simulation_jo"
                "bs(job_id)\n"
                "                );\n"
                "                CREATE TABLE IF NOT EXISTS simulation_job_attemp"
                "ts (\n"
                "                    job_id TEXT NOT NULL,\n"
                "                    run_id TEXT NOT NULL,\n"
                "                    attempt INTEGER NOT NULL,\n"
                "                    worker_id TEXT NOT NULL,\n"
                "                    started_at TEXT NOT NULL,\n"
                "                    ended_at TEXT NOT NULL DEFAULT '',\n"
                "                    result TEXT NOT NULL,\n"
                "                    error TEXT NOT NULL DEFAULT '',\n"
                "                    artifact_paths_json TEXT NOT NULL DEFAULT '{"
                "}',\n"
                "                    PRIMARY KEY(job_id, attempt),\n"
                "                    FOREIGN KEY(job_id) REFERENCES simulation_jo"
                "bs(job_id)\n"
                "                );\n"
                "                CREATE TABLE IF NOT EXISTS simulation_metrics (\n"
                "                    job_id TEXT NOT NULL,\n"
                "                    run_id TEXT NOT NULL,\n"
                "                    metric_index INTEGER NOT NULL,\n"
                "                    metric_json TEXT NOT NULL,\n"
                "                    PRIMARY KEY(job_id, metric_index),\n"
                "                    FOREIGN KEY(job_id) REFERENCES simulation_jo"
                "bs(job_id)\n"
                "                );\n"
                "                CREATE TABLE IF NOT EXISTS simulation_artifacts "
                "(\n"
                "                    job_id TEXT NOT NULL,\n"
                "                    run_id TEXT NOT NULL,\n"
                "                    name TEXT NOT NULL,\n"
                "                    relative_path TEXT NOT NULL,\n"
                "                    PRIMARY KEY(job_id, name),\n"
                "                    FOREIGN KEY(job_id) REFERENCES simulation_jo"
                "bs(job_id)\n"
                "                );\n"
                "                CREATE TABLE IF NOT EXISTS simulation_operationa"
                "l_leases_v1 (\n"
                "                    lease_id TEXT PRIMARY KEY, schema TEXT NOT N"
                "ULL,\n"
                "                    job_id TEXT NOT NULL UNIQUE, run_id TEXT NOT"
                " NULL, worker_id TEXT NOT NULL,\n"
                "                    attempt INTEGER, lifecycle TEXT NOT NULL,\n"
                "                    pid INTEGER NOT NULL, boot_id TEXT NOT NULL,"
                " process_start_ticks INTEGER NOT NULL,\n"
                "                    epoch TEXT NOT NULL, generation INTEGER NOT "
                "NULL, row_revision INTEGER NOT NULL,\n"
                "                    original_job_digest TEXT NOT NULL, original_"
                "policy_digest TEXT NOT NULL,\n"
                "                    original_acquisition_json TEXT NOT NULL, seg"
                "ment_json TEXT NOT NULL,\n"
                "                    proposal_id TEXT NOT NULL, operation_sha256 "
                "TEXT NOT NULL,\n"
                "                    job_snapshot_json TEXT NOT NULL, proposed_ro"
                "w_digest TEXT NOT NULL,\n"
                "                    durable_phase TEXT NOT NULL, terminal_reason"
                " TEXT NOT NULL,\n"
                "                    FOREIGN KEY(job_id) REFERENCES simulation_jo"
                "bs(job_id)\n"
                "                );\n"
                "                CREATE TABLE IF NOT EXISTS simulation_batches (\n"
                "                    batch_id TEXT PRIMARY KEY,\n"
                "                    manifest_json TEXT NOT NULL,\n"
                "                    run_ids_json TEXT NOT NULL,\n"
                "                    total INTEGER NOT NULL,\n"
                "                    created_at TEXT NOT NULL,\n"
                "                    completed_at TEXT NOT NULL DEFAULT ''\n"
                "                );\n"
                "                "
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
