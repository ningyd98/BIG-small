"""R113 stage A: real worker/SQLite/OC1 foundation, software-only physical seams."""

from __future__ import annotations

import copy
import hashlib
import importlib
import inspect
import json
import os
import sqlite3
import threading
from contextlib import closing, contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import pytest

MODE = "OPERATIONAL_LEASE_FOUNDATION_V1"
MODULE = "cloud_edge_robot_arm.simulation_runtime.operational_lease"


def _api():
    path = Path(__file__).resolve().parents[1] / ("src/" + MODULE.replace(".", "/") + ".py")
    assert path.exists(), "R113 planned missing operational_lease broker/transaction API"
    module = importlib.import_module(MODULE)
    for name in (
        "OperationalLeaseSession",
        "LockedLeaseView",
        "LeaseProposal",
        "LeaseCommitAck",
        "_open_worker_lease_session",
        "_worker_lease_scope",
        "_close_worker_lease_session",
    ):
        assert hasattr(module, name), f"R113 planned missing {name}"
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    assert "operational_time_mode" in inspect.signature(SimulationWorker).parameters
    return module


class _Counter:
    resolution_seconds = 1e-9

    def __init__(self):
        from tests.test_operational_time_v1 import _identity

        self.current_identity = _identity()
        self.now = 0

    def identity(self):
        return self.current_identity

    def read_ns(self):
        return self.now


def _rows(repo):
    with closing(sqlite3.connect(repo.database_path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM simulation_operational_leases_v1 ORDER BY lease_id"
            )
        ]


def _all_sql(repo):
    with closing(sqlite3.connect(repo.database_path)) as conn, conn:
        return tuple(
            tuple(conn.execute(f"SELECT * FROM {table} ORDER BY rowid"))
            for table in (
                "simulation_jobs",
                "simulation_job_leases",
                "simulation_job_events",
                "simulation_job_attempts",
                "simulation_operational_leases_v1",
                "simulation_metrics",
                "simulation_artifacts",
            )
        )


def _tx(repo, session, job, purpose="inspect"):
    return repo._operational_transaction(
        session,
        job_id=job.job_id,
        purpose=purpose,
        operation_sha256=hashlib.sha256(purpose.encode()).hexdigest(),
    )


def _evidence_fields(value):
    if is_dataclass(value) and not isinstance(value, type):
        return _evidence_fields(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return _evidence_fields(value.value)
    if isinstance(value, dict):
        return {key: _evidence_fields(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_evidence_fields(item) for item in value]
    return value


def _evidence(tmp_path, name, payload):
    (tmp_path / f"{name}.json").write_text(json.dumps(_evidence_fields(payload), indent=2) + "\n")


def _exercise(monkeypatch, tmp_path, callback, *, initialize=None, configure=None):
    module = _api()
    from cloud_edge_robot_arm.research.operational_time_v1 import _open_clock_for_test
    from cloud_edge_robot_arm.vision import operational_windows
    from tests.test_visual_worker_factory import software_factory

    broker_raw, app_raw, clocks, sessions, errors, results = [], [], [], [], [], []

    def clock_factory(destination):
        raw = _Counter()  # identity constructed in the true clock-owning thread
        owner = _open_clock_for_test(raw)
        destination.append(raw)
        clocks.append(owner)
        return owner

    monkeypatch.setattr(module, "open_operational_clock", lambda: clock_factory(broker_raw))
    monkeypatch.setattr(
        operational_windows, "open_operational_clock", lambda: clock_factory(app_raw)
    )
    received = []

    def run(worker, repo, job, root):
        try:
            runtime = received[0][3].worker_runtime
            session = worker._operational_lease_session
            assert session is not None
            assert runtime._operational_owner is not None
            assert runtime._operational_owner.task_window is not None
            sessions.append(session)
            results.append(
                callback(module, session, runtime, broker_raw[0], app_raw[0], worker, repo, job)
            )
        except BaseException as error:
            errors.append(error)
            raise

    data = software_factory(monkeypatch, tmp_path, during_initialize=initialize, during_episode=run)
    repo, job, worker, calls, received, backend, events = data
    worker.operational_time_mode = MODE
    if configure is not None:
        configure(data)
    try:
        assert worker.poll_once()
        if errors:
            raise errors[0]
        assert results, repo.get_job(job.job_id).error_message
        assert sessions[0]._closed
        assert all(owner._closed for owner in clocks)
        _evidence(
            tmp_path,
            "lifecycle",
            {
                "rows": _rows(repo),
                "calls": calls,
                "broker_identity": asdict(broker_raw[0].current_identity),
                "app_identity": asdict(app_raw[0].current_identity),
                "session_closed": sessions[0]._closed,
            },
        )
        return results[0], data
    finally:
        events.close()
        if worker._operational_lease_session is not None:
            module._close_worker_lease_session(
                worker._operational_lease_session, reason="test-finally"
            )


def test_two_issuer_threads_keep_domains_distinct(monkeypatch, tmp_path):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        from cloud_edge_robot_arm.research.operational_time_v1 import OperationalTimeError
        from cloud_edge_robot_arm.simulation_runtime.worker import (
            VISUAL_WORKER_FACTORY_SOURCE_PATHS,
        )

        assert lease_raw.now == app_raw.now == 0
        assert lease_raw.current_identity.thread_id != app_raw.current_identity.thread_id
        assert (
            lease_raw.current_identity.native_thread_id != app_raw.current_identity.native_thread_id
        )
        assert runtime._operational_owner.clock.domain.owner_thread_id == threading.get_ident()
        assert session.domain.owner_thread_id == lease_raw.current_identity.thread_id
        assert session.domain != runtime._operational_owner.clock.domain
        assert "src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py" in (
            VISUAL_WORKER_FACTORY_SOURCE_PATHS
        )
        with pytest.raises(OperationalTimeError):
            copy.copy(runtime._operational_owner.clock)
        with pytest.raises(module.OperationalLeaseError):
            copy.copy(session)
        with _tx(repo, session, job) as view:
            observation = session.evaluate_locked(view)
            assert observation.status == "VALID"
            assert observation.domain == session.domain
        # Cross-thread real OC1 read revokes that owner; no broker can read main D_app.
        errors = []
        app_clock = runtime._operational_owner.clock

        def foreign():
            try:
                app_clock.begin_event("wrong-thread")
            except OperationalTimeError as error:
                errors.append(str(error))

        thread = threading.Thread(target=foreign)
        thread.start()
        thread.join(timeout=1)
        assert not thread.is_alive() and errors
        return observation

    _exercise(monkeypatch, tmp_path, check)


@pytest.mark.parametrize(
    "variant",
    ["dict", "copy", "foreign_repo", "foreign_thread"],
    ids=["dict", "copy", "foreign_repo", "foreign_thread"],
)
def test_caller_cannot_register_locked_view(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
            SQLiteSimulationJobRepository,
        )

        before = _all_sql(repo)
        if variant == "foreign_repo":
            other = SQLiteSimulationJobRepository(repo.database_path)
        with repo.publication_guard():
            with pytest.raises(module.OperationalLeaseError):
                session.evaluate_locked({"job_id": job.job_id})
        with _tx(repo, session, job) as view:
            if variant == "dict":
                with pytest.raises(module.OperationalLeaseError):
                    session.propose_locked(dict(view.snapshot), ttl_ns=session.ttl_ns)
            elif variant == "copy":
                with pytest.raises(module.OperationalLeaseError):
                    copied = copy.copy(view)
                    session.propose_locked(copied, ttl_ns=session.ttl_ns)
            elif variant == "foreign_repo":
                assert other is not repo
                assert other.database_path.resolve() == repo.database_path.resolve()
                assert session.repository is repo
                live_before = view._connection.in_transaction
                assert live_before
                with pytest.raises(
                    module.OperationalLeaseError,
                    match="session requires exact concrete repository/job",
                ) as denial:
                    with _tx(other, session, job) as foreign:
                        session.propose_locked(foreign, ttl_ns=session.ttl_ns)
                live_after = view._connection.in_transaction
                assert live_after
            else:
                rejected = []

                def foreign():
                    try:
                        session.propose_locked(view, ttl_ns=session.ttl_ns)
                    except module.OperationalLeaseError as error:
                        rejected.append(str(error))

                thread = threading.Thread(target=foreign)
                thread.start()
                thread.join(timeout=1)
                assert rejected and not thread.is_alive()
        assert _all_sql(repo) == before
        if variant == "foreign_repo":
            _evidence(
                tmp_path,
                "foreign-repository-denial",
                {
                    "repository_id": id(repo),
                    "other_repository_id": id(other),
                    "different_repository_objects": other is not repo,
                    "repository_database": str(repo.database_path.resolve()),
                    "other_database": str(other.database_path.resolve()),
                    "session_repository_is_original": session.repository is repo,
                    "original_connection_id": id(view._connection),
                    "original_connection_in_transaction_before": live_before,
                    "original_connection_in_transaction_after": live_after,
                    "denial_type": type(denial.value).__name__,
                    "denial_message": str(denial.value),
                    "whole_sql_equal_assertion_completed": True,
                },
            )
        return variant

    _exercise(monkeypatch, tmp_path, check)


@pytest.mark.parametrize(
    "variant",
    ["rollback", "cas_zero", "connection_close", "commit_close", "replay"],
    ids=["rollback", "cas_zero", "connection_close", "commit_close", "replay"],
)
def test_locked_view_terminal_states_cannot_authorize(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        with _tx(repo, session, job, "heartbeat") as view:
            detached = session.evaluate_locked(view)
            assert detached.status == "VALID"
            proposal = session.propose_locked(view, ttl_ns=session.ttl_ns)
            if variant == "rollback":
                view._connection.execute("ROLLBACK")
            elif variant == "cas_zero":
                view._connection.execute(
                    "UPDATE simulation_operational_leases_v1 "
                    "SET row_revision=row_revision+1 WHERE job_id=?",
                    (job.job_id,),
                )
                with pytest.raises(module.OperationalLeaseError):
                    repo._commit_operational_proposal(view, proposal)
            elif variant == "connection_close":
                view._connection.close()
            elif variant == "commit_close":
                view._connection.execute("COMMIT")
                view._connection.close()
            else:
                ack = repo._commit_operational_proposal(view, proposal)
                assert session.confirm_committed(ack).status == "VALID"
                with pytest.raises(module.OperationalLeaseError):
                    session.confirm_committed(ack)
            with pytest.raises(module.OperationalLeaseError):
                session.evaluate_locked(view)
        with pytest.raises(module.OperationalLeaseError):
            session.evaluate_locked(view)
        assert detached.status == "VALID"  # immutable history cannot authorize a new mutation
        _evidence(
            tmp_path,
            "terminal-view",
            {"variant": variant, "state": view.state, "rows": _rows(repo)},
        )
        return variant

    _exercise(monkeypatch, tmp_path, check)


def test_lease_acquire_reads_after_lock(monkeypatch, tmp_path):
    module = _api()
    from cloud_edge_robot_arm.research.operational_time_v1 import _open_clock_for_test
    from tests.test_visual_worker_factory import software_factory

    started, held, released = threading.Event(), threading.Event(), threading.Event()
    clocks, raws, errors = [], [], []

    def factory():
        raw = _Counter()
        clock = _open_clock_for_test(raw)
        clocks.append(clock)
        raws.append(raw)
        started.set()
        return clock

    monkeypatch.setattr(module, "open_operational_clock", factory)
    observed = []

    def episode(worker, repo, job, root):
        observed.extend(_rows(repo))

    repo, job, worker, calls, received, backend, events = software_factory(
        monkeypatch,
        tmp_path,
        during_episode=episode,
    )
    worker.operational_time_mode = MODE

    def holder():
        try:
            with repo.publication_guard():
                with (
                    closing(sqlite3.connect(repo.database_path, isolation_level=None)) as conn,
                    conn,
                ):
                    conn.execute("BEGIN IMMEDIATE")
                    held.set()
                    assert started.wait(timeout=1)
                    raws[0].now = 2_000_000_000
                    conn.execute("ROLLBACK")
            released.set()
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert held.wait(timeout=1)
        assert worker.poll_once()
        thread.join(timeout=1)
        assert not thread.is_alive() and released.is_set() and not errors
        assert observed, repo.get_job(job.job_id).error_message
        origin = json.loads(observed[0]["original_acquisition_json"])
        assert origin["lower_ns"] == origin["upper_ns"] == 2_000_000_000
        assert all(clock._closed for clock in clocks)
        _evidence(tmp_path, "post-lock-acquisition", observed)
    finally:
        started.set()
        thread.join(timeout=1)
        events.close()


def test_heartbeat_preserves_original_task_budget(monkeypatch, tmp_path):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        owner = runtime._operational_owner
        assert owner.task_window is not None
        original = owner.export_record(owner.task_window)
        original_hard = tuple(item.deadline for item in owner._hard)
        task_matches = [
            item.deadline
            for item in owner._hard
            if item.source_id == owner._startup.job_source + ":task"
        ]
        assert len(task_matches) == 1
        original_deadline = task_matches[0]
        assert original_deadline.origin is owner.task_origin
        original_token = owner.task_origin_token
        assert original_token is not None
        acquisition = _rows(repo)[0]["original_acquisition_json"]
        generation = _rows(repo)[0]["generation"]
        lease_raw.now = 1_000_000_000
        repo.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
        row = _rows(repo)[0]
        assert row["generation"] > generation
        assert row["original_acquisition_json"] == acquisition
        assert owner.export_record(owner.task_window) == original
        assert all(
            current.deadline is saved
            for current, saved in zip(owner._hard, original_hard, strict=True)
        )
        assert row["attempt"] == repo.list_attempts(job.run_id)[0].attempt
        assert row["lifecycle"] == "ATTEMPT_BOUND"
        # Live producer identities are actual ingress records, not caller context copies.
        assert any(item["role"] == "heartbeat" for item in session.ingress_history)
        assert any(item["role"] == "main" for item in session.ingress_history)
        assert any(
            item["lifecycle"] == "ACQUIRED" and item["purpose"] == "heartbeat"
            for item in session.ingress_history
        )
        rejected = []
        before = _all_sql(repo)

        def stranger():
            try:
                repo.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
            except module.OperationalLeaseError as error:
                rejected.append(str(error))

        thread = threading.Thread(target=stranger)
        thread.start()
        thread.join(timeout=1)
        assert rejected and not thread.is_alive()
        assert _all_sql(repo) == before
        app_raw.now = original_deadline.deadline_ns
        assert not owner.clock.before_deadline(
            original_deadline, owner.clock.read_current(after=original_token)
        )
        _evidence(
            tmp_path,
            "renewal",
            {"original": original, "row": row, "ingress": session.ingress_history},
        )
        return original

    _exercise(monkeypatch, tmp_path, check)


@pytest.mark.parametrize(
    "variant", ["expired", "cancelled", "reassigned"], ids=["expired", "cancelled", "reassigned"]
)
def test_late_heartbeat_cannot_revive(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        before = _rows(repo)[0]
        if variant == "expired":
            lease_raw.now = json.loads(before["segment_json"])["deadline_ns"]
        elif variant == "cancelled":
            repo.request_cancel(job.job_id)
        else:
            repo.request_cancel(job.job_id)
            # Explicit crash/ownership fixture is negative; no replacement permission.
            with (
                repo.publication_guard(),
                closing(sqlite3.connect(repo.database_path)) as conn,
                conn,
            ):
                conn.execute(
                    "UPDATE simulation_jobs SET worker_id=?, lease_id=? WHERE job_id=?",
                    ("other", "other-lease", job.job_id),
                )
        generation = _rows(repo)[0]["generation"]
        with pytest.raises(module.OperationalLeaseError):
            repo.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
        assert _rows(repo)[0]["generation"] == generation
        from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
            SQLiteSimulationJobRepository,
        )

        other = SQLiteSimulationJobRepository(repo.database_path)
        with pytest.raises(module.OperationalLeaseError):
            other.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
        repo.release_lease(session.lease_id)
        assert _rows(repo)[0]["durable_phase"] in {"REVOKED", "TERMINATED"}
        return variant

    _exercise(monkeypatch, tmp_path, check)


@pytest.mark.parametrize(
    "variant",
    ["rollback", "cas_zero", "confirmation_lost"],
    ids=["rollback", "cas_zero", "confirmation_lost"],
)
def test_pending_proposal_requires_commit_confirmation(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        before = _rows(repo)[0]
        with _tx(repo, session, job, "heartbeat") as view:
            proposal = session.propose_locked(view, ttl_ns=session.ttl_ns)
            if variant == "rollback":
                view._connection.execute("ROLLBACK")
            elif variant == "cas_zero":
                view._connection.execute(
                    "UPDATE simulation_operational_leases_v1 "
                    "SET row_revision=row_revision+1 WHERE job_id=?",
                    (job.job_id,),
                )
                with pytest.raises(module.OperationalLeaseError):
                    repo._commit_operational_proposal(view, proposal)
            else:
                ack = repo._commit_operational_proposal(view, proposal)
                assert _rows(repo)[0]["durable_phase"] == "COMMITTED"
                trace = _lost_confirmation(monkeypatch, session, ack)
                _evidence(tmp_path, "actual-lost-confirmation", trace)
        assert proposal.state != "ACTIVE"
        with pytest.raises(module.OperationalLeaseError):
            repo.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
        rows = _rows(repo)
        if variant != "confirmation_lost":
            assert rows[0]["generation"] == before["generation"]
        _evidence(
            tmp_path,
            "unacknowledged",
            {"variant": variant, "rows": rows, "proposal_state": proposal.state},
        )
        return variant

    _exercise(monkeypatch, tmp_path, check)


@pytest.mark.parametrize(
    "variant", ["recovery_service", "manual_retry"], ids=["recovery_service", "manual_retry"]
)
def test_restart_terminates_without_reissue(monkeypatch, tmp_path, variant):
    new, job, ended_session, original, crash = _unfinished_clone(monkeypatch, tmp_path)
    module = _api()
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.recovery import ArtifactRecoveryService

    before_attempts = new.list_attempts(job.run_id)
    assert len(before_attempts) == 1 and before_attempts[0].ended_at is None
    assert ended_session._closed and ended_session._unusable.is_set()
    if variant == "recovery_service":
        ArtifactRecoveryService(
            repository=new, artifact_root=tmp_path, requeue_recoverable=True
        ).recover_interrupted_jobs()
    else:
        new.terminate_orphaned_operational_attempts()
        with pytest.raises(ValueError, match="operational"):
            new.retry_job(job.job_id)
    current = new.get_job(job.job_id)
    assert current.status != RuntimeJobStatus.QUEUED
    assert (
        new.update_status_cas(
            job.job_id,
            expected=current.status,
            next_status=RuntimeJobStatus.QUEUED,
            reason_code="forbidden-requeue",
            worker_id="",
            lease_id="",
        )
        is None
    )
    recovered = new.list_attempts(job.run_id)
    assert len(recovered) == 1 and recovered[0].attempt == before_attempts[0].attempt
    assert recovered[0].ended_at is not None and recovered[0].result == "INTERRUPTED"
    assert _rows(new)[0]["original_acquisition_json"] == crash["original_acquisition_json"]
    assert original["hard_deadlines"] and original["task_origin_event_id"]
    with pytest.raises(module.OperationalLeaseError):
        ended_session.evaluate_locked(dict(crash))
    # A still-live foreign identity is UNKNOWN; registry absence alone is insufficient.
    with new.publication_guard(), closing(sqlite3.connect(new.database_path)) as conn, conn:
        conn.execute(
            "UPDATE simulation_operational_leases_v1 SET pid=?, epoch=?, durable_phase='COMMITTED'",
            (os.getppid(), "unknown-foreign-live"),
        )
    unknown_before = _all_sql(new)
    assert new.terminate_orphaned_operational_attempts() == []
    assert _all_sql(new) == unknown_before
    # Legacy recovery remains explicitly requeueable, independent of this ended epoch.
    legacy_path = tmp_path / "legacy"
    legacy_path.mkdir()
    from tests.test_rgbd_runtime_control import _queued_closed_loop_worker

    legacy, legacy_job, legacy_worker = _queued_closed_loop_worker(legacy_path)
    lease = legacy.acquire_lease(worker_id="legacy", backend="MUJOCO", lease_ttl_seconds=30)
    assert lease is not None
    legacy.start_attempt(legacy_job.job_id, worker_id="legacy")
    with legacy.publication_guard(), closing(sqlite3.connect(legacy.database_path)) as conn, conn:
        conn.execute(
            "UPDATE simulation_jobs "
            "SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE job_id=?",
            (legacy_job.job_id,),
        )
    ArtifactRecoveryService(
        repository=legacy, artifact_root=legacy_path, requeue_recoverable=True
    ).recover_interrupted_jobs()
    assert legacy.get_job(legacy_job.job_id).status == RuntimeJobStatus.QUEUED
    _evidence(
        tmp_path,
        "restart",
        {
            "variant": variant,
            "before_attempts": before_attempts,
            "recovered_attempts": recovered,
            "current": current,
        },
    )


def _lost_confirmation(monkeypatch, session, ack):
    """Block a real dequeued confirm; caller timeout precedes the late reply."""
    held, release, returned = threading.Event(), threading.Event(), threading.Event()
    ready = threading.Event()
    original_get = session._queue.get
    requests, observations, errors = [], [], []

    def delayed_get(*args, **kwargs):
        ready.set()
        request = original_get(*args, **kwargs)
        if request.kind == "confirm":
            requests.append(request)
            held.set()
            if not release.wait(session.wait_cap + 2):
                raise RuntimeError("owned confirmation barrier was not released")
        return request

    monkeypatch.setattr(session._queue, "get", delayed_get)
    assert ready.wait(session.wait_cap), "broker did not enter owned queue seam"

    def unblock_after_timeout():
        try:
            assert held.wait(session.wait_cap + 1)
            assert session._unusable.wait(session.wait_cap + 1)
            observations.append(
                {
                    "cancelled_before_release": requests[0].cancelled.is_set(),
                    "unusable_before_release": session._unusable.is_set(),
                }
            )
        except BaseException as error:
            errors.append(error)
        finally:
            release.set()
            returned.set()

    thread = threading.Thread(target=unblock_after_timeout, name="owned-late-confirm-release")
    thread.start()
    try:
        with pytest.raises(_api().OperationalLeaseError):
            session.confirm_committed(ack)
        assert returned.wait(session.wait_cap + 1)
        assert requests[0].completed.wait(session.wait_cap + 1)
        assert observations and observations[0]["cancelled_before_release"]
        assert observations[0]["unusable_before_release"]
        assert ack._proposal.state != "ACTIVE"
        assert not errors
        return {
            "observations": observations,
            "late_reply_error": str(requests[0].error),
            "broker_thread": session.domain.owner_thread_id,
            "wait_cap": session.wait_cap,
        }
    finally:
        release.set()
        thread.join(timeout=session.wait_cap + 1)
        assert not thread.is_alive()
        monkeypatch.setattr(session._queue, "get", original_get)


def _unfinished_clone(monkeypatch, tmp_path):
    """Backup real RUNNING/open-attempt bytes; original finally cannot modify clone."""
    captured = []
    database = tmp_path / "crash-snapshot.db"

    def snapshot(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        attempts = repo.list_attempts(job.run_id)
        assert len(attempts) == 1 and attempts[0].ended_at is None
        owner = runtime._operational_owner
        assert owner is not None and owner.task_window is not None
        with repo.publication_guard(), closing(sqlite3.connect(repo.database_path)) as source:
            with closing(sqlite3.connect(database)) as destination:
                source.backup(destination)
        captured.append((session, owner.export_record(owner.task_window), _rows(repo)[0]))
        return "actual-open-attempt-backup"

    _, data = _exercise(monkeypatch, tmp_path, snapshot)
    repo, job, worker, calls, received, backend, events = data
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )

    clone = SQLiteSimulationJobRepository(database)
    assert captured[0][0]._closed and captured[0][0]._unusable.is_set()
    assert clone.list_attempts(job.run_id)[0].ended_at is None
    _evidence(
        tmp_path,
        "crash-snapshot-provenance",
        {
            "original_database": str(repo.database_path),
            "snapshot_database": str(database),
            "epoch_ended": captured[0][0]._closed,
            "snapshot_row": captured[0][2],
            "snapshot_attempts": clone.list_attempts(job.run_id),
        },
    )
    return clone, job, *captured[0]


def _denied_with_unchanged_rows(repo, operation, *, status_none_allowed=False):
    before = _all_sql(repo)
    try:
        value = operation()
    except _api().OperationalLeaseError as error:
        rejection = {"kind": "OperationalLeaseError", "reason": str(error)}
    else:
        assert status_none_allowed and value is None, (
            "authority exception required for void mutation"
        )
        rejection = {"kind": "documented-status-CAS-None"}
    assert _all_sql(repo) == before, "denied operation changed persisted effects"
    return rejection


@pytest.mark.parametrize(
    "variant",
    ["worker_mismatch", "lease_mismatch", "revoked_cleanup"],
    ids=["worker_mismatch", "lease_mismatch", "revoked_cleanup"],
)
def test_operational_status_cas_cannot_grant_without_session(monkeypatch, tmp_path, variant):
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.state_machine import ALLOWED_TRANSITIONS

    def revoked_check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        current = repo.get_job(job.job_id)
        assert current.status == RuntimeJobStatus.RUNNING
        assert current.worker_id == worker.worker_id and current.lease_id == session.lease_id
        assert RuntimeJobStatus.FINALIZING in ALLOWED_TRANSITIONS[current.status]
        session.invalidate("negative-only-cleanup-test")
        rejection = _denied_with_unchanged_rows(
            repo,
            lambda: repo.update_status_cas(
                job.job_id,
                expected=current.status,
                next_status=RuntimeJobStatus.FINALIZING,
                reason_code="forbidden-success",
                worker_id=worker.worker_id,
                lease_id=session.lease_id,
                expected_worker_id=current.worker_id,
                expected_lease_id=current.lease_id,
            ),
            status_none_allowed=True,
        )
        # The legal-state positive challenge is completed before negative cancellation.
        repo.request_cancel(job.job_id)
        operations = [
            lambda: repo.save_metrics(job.job_id, [{"metric": "forbidden-success"}]),
            lambda: repo.save_artifacts(job.job_id, {"result": "forbidden-success.json"}),
            lambda: repo.finish_attempt(
                job.job_id,
                attempt=1,
                result="SUCCEEDED",
                error="",
                artifact_paths={"result": "forbidden-success.json"},
            ),
        ]
        payload_rejections = [
            _denied_with_unchanged_rows(repo, operation) for operation in operations
        ]
        repo.release_lease(session.lease_id)
        _evidence(
            tmp_path,
            "revoked-legal-source-denials",
            {
                "source": current,
                "positive_rejection": rejection,
                "payload_rejections": payload_rejections,
            },
        )
        return variant

    if variant == "revoked_cleanup":
        _exercise(monkeypatch, tmp_path, revoked_check)
        return
    trials = [
        (RuntimeJobStatus.RUNNING, RuntimeJobStatus.FINALIZING),
        (RuntimeJobStatus.FINALIZING, RuntimeJobStatus.SUCCEEDED),
    ]
    for source, target in trials:
        trial_root = tmp_path / source.value.lower()
        trial_root.mkdir()

        def check(
            module,
            session,
            runtime,
            lease_raw,
            app_raw,
            worker,
            repo,
            job,
            *,
            source=source,
            target=target,
            trial_root=trial_root,
        ):
            current = repo.get_job(job.job_id)
            assert current.status == RuntimeJobStatus.RUNNING
            if source == RuntimeJobStatus.FINALIZING:
                # This preparation is actual authorized main-thread status CAS,
                # never foreign success.
                prepared = repo.update_status_cas(
                    job.job_id,
                    expected=RuntimeJobStatus.RUNNING,
                    next_status=RuntimeJobStatus.FINALIZING,
                    reason_code="legal-positive-source-preparation",
                    worker_id=worker.worker_id,
                    lease_id=session.lease_id,
                    expected_worker_id=current.worker_id,
                    expected_lease_id=current.lease_id,
                )
                assert prepared is not None and prepared.status == RuntimeJobStatus.FINALIZING
            current = repo.get_job(job.job_id)
            assert current.status == source and target in ALLOWED_TRANSITIONS[source]
            assert current.worker_id == worker.worker_id and current.lease_id == session.lease_id
            errors, results = [], []

            def foreign():
                try:
                    proposed_worker = (
                        "changed-worker" if variant == "worker_mismatch" else worker.worker_id
                    )
                    proposed_lease = (
                        "changed-lease" if variant == "lease_mismatch" else session.lease_id
                    )
                    results.append(
                        _denied_with_unchanged_rows(
                            repo,
                            lambda: repo.update_status_cas(
                                job.job_id,
                                expected=source,
                                next_status=target,
                                reason_code="forbidden-positive-owner",
                                worker_id=proposed_worker,
                                lease_id=proposed_lease,
                                expected_worker_id=current.worker_id,
                                expected_lease_id=current.lease_id,
                            ),
                            status_none_allowed=True,
                        )
                    )
                except BaseException as error:
                    errors.append(error)

            thread = threading.Thread(target=foreign, name="owned-foreign-status")
            thread.start()
            try:
                thread.join(timeout=2)
                assert not thread.is_alive()
                if errors:
                    raise errors[0]
                assert results
                _evidence(
                    trial_root,
                    "legal-source-positive-challenge",
                    {
                        "variant": variant,
                        "source": current,
                        "target": target.value,
                        "rejections": results,
                    },
                )
            finally:
                thread.join(timeout=2)
            return variant

        _exercise(monkeypatch, trial_root, check)


@pytest.mark.parametrize(
    "variant",
    ["direct_legacy", "forged_tls", "nested_foreign_job"],
    ids=["direct_legacy", "forged_tls", "nested_foreign_job"],
)
def test_private_transaction_helpers_require_writer_owner(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        if variant == "direct_legacy":

            def operation():
                with repo.publication_guard(), repo._legacy_write_transaction():
                    repo.save_metrics(job.job_id, [{"metric": "private-helper-bypass"}])

            _denied_with_unchanged_rows(repo, operation)
        elif variant == "forged_tls":

            def operation():
                with repo.publication_guard(), closing(sqlite3.connect(repo.database_path)) as conn:
                    conn.row_factory = sqlite3.Row
                    conn.execute("BEGIN IMMEDIATE")
                    repo._transactions.connection = conn  # connection-only descriptor, no issuer
                    try:
                        repo.save_metrics(job.job_id, [{"metric": "forged-tls"}])
                        conn.commit()
                    finally:
                        repo._transactions.connection = None
                        if conn.in_transaction:
                            conn.rollback()

            _denied_with_unchanged_rows(repo, operation)
        else:
            from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
            from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

            foreign = repo.create_job(
                run_id="actual-second-operational",
                batch_id="",
                backend="MUJOCO",
                scenario_id=job.scenario_id,
                control_mode=job.control_mode,
                seed=job.seed,
                manifest_id=job.manifest_id,
                reproducibility_hash=job.reproducibility_hash,
                draft=job.draft,
                timeout_seconds=job.timeout_seconds,
                max_attempts=1,
                artifact_root="actual-second-operational",
                source_commit=job.source_commit,
                source_tree_hash=job.source_tree_hash,
            )
            repo.update_status_cas(
                foreign.job_id,
                expected=RuntimeJobStatus.CREATED,
                next_status=RuntimeJobStatus.QUEUED,
                reason_code="second-actual-job",
                worker_id="",
                lease_id="",
            )
            second = SimulationWorker(
                worker_id="second-actual-worker",
                backend="MUJOCO",
                repository=repo,
                artifact_root=tmp_path,
                planner_factory=worker.planner_factory,
                visual_role_binding=worker.visual_role_binding,
                visual_event_repository=worker.visual_event_repository,
                visual_robot_id=worker.visual_robot_id,
                operational_time_mode=MODE,
            )
            # Stop only physical setup of this genuine second acquired/bound job.
            backend = received_backend[0]
            original_initialize = backend.initialize

            def blocked_physical_setup(config):
                raise RuntimeError("SECOND_JOB_SOFTWARE_PHYSICAL_SETUP_BLOCKED")

            monkeypatch.setattr(backend, "initialize", blocked_physical_setup)
            try:
                try:
                    second.poll_once()
                except module.OperationalLeaseError:
                    pass  # negative-only cleanup may deny old publication tail
            finally:
                monkeypatch.setattr(backend, "initialize", original_initialize)
                if second._operational_lease_session is not None:
                    module._close_worker_lease_session(
                        second._operational_lease_session, reason="second-test-finally"
                    )
            assert any(r["job_id"] == foreign.job_id for r in _rows(repo))
            with _tx(repo, session, job) as view:
                assert session.evaluate_locked(view).status == "VALID"
                before = tuple(
                    tuple(view._connection.execute(f"SELECT * FROM {table} ORDER BY rowid"))
                    for table in ("simulation_metrics", "simulation_jobs")
                )
                with pytest.raises(module.OperationalLeaseError):
                    repo.save_metrics(foreign.job_id, [{"metric": "cross-job-nested"}])
                after = tuple(
                    tuple(view._connection.execute(f"SELECT * FROM {table} ORDER BY rowid"))
                    for table in ("simulation_metrics", "simulation_jobs")
                )
                assert after == before
        return variant

    received_backend = []
    _exercise(monkeypatch, tmp_path, check, configure=lambda data: received_backend.append(data[5]))


class _CommitCloseConnection:
    """Pass-through real connection; close only after successful actual COMMIT."""

    def __init__(self, connection, trigger):
        self.connection = connection
        self.trigger = trigger

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, *args, **kwargs):
        value = self.connection.execute(sql, *args, **kwargs)
        if sql == "COMMIT":
            self.trigger(self.connection)
        return value


def _faulted_poll(monkeypatch, tmp_path, variant):
    module = _api()
    from cloud_edge_robot_arm.research.operational_time_v1 import _open_clock_for_test
    from tests.test_visual_worker_factory import software_factory

    data = software_factory(monkeypatch, tmp_path)
    repo, job, worker, calls, received, backend, events = data
    worker.operational_time_mode = MODE
    sessions, clocks, committed, faults = [], [], [], []

    def broker_clock():
        owner = _open_clock_for_test(_Counter())
        clocks.append(owner)
        session = next(s for s in module._SESSIONS.values() if s.worker is worker)
        sessions.append(session)
        if variant == "initial_heartbeat_failed":
            original_get = session._queue.get

            def fault_get(*args, **kwargs):
                request = original_get(*args, **kwargs)
                if request.view is not None and request.view.purpose == "heartbeat":
                    faults.append("actual-initial-heartbeat-queue-get-fault")
                    raise RuntimeError("actual queue receiver fault before execute")
                return request

            hooks.setattr(session._queue, "get", fault_get)
        return owner

    original_connect = repo._connect

    def after_commit(conn):
        rows = [dict(row) for row in conn.execute("SELECT * FROM simulation_operational_leases_v1")]
        if not rows:
            return
        row = rows[0]
        if variant == "initial_heartbeat_failed" and not committed:
            committed.append({"row": row, "attempts": repo.list_attempts(job.run_id)})
        elif not faults and (
            (variant == "acquire_ack_lost" and row["attempt"] is None)
            or (variant == "bind_ack_lost" and row["lifecycle"] == "ATTEMPT_BOUND")
        ):
            committed.append({"row": row, "attempts": repo.list_attempts(job.run_id)})
            faults.append("actual-connection-close-after-successful-commit")
            conn.close()

    @contextmanager
    def connections():
        active = getattr(repo._transactions, "connection", None)
        if active is not None:
            yield active
        else:
            with original_connect() as conn:
                yield _CommitCloseConnection(conn, after_commit)

    errors = []
    try:
        with monkeypatch.context() as hooks:
            hooks.setattr(module, "open_operational_clock", broker_clock)
            hooks.setattr(repo, "_connect", connections)
            try:
                worker.poll_once()
            except (module.OperationalLeaseError, sqlite3.Error) as error:
                errors.append(str(error))
            assert len(faults) == 1 and len(committed) == 1, (
                "actual one-shot commit/queue fault did not occur"
            )
            assert sessions and sessions[0]._unusable.is_set() and sessions[0]._closed
            assert all(clock._closed for clock in clocks)
            assert all(
                getattr(repo._transactions, name, None) is None
                for name in ("connection", "nonce", "commit", "writer_owner")
            )
            from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import _WRITER_OWNERS

            assert not any(
                owner.repository is repo and owner.thread_id == threading.get_ident()
                for owner in _WRITER_OWNERS.values()
            )
            released_registration = {
                "TLS": "cleared-by-real-owner-exit",
                "private_owner": "unregistered",
            }
        # Hooks are restored only after real owner/TLS cleanup has been asserted.
        assert repo._connect == original_connect
        attempts = repo.list_attempts(job.run_id)
        current = repo.get_job(job.job_id)
        leases = repo.list_leases(job.run_id)
        _evidence(
            tmp_path,
            "actual-failure-cleanup",
            {
                "variant": variant,
                "committed": committed,
                "faults": faults,
                "errors": errors,
                "after": _rows(repo),
                "attempts": attempts,
                "current": current,
                "leases": leases,
                "registration": released_registration,
                "broker_clocks_closed": [clock._closed for clock in clocks],
                "app_clock": "not issued before acquisition/initial heartbeat/bind failure",
            },
        )
        return data, committed, sessions
    finally:
        events.close()
        if worker._operational_lease_session is not None:
            module._close_worker_lease_session(
                worker._operational_lease_session, reason="fault-test-finally"
            )


@pytest.mark.parametrize(
    "variant",
    ["bind_ack_lost", "initial_heartbeat_failed", "acquire_ack_lost"],
    ids=["bind_ack_lost", "initial_heartbeat_failed", "acquire_ack_lost"],
)
def test_operational_failure_cleanup_closes_actual_attempt(monkeypatch, tmp_path, variant):
    data, committed, sessions = _faulted_poll(monkeypatch, tmp_path, variant)
    repo, job, worker, calls, received, backend, events = data
    if variant == "bind_ack_lost":
        assert committed[0]["attempts"] and committed[0]["attempts"][0].ended_at is None
    else:
        assert committed[0]["row"]["lifecycle"] == "ACQUIRED"
    assert all(
        a.ended_at is not None and a.result == "INTERRUPTED" for a in repo.list_attempts(job.run_id)
    )
    assert repo.get_job(job.job_id).status.value not in {
        "LEASED",
        "STARTING",
        "RUNNING",
        "FINALIZING",
    }
    assert all(lease.released_at is not None for lease in repo.list_leases(job.run_id))
    assert _rows(repo)[0]["durable_phase"] in {"REVOKED", "TERMINATED"}
    before = repo.list_attempts(job.run_id)
    with pytest.raises(ValueError, match="operational"):
        repo.retry_job(job.job_id)
    assert repo.list_attempts(job.run_id) == before


@pytest.mark.parametrize(
    "variant", ["committed", "revoked", "terminated"], ids=["committed", "revoked", "terminated"]
)
def test_orphan_terminal_cleanup_covers_durable_phase(monkeypatch, tmp_path, variant):
    repo, job, session, original, crash = _unfinished_clone(monkeypatch, tmp_path)
    module = _api()
    phases = {"committed": "COMMITTED", "revoked": "REVOKED", "terminated": "TERMINATED"}
    statuses = {"committed": "RUNNING", "revoked": "CANCEL_REQUESTED", "terminated": "FINALIZING"}
    with repo.publication_guard(), closing(sqlite3.connect(repo.database_path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE simulation_jobs SET status=? WHERE job_id=?", (statuses[variant], job.job_id)
        )
        row = dict(conn.execute("SELECT * FROM simulation_operational_leases_v1").fetchone())
        row.update(
            durable_phase=phases[variant],
            lifecycle="TERMINAL" if variant != "committed" else "ATTEMPT_BOUND",
        )
        row["job_snapshot_json"] = repo._job_snapshot(conn, job.job_id)
        row["proposed_row_digest"] = module._canonical(row)
        conn.execute(
            "UPDATE simulation_operational_leases_v1 SET durable_phase=?,lifecycle=?,"
            "job_snapshot_json=?,proposed_row_digest=? WHERE job_id=?",
            (
                row["durable_phase"],
                row["lifecycle"],
                row["job_snapshot_json"],
                row["proposed_row_digest"],
                job.job_id,
            ),
        )
    assert repo.list_attempts(job.run_id)[0].ended_at is None
    assert session._closed and session._unusable.is_set()
    assert repo.terminate_orphaned_operational_attempts() == [job.job_id]
    attempts = repo.list_attempts(job.run_id)
    assert (
        len(attempts) == 1
        and attempts[0].ended_at is not None
        and attempts[0].result == "INTERRUPTED"
    )
    assert repo.get_job(job.job_id).status.value == "INTERRUPTED"
    assert _rows(repo)[0]["durable_phase"] == "TERMINATED"
    assert _rows(repo)[0]["original_acquisition_json"] == crash["original_acquisition_json"]
    before = _all_sql(repo)
    assert repo.terminate_orphaned_operational_attempts() == []
    assert _all_sql(repo) == before
    _evidence(
        tmp_path,
        "durable-orphan",
        {"variant": variant, "before": row, "after": _rows(repo), "attempts": attempts},
    )


@pytest.mark.parametrize(
    "variant",
    ["purpose", "operation_digest", "identity_snapshot", "lifecycle_replay"],
    ids=["purpose", "operation_digest", "identity_snapshot", "lifecycle_replay"],
)
def test_locked_view_issued_bindings_cannot_be_retargeted(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
            SQLiteSimulationJobRepository,
        )

        other = SQLiteSimulationJobRepository(tmp_path / "foreign-issued-view.db")
        if variant == "purpose":
            mutations = [("purpose", "heartbeat")]
        elif variant == "operation_digest":
            mutations = [("operation_sha256", "0" * 64)]
        elif variant == "lifecycle_replay":
            mutations = [("state", "OPEN")]
        else:
            mutations = [
                ("_repository", other),
                ("_session", object()),
                ("_nonce", "changed"),
                ("_thread_id", -1),
                ("_native_thread_id", -1),
                ("_connection", None),
            ]
            for key in ("job_id", "lease_id", "worker_id", "attempt", "generation", "row_revision"):
                row = _rows(repo)[0]
                row[key] = -1 if key in {"attempt", "generation", "row_revision"} else "changed"
                mutations.append(("_snapshot_json", json.dumps(row, sort_keys=True)))
            mutations.append(("_snapshot_json", "{}"))
        results = []
        if variant == "identity_snapshot":
            original_database = repo.database_path
            before = _all_sql(repo)
            with _tx(repo, session, job) as view:
                try:
                    repo.database_path = tmp_path / "retargeted-resolved-database.db"
                    with pytest.raises(module.OperationalLeaseError):
                        session.evaluate_locked(view)
                    results.append(("resolved_database", "use_rejected"))
                finally:
                    repo.database_path = original_database
            assert _all_sql(repo) == before
        for field, value in mutations:
            before = _all_sql(repo)
            with _tx(repo, session, job) as view:
                if variant == "lifecycle_replay":
                    assert view._connection.in_transaction and view._proposal is None
                    assert not session._unusable.is_set()
                    assert (
                        view._connection.execute(
                            "SELECT job_id FROM simulation_jobs WHERE job_id=?", (job.job_id,)
                        ).fetchone()
                        is not None
                    )
                    module._invalidate_view(view, "actual-owner-terminal-view-transition")
                    assert view.state == "INVALIDATED" and not session._unusable.is_set()
                    with pytest.raises(module.OperationalLeaseError):
                        session.evaluate_locked(view)
                    assert view._connection.in_transaction and view._proposal is None
                    assert (
                        view._connection.execute(
                            "SELECT job_id FROM simulation_jobs WHERE job_id=?", (job.job_id,)
                        ).fetchone()
                        is not None
                    )
                try:
                    setattr(view, field, value)
                except (AttributeError, module.OperationalLeaseError):
                    results.append((field, "assignment_rejected"))
                else:
                    with pytest.raises(module.OperationalLeaseError):
                        session.evaluate_locked(view)
                    results.append((field, "use_rejected"))
            assert _all_sql(repo) == before
        _evidence(tmp_path, "issued-binding-subcases", {"variant": variant, "results": results})
        return variant

    _exercise(monkeypatch, tmp_path, check)


@pytest.mark.parametrize(
    "variant", ["exact_deadline", "after_deadline"], ids=["exact_deadline", "after_deadline"]
)
def test_confirmation_consumption_keeps_previous_bound(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        lease_raw.now = 1_000_000_000
        with _tx(repo, session, job, "heartbeat") as view:
            proposal = session.propose_locked(view, ttl_ns=session.ttl_ns)
            ack = repo._commit_operational_proposal(view, proposal)
            previous, proposed = proposal._previous, proposal._segment
            assert (
                previous is not None
                and previous.deadline.deadline_ns < proposed.deadline.deadline_ns
            )
            held, release, ready = threading.Event(), threading.Event(), threading.Event()
            original_get = session._queue.get
            seen, errors = [], []

            def delayed_get(*args, **kwargs):
                ready.set()
                request = original_get(*args, **kwargs)
                if request.kind == "consume":
                    seen.append(request)
                    held.set()
                    if not release.wait(session.wait_cap + 1):
                        raise RuntimeError("owned consume barrier not released")
                return request

            monkeypatch.setattr(session._queue, "get", delayed_get)
            assert ready.wait(session.wait_cap), "broker did not enter consume queue seam"

            def advance_original_bound():
                try:
                    assert held.wait(session.wait_cap + 1)
                    lease_raw.now = previous.deadline.deadline_ns + (variant == "after_deadline")
                    assert lease_raw.now < proposed.deadline.deadline_ns
                except BaseException as error:
                    errors.append(error)
                finally:
                    release.set()

            thread = threading.Thread(target=advance_original_bound, name="owned-consume-counter")
            thread.start()
            try:
                with pytest.raises(module.OperationalLeaseError):
                    session.confirm_committed(ack)
                assert held.is_set() and seen and not errors
                assert session._unusable.is_set()
                with pytest.raises(module.OperationalLeaseError):
                    repo.heartbeat_lease(
                        session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds
                    )
                _evidence(
                    tmp_path,
                    "prior-bound-consumption",
                    {
                        "prior": previous.receipt(),
                        "proposed": proposed.receipt(),
                        "current_ns": lease_raw.now,
                        "broker_thread": session.domain.owner_thread_id,
                    },
                )
                return variant
            finally:
                release.set()
                thread.join(timeout=session.wait_cap + 1)
                assert not thread.is_alive()
                monkeypatch.setattr(session._queue, "get", original_get)

    _exercise(monkeypatch, tmp_path, check)


def test_actual_main_and_thread_heartbeat_producers(monkeypatch, tmp_path):
    records, main_samples = [], []

    def configure(data):
        from cloud_edge_robot_arm.vision import operational_windows

        repo, job, worker, calls, received, backend, events = data
        draft = dict(job.draft)
        draft["parameter_overrides"] = {
            **draft.get("parameter_overrides", {}),
            "runtime_delay_ms": 120,
        }
        with repo.publication_guard(), closing(sqlite3.connect(repo.database_path)) as conn, conn:
            conn.execute(
                "UPDATE simulation_jobs SET draft_json=? WHERE job_id=?",
                (json.dumps(draft), job.job_id),
            )
        original = repo.heartbeat_lease

        def record_actual_call(*args, **kwargs):
            frame = inspect.currentframe()
            assert frame is not None and frame.f_back is not None
            caller = frame.f_back
            try:
                python_thread, native_thread = threading.get_ident(), threading.get_native_id()
                records.append(
                    {
                        "python_thread": python_thread,
                        "native_thread": native_thread,
                        "caller": caller.f_code.co_name,
                    }
                )
                if caller.f_code is not worker._run.__func__.__code__:
                    # The true maintenance thread never borrows main D_app handles.
                    return original(*args, **kwargs)
                session = worker._operational_lease_session
                assert session is not None
                assert (python_thread, native_thread) == (
                    session.main_thread,
                    session.main_native_thread,
                )
                owner = operational_windows._current_owner()
                assert owner is not None and owner._startup.worker is worker
                window, token, origin, clock = (
                    owner.task_window,
                    owner.task_origin_token,
                    owner.task_origin,
                    owner.clock,
                )
                assert window is not None and token is not None and origin is not None
                hard = tuple(bound.deadline for bound in owner._hard)
                origins = tuple(deadline.origin for deadline in hard)
                export_before = owner.export_record(window)
                before_current = clock.read_current(after=token)
                row_before = _rows(repo)[0]
                # Exactly one pass-through call to the original real guarded heartbeat.
                result = original(*args, **kwargs)
                after_owner = operational_windows._current_owner()
                assert after_owner is owner and after_owner.clock is clock
                assert after_owner.task_window == window and after_owner.task_origin_token is token
                assert after_owner.task_origin is origin
                assert len(after_owner._hard) == len(hard)
                assert all(
                    bound.deadline is saved
                    for bound, saved in zip(after_owner._hard, hard, strict=True)
                )
                assert all(
                    deadline.origin is saved for deadline, saved in zip(hard, origins, strict=True)
                )
                export_after = after_owner.export_record(window)
                assert export_after == export_before
                after_current = clock.read_current(after=token)
                assert before_current.domain == after_current.domain == clock.domain
                row_after = _rows(repo)[0]
                assert row_after["generation"] > row_before["generation"]
                assert (
                    row_after["original_acquisition_json"]
                    == row_before["original_acquisition_json"]
                )
                main_samples.append(
                    {
                        "owner": owner,
                        "clock": clock,
                        "window": window,
                        "token": token,
                        "origin": origin,
                        "hard": hard,
                        "deadline_origins": origins,
                        "export_before": export_before,
                        "export_after": export_after,
                        "D_app_before": {
                            "domain": asdict(before_current.domain),
                            "lower_ns": before_current.lower_ns,
                            "upper_ns": before_current.upper_ns,
                        },
                        "D_app_after": {
                            "domain": asdict(after_current.domain),
                            "lower_ns": after_current.lower_ns,
                            "upper_ns": after_current.upper_ns,
                        },
                        "row_before": row_before,
                        "row_after": row_after,
                        "python_thread": python_thread,
                        "native_thread": native_thread,
                    }
                )
                return result
            finally:
                del caller
                del frame

        monkeypatch.setattr(repo, "heartbeat_lease", record_actual_call)

    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        main = [r for r in records if r["caller"] == "_run"]
        background = [r for r in records if r["caller"] == "maintain_lease"]
        assert main and background and main_samples
        assert all(r["python_thread"] == session.main_thread for r in main)
        assert all(r["python_thread"] != session.main_thread for r in background)
        assert any(
            r["role"] == "heartbeat" and r["lifecycle"] == "ACQUIRED"
            for r in session.ingress_history
        )
        owner = runtime._operational_owner
        assert owner is not None and owner.task_window is not None
        late_export = owner.export_record(owner.task_window)
        for sample in main_samples:
            assert sample["owner"] is owner and sample["clock"] is owner.clock
            assert (
                sample["window"] == owner.task_window and sample["token"] is owner.task_origin_token
            )
            assert sample["origin"] is owner.task_origin
            assert sample["export_before"]["domain"] == late_export["domain"]
            assert (
                sample["export_before"]["task_origin_event_id"]
                == late_export["task_origin_event_id"]
            )
            # Inputs/source hashes/episode metadata may be enriched after the delay loop.
            # Every original deadline and budget remains exactly its original handle/receipt.
            assert all(
                any(bound.deadline is saved for bound in owner._hard) for saved in sample["hard"]
            )
            assert all(
                deadline.origin is saved
                for deadline, saved in zip(sample["hard"], sample["deadline_origins"], strict=True)
            )
            for deadline_receipt in sample["export_before"]["hard_deadlines"]:
                assert deadline_receipt in late_export["hard_deadlines"]
        errors = []

        def foreign():
            try:
                with module._heartbeat_lease_scope(session):
                    repo.heartbeat_lease(
                        session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds
                    )
            except module.OperationalLeaseError as error:
                errors.append(str(error))

        thread = threading.Thread(target=foreign, name="owned-false-heartbeat-scope")
        thread.start()
        try:
            thread.join(timeout=1)
            assert not thread.is_alive() and errors
        finally:
            thread.join(timeout=1)
        with pytest.raises(module.OperationalLeaseError):
            with module._heartbeat_lease_scope(session):
                repo.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
        evidence = [
            {
                key: value
                for key, value in sample.items()
                if key not in {"owner", "clock", "token", "origin", "hard", "deadline_origins"}
            }
            for sample in main_samples
        ]
        _evidence(
            tmp_path,
            "actual-heartbeat-producers",
            {
                "calls": records,
                "actual_main_before_after": evidence,
                "later_app_export": late_export,
                "source_identity": session._binding_hash,
                "ingress": session.ingress_history,
            },
        )
        return "actual-delay-loop-and-maintain-thread"

    _exercise(monkeypatch, tmp_path, check, configure=configure)


def test_normal_success_publication_uses_real_operational_authority(monkeypatch, tmp_path):
    from dataclasses import replace

    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.vision import execution

    injected = {
        "success": True,
        "status": "SUCCESS",
        "online_reported_complete": True,
        "physical_success": True,
        "failure_reason": None,
        "terminal_reason": None,
    }
    outcomes, observations, references = [], [], []
    wrapper_calls = []

    def configure(data):
        original_episode = execution.run_visual_episode

        def controlled_episode(actual_planner, actual_robot, actual_capture, policy):
            wrapper_calls.append("original-episode-called-once")
            assert len(wrapper_calls) == 1
            original = original_episode(actual_planner, actual_robot, actual_capture, policy)
            before = asdict(original)
            assert before["success"] is False and before["status"] == "FAILED"
            assert before["failure_reason"] == before["terminal_reason"] == "SOFTWARE_FACTORY_ONLY"
            controlled = replace(original, **injected)
            after = asdict(controlled)
            assert {key: value for key, value in before.items() if key not in injected} == {
                key: value for key, value in after.items() if key not in injected
            }
            for key in ("measured_lift_m", "hold_s", "placed_stable_s", "elapsed_s"):
                assert before[key] == after[key] == 0.0
            for key in ("executed_actions", "model_calls", "observation_count"):
                assert before[key] == after[key] == 0
            assert before["verification_records"] == after["verification_records"] == ()
            outcomes.append({"original": before, "injected": after})
            return controlled

        monkeypatch.setattr(execution, "run_visual_episode", controlled_episode)

    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        current = repo.get_job(job.job_id)
        attempts, leases = repo.list_attempts(job.run_id), repo.list_leases(job.run_id)
        assert current.status == RuntimeJobStatus.RUNNING
        assert session.worker is worker and session.repository is repo
        assert worker.repository is repo and worker._operational_lease_session is session
        assert session.job_id == current.job_id == job.job_id
        assert session.worker_id == current.worker_id == worker.worker_id
        assert session.lease_id == current.lease_id
        assert len(attempts) == len(leases) == 1
        attempt, lease = attempts[0], leases[0]
        assert attempt.job_id == lease.job_id == current.job_id
        assert attempt.run_id == current.run_id == job.run_id
        assert attempt.worker_id == lease.worker_id == current.worker_id
        assert attempt.attempt == current.attempt == 1
        assert attempt.ended_at is None and attempt.result == "RUNNING"
        assert lease.lease_id == current.lease_id and lease.released_at is None
        owner = runtime._operational_owner
        assert owner is not None and owner.task_window is not None
        app_clock = owner.clock
        assert owner.task_origin is not None and not app_clock._closed
        app_export = owner.export_record(owner.task_window)
        assert app_export["domain"] and app_export["task_origin_event_id"]
        assert app_export["domain"]["owner_thread_id"] == app_clock.domain.owner_thread_id
        assert app_clock.domain.owner_thread_id == session.main_thread == threading.get_ident()
        rows = _rows(repo)
        assert len(rows) == 1
        row = rows[0]
        assert row["epoch"] == session.epoch and row["lease_id"] == session.lease_id
        assert row["worker_id"] == worker.worker_id and row["attempt"] == attempt.attempt
        assert row["durable_phase"] == "COMMITTED" and row["lifecycle"] == "ATTEMPT_BOUND"
        observations.append(
            _evidence_fields(
                {
                    "job": current,
                    "attempt": attempt,
                    "lease": lease,
                    "row": row,
                    "app_export": app_export,
                    "broker_domain": session.domain,
                    "app_owner_thread": app_clock.domain.owner_thread_id,
                    "main_thread": session.main_thread,
                }
            )
        )
        references.append((session, app_clock))
        return "observed-real-open-running-authority"

    observed, data = _exercise(monkeypatch, tmp_path, check, configure=configure)
    repo, original_job, worker, calls, received, backend, events = data
    assert observed == "observed-real-open-running-authority"
    assert len(observations) == len(outcomes) == len(wrapper_calls) == len(received) == 1
    assert calls.count("episode") == calls.count("raw_exit") == calls.count("shutdown") == 1
    session, app_clock = references[0]
    assert session._closed and app_clock._closed
    assert not session._broker.is_alive() and not session.join_failed
    assert session._heartbeat_thread is not None and not session._heartbeat_thread.is_alive()
    assert worker._operational_lease_session is None
    with pytest.raises(sqlite3.ProgrammingError):
        _ = events._conn.in_transaction
    current = repo.get_job(original_job.job_id)
    attempts, leases = (
        repo.list_attempts(original_job.run_id),
        repo.list_leases(original_job.run_id),
    )
    assert current.status == RuntimeJobStatus.SUCCEEDED
    assert len(attempts) == len(leases) == 1
    attempt, lease = attempts[0], leases[0]
    during = observations[0]
    assert current.job_id == during["job"]["job_id"] == original_job.job_id
    assert current.run_id == during["job"]["run_id"] == original_job.run_id
    assert current.worker_id == attempt.worker_id == lease.worker_id == during["job"]["worker_id"]
    assert current.lease_id == lease.lease_id == during["lease"]["lease_id"]
    assert current.attempt == attempt.attempt == during["attempt"]["attempt"] == 1
    assert attempt.job_id == lease.job_id == current.job_id and attempt.run_id == current.run_id
    assert attempt.result == "SUCCEEDED" and attempt.ended_at is not None and attempt.error == ""
    assert lease.released_at is not None and current.completed_at is not None
    rows = _rows(repo)
    assert len(rows) == 1
    row = rows[0]
    assert row["epoch"] == during["row"]["epoch"] == session.epoch
    assert row["lease_id"] == current.lease_id and row["worker_id"] == current.worker_id
    assert row["original_acquisition_json"] == during["row"]["original_acquisition_json"]
    assert row["lifecycle"] == "TERMINAL" and row["durable_phase"] == "COMMITTED"
    assert row["terminal_reason"] == "owned publication completed"
    snapshot = json.loads(row["job_snapshot_json"])
    assert snapshot["job"]["job_id"] == current.job_id
    assert snapshot["job"]["run_id"] == current.run_id
    assert snapshot["job"]["status"] == "SUCCEEDED"
    assert snapshot["job"]["worker_id"] == current.worker_id
    assert snapshot["job"]["lease_id"] == current.lease_id
    assert len(snapshot["attempts"]) == 1
    assert snapshot["attempts"][0]["result"] == "SUCCEEDED"
    assert snapshot["attempts"][0]["ended_at"] == attempt.ended_at.isoformat()
    actual_events = repo.list_events(current.run_id)
    transitions = [(event.previous_status, event.next_status) for event in actual_events]
    assert ("RUNNING", "FINALIZING") in transitions
    assert ("FINALIZING", "SUCCEEDED") in transitions
    assert sum(event.event_type == "artifact_created" for event in actual_events) == 1
    assert not current.cancel_requested and current.error_code == current.error_message == ""
    assert not any(
        event.next_status in {"FAILED", "CANCELLED", "INTERRUPTED", "TIMED_OUT"}
        for event in actual_events
    )
    case_root = tmp_path.resolve()
    run_dir = (tmp_path / current.artifact_root).resolve()
    assert run_dir.is_relative_to(case_root)

    def artifact_path(key):
        relative = Path(current.artifact_paths[key])
        assert not relative.is_absolute()
        path = (tmp_path / relative).resolve()
        assert path.is_relative_to(run_dir) and path.is_file()
        assert not any(part in {"stage", "previous", "unconfirmed"} for part in relative.parts)
        return path

    def read_json(key):
        return json.loads(artifact_path(key).read_text())

    def read_jsonl(key):
        return [json.loads(line) for line in artifact_path(key).read_text().splitlines() if line]

    for key in ("job", "runtime_job"):
        value = read_json(key)
        for field in (
            "job_id",
            "run_id",
            "backend",
            "scenario_id",
            "control_mode",
            "seed",
            "attempt",
            "timeout_seconds",
            "source_commit",
            "source_tree_hash",
        ):
            assert value[field] == getattr(current, field)
        assert value["status"] == "SUCCEEDED"
        assert value["real_controller_contacted"] is False
        assert value["hardware_motion_observed"] is False
        assert value["hardware_write_operations"] == []
    result = read_json("result")
    assert result["status"] == "SUCCEEDED"
    assert all(
        result[key] is True
        for key in (
            "task_success",
            "success",
            "visual_episode_success",
            "online_reported_complete",
            "physical_success",
            "semantic_success",
        )
    )
    assert result["terminal_reason"] is None and result["failure_reason"] is None
    assert result["task_execution"] == "NOT_EXECUTED"
    assert result["episode_id"] == outcomes[0]["original"]["episode_id"] == backend._episode_id
    for key in ("executed_actions", "model_calls", "observation_count"):
        assert result[key] == 0
    for key in ("measured_lift_m", "hold_s", "placed_stable_s", "elapsed_s"):
        assert result[key] == 0.0
    assert result["verification_records"] == []
    assert result["real_controller_contacted"] is False
    assert result["hardware_motion_observed"] is False
    file_attempts = read_jsonl("attempts")
    assert len(file_attempts) == 1
    for field in ("attempt", "worker_id", "result", "error"):
        assert file_attempts[0][field] == getattr(attempt, field)
    assert file_attempts[0]["started_at"] == attempt.started_at.isoformat()
    assert file_attempts[0]["ended_at"] == attempt.ended_at.isoformat()
    for key in ("leases", "lease_history"):
        file_leases = read_jsonl(key)
        assert len(file_leases) == 1
        for field in ("job_id", "lease_id", "worker_id"):
            assert file_leases[0][field] == getattr(lease, field)
        for field in ("acquired_at", "expires_at", "heartbeat_at", "released_at"):
            assert file_leases[0][field] == getattr(lease, field).isoformat()
    file_transitions = read_jsonl("state_transitions")
    assert [(value["previous_status"], value["next_status"]) for value in file_transitions] == [
        (event.previous_status, event.next_status)
        for event in actual_events
        if event.previous_status or event.next_status
    ]
    assert sum(value["event_type"] == "artifact_created" for value in read_jsonl("events")) == 1
    consistency = read_json("evidence_consistency")
    assert consistency["consistent"] is True and consistency["run_id"] == current.run_id
    for key in (
        "api_status",
        "job_status",
        "runtime_job_status",
        "result_status",
        "final_attempt_status",
        "final_transition_status",
        "expected_terminal_status",
    ):
        assert consistency[key] == "SUCCEEDED"
    assert all(
        consistency[key] is True
        for key in ("terminal_event_present", "artifact_created_present", "lease_released")
    )
    assert consistency["file_hashes"]
    verified_files = {}
    for key, expected in consistency["file_hashes"].items():
        path = artifact_path(key)
        blob = path.read_bytes()
        assert hashlib.sha256(blob).hexdigest() == expected
        verified_files[key] = {"path": str(path), "bytes": len(blob), "sha256": expected}
    assert not list(run_dir.rglob("rejection.json"))
    _evidence(
        tmp_path,
        "software-positive-publication",
        {
            "label": "CPU_CONTROLLED_OUTCOME_NOT_PHYSICS_EVIDENCE",
            "controlled_flags_injected": True,
            "native_physics_validated": False,
            "real_controller_contacted": False,
            "hardware_motion_observed": False,
            "injected_fields": injected,
            "outcomes": outcomes,
            "during_episode": observations,
            "final_job": current,
            "final_attempts": attempts,
            "final_leases": leases,
            "final_operational_rows": rows,
            "actual_events": actual_events,
            "generated_consistency": consistency,
            "verified_files": verified_files,
            "resources": {
                "episode_wrapper_calls": len(wrapper_calls),
                "original_episode_calls": calls.count("episode"),
                "received": len(received),
                "raw_exit": calls.count("raw_exit"),
                "shutdown": calls.count("shutdown"),
                "session_closed": session._closed,
                "app_clock_closed": app_clock._closed,
                "exercise_asserted_all_owner_clocks_closed": True,
                "broker_alive": session._broker.is_alive(),
                "heartbeat_alive": session._heartbeat_thread.is_alive(),
                "events_closed_property_raised": True,
            },
        },
    )


# R158 Stage B / T1: appended detached-codec cases; the frozen A prefix stays intact.
def _b_canonical(value):
    import json

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _b_sha(value):
    import hashlib

    return hashlib.sha256(_b_canonical(value)).hexdigest()


def _b_api():
    import importlib
    from pathlib import Path

    name = "cloud_edge_robot_arm.vision.local_temporal"
    source = Path(__file__).resolve().parents[1] / "src/cloud_edge_robot_arm/vision/local_temporal.py"
    assert source.is_file(), "R158 missing detached local temporal schema contract"
    api = importlib.import_module(name)
    for symbol in (
        "LocalEnvelope",
        "LocalOriginalTime",
        "LocalAuthorityDecision",
        "LocalTransactionReceipt",
        "LocalVerificationBudgetState",
    ):
        assert hasattr(api, symbol), f"R158 missing detached local contract {symbol}"
    return api


def _b_utc(monkeypatch, basis):
    import importlib
    from datetime import datetime

    class DateTimeMeta(type):
        def __instancecheck__(cls, value):
            return isinstance(value, datetime)

    class FixtureDateTime(datetime, metaclass=DateTimeMeta):
        @classmethod
        def now(cls, tz=None):
            return basis.replace(tzinfo=None) if tz is None else basis.astimezone(tz)

    for name in (
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_owner",
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_verification",
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap",
        "cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision",
        "cloud_edge_robot_arm.repositories.event_autonomy.memory",
        "cloud_edge_robot_arm.edge.recovery.lifecycle",
        "cloud_edge_robot_arm.edge.recovery.verification_router",
        "tests.test_visual_bootstrap",
    ):
        monkeypatch.setattr(importlib.import_module(name), "datetime", FixtureDateTime)


def _b_legacy_sources(monkeypatch):
    """Use real pure builders/codecs and one real Memory repository; no worker."""
    import importlib
    from datetime import timedelta

    from cloud_edge_robot_arm.contracts.models import RecoveryBudget
    from cloud_edge_robot_arm.edge.recovery.verification_router import (
        VerificationBudget,
        VerificationBudgetState,
    )
    from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
        InMemoryEventAutonomyRepository,
    )
    from cloud_edge_robot_arm.vision.role_models import RoleModelBundle, RoleProviderSnapshot
    from cloud_edge_robot_arm.vision.worker_owner import WorkerLeaseObservation
    from tests import test_visual_bootstrap as bootstrap_fixture
    from tests import test_visual_owner_repository as owner_fixture
    from tests import test_visual_verification_repository as route_fixture

    data = owner_fixture.values()
    original = data["original"]
    basis = original.registered_at + timedelta(seconds=0.2)
    _b_utc(monkeypatch, basis)
    state = VerificationBudgetState(
        3, 2, 0, original.verification_deadline_at, VerificationBudget(3, 2, 3, 40.0)
    )
    retry = RecoveryBudget(
        budget_id="r158-legacy-original-retry",
        task_id=original.identity.task_id,
        task_total_retry_limit=2,
        per_step_retry_limit=1,
        per_skill_retry_limit=2,
        effective_retry_limit=2,
        remaining_retries=2,
        retry_deadline=original.verification_deadline_at,
        scene_version=original.contract.scene_version,
        created_at=original.registered_at,
        updated_at=original.registered_at,
    )
    # Reuse the existing immutable original builder with the actual lease identity
    # and the exact role bundle consumed by the supervision definition.
    lease = WorkerLeaseObservation(
        original.identity.job_id, original.identity.run_id, original.identity.worker_id,
        original.identity.lease_id, original.identity.attempt,
        original.registered_at - timedelta(seconds=1), basis,
        original.registered_at + timedelta(seconds=90), "a" * 64, "b" * 64, "c" * 64,
    )
    cloud = RoleProviderSnapshot(
        "CLOUD", "software-provider", "LOCAL_HOST", "software-model",
        None, None, None, "d" * 64, original.source_hashes,
    )
    bundle = RoleModelBundle(cloud, "software-edge", "e" * 64, "f" * 64)
    owner_module = importlib.import_module("cloud_edge_robot_arm.vision.owner_registration")
    identity = lease.identity(
        episode_id=original.identity.episode_id, task_id=original.identity.task_id,
        plan_id=original.identity.plan_id, robot_id=original.identity.robot_id,
    )
    original = owner_module.freeze_original_visual_plan(
        **{**original.freeze_inputs(), "identity": identity, "role_bundle_hash": bundle.digest()}
    )
    data["original"], data["current_identity"] = original, identity
    repo = InMemoryEventAutonomyRepository()
    try:
        publication = repo.initialize_visual_owner_if_absent(
            original, data["source_checkpoint"], state, retry
        )
        data["publication"] = publication
        owner_module = importlib.import_module("cloud_edge_robot_arm.vision.owner_registration")
        grounding = owner_module.bind_step_grounding(**{
            key: value for key, value in data.items() if key != "publication"
        })
        route_input_v2 = route_fixture.request_for(data)
        raw_v1 = route_input_v2.to_payload()
        raw_v1["schema_version"] = "visual.verification.route-input.v1"
        del raw_v1["grounding_receipt"]
        route_module = route_fixture.api()
        route_input_v1 = route_module.VisualVerificationRouteInput.from_payload(raw_v1)
        route_result = repo.route_visual_verification_if_current(request=route_input_v2)
        assert route_result is not None, "legacy fixture must enter the actual source route"
        assert route_result.write_disposition == "NEW_COMMIT"
        completion = route_fixture.software_completion(data)
        supervision_module = importlib.import_module(
            "cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision"
        )
        supervision_definition = supervision_module.VisualSupervisionDefinition(
            original=original, publication=publication, lease=lease,
            task_started_at=original.registered_at, task_timeout_s=60.0,
            supervision_period_s=1.0, model_snapshot_hash="1" * 64, role_bundle=bundle,
        )
        supervision_record = repo.initialize_visual_supervision_if_absent(supervision_definition)
        supervision_request = supervision_module.VisualSupervisionTransitionInput(
            record=supervision_record, original=original, publication=publication, lease=lease,
            robot_state=data["online"].robot_state, step_id="move", cursor=1,
            kind="RESERVE_CAPTURE", event_key="r158-supervision-capture",
            model_snapshot_hash="1" * 64, role_bundle=bundle,
        )
        supervision_result = repo.transition_visual_supervision_if_current(
            request=supervision_request
        )
        assert supervision_result is not None, "legacy fixture must reserve a real source claim"
        bootstrap_source = bootstrap_fixture.source.__wrapped__()
        source, bootstrap_record, promoted_original, bootstrap_retry, promotion = (
            bootstrap_fixture.promotion_sources(bootstrap_source)
        )
        bootstrap_request = bootstrap_fixture.api().VisualBootstrapTransitionInput(
            record=bootstrap_fixture.api().VisualBootstrapRecord.start(source[1]),
            kind="RESERVE_INITIAL_CAPTURE", event_key="r158-bootstrap-initial",
            current_lease=source[0], robot_state=data["online"].robot_state,
        )
        sources = {
            "visual.bootstrap.definition.v1": source[1],
            "visual.bootstrap.record.v1": bootstrap_record,
            "visual.bootstrap.transition.v1": bootstrap_request,
            "visual.bootstrap.promotion.v1": promotion,
            "visual.supervision.definition.v1": supervision_definition,
            "visual.supervision.record.v1": supervision_result.record,
            "visual.supervision.transition.v1": supervision_request,
            "visual.owner.original.v1": original,
            "visual.owner.grounding.v1": grounding,
            "visual.owner.publication.v1": publication,
            "visual.verification.route-input.v1": route_input_v1,
            "visual.verification.route-input.v2": route_input_v2,
            "visual.verification.route.v1": route_result.record,
            "visual.verification.effect-completion.v1": completion,
            "recovery.verification-budget.v1": publication.verification_budget,
            "recovery.retry-budget.v1": retry,
        }
        return {
            "sources": sources, "data": data, "basis": basis, "state": state,
            "retry": retry, "promoted_original": promoted_original,
            "bootstrap_retry": bootstrap_retry,
        }
    finally:
        repo.close()


def _b_fields():
    """The fifteen exact semantic field sets in the frozen R158 schema contract."""
    return {
        "visual.bootstrap.definition.local.v1": "scope episode_id user_instruction task_timeout_s verification_limits role_bundle_hash model_snapshot_hash source_hashes".split(),
        "visual.bootstrap.record.local.v1": "scope definition revision state initial_capture_claimed pending observation camera_descriptor_hash draft planning_source_usable proposal_hash terminal_reason adopted_original_hash history".split(),
        "visual.bootstrap.transition.local.v1": "scope bootstrap_id definition_hash expected_record_hash kind event_key robot_state claim_id observation draft".split(),
        "visual.bootstrap.promotion.local.v1": "scope bootstrap_id definition_hash expected_record_hash event_key original robot_state".split(),
        "visual.supervision.definition.local.v1": "scope original publication task_timeout_s supervision_period_s model_snapshot_hash role_bundle job_configuration_hash".split(),
        "visual.supervision.record.local.v1": "scope definition revision max_periodic_captures max_supervisor_calls captures_reserved supervisor_calls_reserved last_capture_cursor last_wait_cursor wait_seconds_reserved claims history".split(),
        "visual.supervision.transition.local.v1": "scope task_id definition_hash expected_revision expected_record_hash original publication robot_state step_id cursor kind event_key model_snapshot_hash role_bundle claim_id observation context decision wait_duration_s wait_elapsed_s".split(),
        "visual.owner.original.local.v1": "binding_scope identity contract contract_provenance proposal_hash role_bundle_hash compiler_source_hashes source_hashes requirements dependencies".split(),
        "visual.owner.grounding.local.v1": "binding_scope original_plan_hash current_identity original_requirements owner_revision state_generation source_checkpoint_hash observation_id observation_checksum_sha256 calibration_version plan_version command_seq grounding_policy_hash grounding_inputs_hash duration_check_hash grounding_source_hashes grounded_step expected_duration_s".split(),
        "visual.owner.publication.local.v1": "binding_scope mode_scope identity original_plan_hash contract_hash owner_revision state_generation checkpoint verification_budget retry_budget grounding operation_hash source_owner_revision publication_hash".split(),
        "visual.verification.route-input.local.v1": "scope original publication online step_id attempt phase event_key execution_contract completion grounding_receipt".split(),
        "visual.verification.route.local.v1": "scope input input_hash semantic_hash source_key route reasons verdicts before_verification_budget after_verification_budget produced_publication produced_publication_hash source_context_hash native_context_hash evidence_content_hash context_domains capture_claim_id camera_source_descriptor_sha256".split(),
        "visual.verification.effect-completion.local.v1": "scope result task_id plan_id robot_id step_id attempt plan_version command_seq before_observation_id execution_payload_hash source_checkpoint_hash source_hashes".split(),
        "recovery.verification-budget.local.v1": "task_id state revision content_hash".split(),
        "recovery.retry-budget.local.v1": "budget_id task_id per_step_retry_limit per_skill_retry_limit task_total_retry_limit retry_count_used task_retry_count step_retry_counts skill_retry_counts event_retry_counts retry_cooldown_ms retry_backoff_policy effective_retry_limit remaining_retries scene_version".split(),
    }


def _b_detached_original(legacy):
    """Caller-created strict descriptors: descriptive causality, no live owner."""
    from dataclasses import asdict

    from tests.test_operational_time_v1 import _clock, _event

    app, _ = _clock([0, 0, 0, 0, 0, 0])
    lease, _ = _clock([0, 0, 0, 0, 0, 0])
    try:
        token, bracket = _event(app)
        lease_token, acquisition = _event(lease)
        app_current = app.read_current(after=token)
        identity = legacy["data"]["original"].identity.to_payload()
        hashes = dict(legacy["data"]["original"].source_hashes)
        domain = json.loads(json.dumps(asdict(app.domain)))
        lease_domain = json.loads(json.dumps(asdict(lease.domain)))
        source_identity = _b_sha({"identity": identity, "sources": hashes})
        hard = [
            {"origin_event_id": token.event_identity, "source_id": source_identity + ":task",
             "budget_ns": 60_000_000_000, "deadline_ns": bracket.lower_ns + 60_000_000_000,
             "end_exclusive": True},
            {"origin_event_id": token.event_identity, "source_id": source_identity + ":verification",
             "budget_ns": 40_000_000_000, "deadline_ns": bracket.lower_ns + 40_000_000_000,
             "end_exclusive": True},
        ]
        task = {
            "schema_version": "simulation.operational-window.local.v1",
            "window_id": "r158-original-task", "kind": "bootstrap",
            "kind_policy": "HARD_ORIGINAL_TASK_LIFECYCLE", "budget_semantics": "HARD_OPEN",
            "budget_ns": 60_000_000_000, "domain": domain, "origin_domain": "ORIGINAL_TASK_D",
            "task_origin_event_id": token.event_identity, "event_id": token.event_identity,
            "source_hashes": hashes, "source_identity": source_identity,
            **{key: identity[key] for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt")},
            "fencing": legacy["data"]["original"].registered_at.isoformat(),
            "episode_id": identity["episode_id"], "parents": [], "age_constraints": [],
            "hard_deadlines": hard, "deadline_ns": hard[1]["deadline_ns"],
            "deadline_semantics": "HARD_OPEN",
            "effective_upper": {"value_ns": hard[1]["deadline_ns"], "inclusive": False},
            "lease_deadline_domain": "SEPARATE_D_LEASE_DECISION", "live_authority": "NOT_EXPORTED",
        }
        provenance = {"kind": "EXTERNAL_UTC",
                      "content_sha256": _b_sha(legacy["data"]["original"].contract.model_dump(mode="json"))}
        original = {
            "schema_version": "visual.local-original-time.v1", "app_domain": domain,
            "task_origin_event_id": token.event_identity, "task_reference": task,
            "verification_reference": copy.deepcopy(task), "recovery_reference": copy.deepcopy(task),
            "lease_identity": {
                **{key: identity[key] for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt")},
                "epoch": identity["owner_epoch"], "source_identity": source_identity,
                "original_acquisition": {
                    "domain": lease_domain, "event_identity": lease_token.event_identity,
                    "lower_ns": acquisition.lower_ns, "upper_ns": acquisition.upper_ns,
                },
            },
            "source_hashes": hashes, "contract_provenance": provenance,
        }
        return original, {
            "domain": domain, "event_identity": app_current.event_identity,
            "lower_ns": app_current.lower_ns, "upper_ns": app_current.upper_ns,
        }
    finally:
        app.close()
        lease.close()
        assert app._closed and lease._closed


def _b_decision(original, app_current, generation=1):
    acquisition = original["lease_identity"]["original_acquisition"]
    identity = original["lease_identity"]
    lease_observation = {
        "status": "UNKNOWN", "reasons": ["detached_codec_fixture_no_broker_authority"],
        "domain": acquisition["domain"], "original_acquisition": acquisition,
        "segment": {"domain": acquisition["domain"], "generation": generation,
                    "origin": acquisition, "deadline_ns": 1_000_000_000},
        "current": {"domain": acquisition["domain"], "lower_ns": 0, "upper_ns": 0},
        "job_id": identity["job_id"], "lease_id": identity["lease_id"],
        "worker_id": identity["worker_id"], "attempt": identity["attempt"],
        "generation": generation, "source_identity": identity["source_identity"],
        "schema": "simulation.operational-lease-observation.v1",
        "stage_label": "LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO",
    }
    return {
        "schema_version": "visual.local-two-authority-decision.v1",
        "operation_id": "r158-detached-operation", "operation_sha256": "a" * 64,
        "original_time_hash": _b_sha(original), "app_domain": original["app_domain"],
        "app_current": app_current, "app_verdict": {"status": "UNKNOWN", "reasons": ["detached"]},
        "app_references": [original["task_reference"]], "lease_observation": lease_observation,
        "lease_epoch": identity["epoch"], "lease_generation": generation,
        "lease_row_revision": generation, "lease_row_digest": "b" * 64,
        "source_identity": identity["source_identity"],
        **{key: identity[key] for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt")},
        "disposition": "UNKNOWN", "reasons": ["detached_codec_fixture_no_private_scope"],
    }


def _b_transaction(decision):
    return {
        "schema_version": "visual.local-publication-transaction.v1",
        "operation_id": decision["operation_id"], "operation_sha256": decision["operation_sha256"],
        "job_id": decision["job_id"], "attempt": decision["attempt"], "lease_id": decision["lease_id"],
        "epoch": decision["lease_epoch"], "generation": decision["lease_generation"],
        "row_revision": decision["lease_row_revision"], "job_database_id": "r158-detached-job-db",
        "event_repository_id": "r158-detached-event-repo", "event_kind": "codec_history",
        "event_key": "r158-detached-history", "expected_event_revision": 0, "event_revision": 1,
        "event_record_hash": "c" * 64, "job_receipt_hash": None, "event_receipt_hash": None,
        "phase": "UNKNOWN", "failure_reason": "no_private_commit",
    }


def _b_local_cases(legacy, original, app_current):
    """Semantic sources come from actual legacy codecs, never empty schema placeholders."""
    sources = legacy["sources"]
    fields = _b_fields()
    bootstrap_original = copy.deepcopy(original)
    bootstrap_definition = sources["visual.bootstrap.definition.v1"].to_payload()
    bootstrap_lease = bootstrap_definition["lease"]
    task_ns = int(bootstrap_definition["task_timeout_s"] * 1_000_000_000)
    verification_ns = int(min(
        bootstrap_definition["task_timeout_s"], bootstrap_definition["verification_limits"]["deadline_s"]
    ) * 1_000_000_000)
    bootstrap_original["source_hashes"] = copy.deepcopy(bootstrap_definition["source_hashes"])
    bootstrap_original["contract_provenance"] = {
        "kind": "EXTERNAL_UTC",
        "content_sha256": _b_sha(legacy["promoted_original"].contract.model_dump(mode="json")),
    }
    for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt"):
        bootstrap_original["lease_identity"][key] = bootstrap_lease[key]
    bootstrap_original["lease_identity"]["epoch"] = legacy["promoted_original"].identity.owner_epoch
    bootstrap_original["lease_identity"]["source_identity"] = _b_sha({
        "lease": {key: bootstrap_lease[key] for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt")},
        "sources": bootstrap_original["source_hashes"],
    })
    for name in ("task_reference", "verification_reference", "recovery_reference"):
        ref = bootstrap_original[name]
        ref["budget_ns"] = task_ns
        ref["source_hashes"] = copy.deepcopy(bootstrap_original["source_hashes"])
        ref["source_identity"] = bootstrap_original["lease_identity"]["source_identity"]
        ref["fencing"] = bootstrap_lease["acquired_at"]
        ref["episode_id"] = bootstrap_definition["episode_id"]
        for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt"):
            ref[key] = bootstrap_lease[key]
        for index, budget in enumerate((task_ns, verification_ns)):
            ref["hard_deadlines"][index]["budget_ns"] = budget
            ref["hard_deadlines"][index]["deadline_ns"] = budget
            ref["hard_deadlines"][index]["source_id"] = ref["source_identity"] + (":task" if index == 0 else ":verification")
        ref["deadline_ns"] = verification_ns
        ref["effective_upper"]["value_ns"] = verification_ns
    local = {}
    for tag, exact in fields.items():
        old_tag = tag.replace(".local.v1", ".v1")
        if tag == "visual.verification.route-input.local.v1":
            old_tag = "visual.verification.route-input.v2"
        source = sources[old_tag]
        bound_original = bootstrap_original if tag.startswith("visual.bootstrap.") else original
        decision = _b_decision(bound_original, app_current)
        transaction = _b_transaction(decision)
        raw = source.model_dump(mode="json") if old_tag == "recovery.retry-budget.v1" else source.to_payload()
        diagnostics = {
            "utc": {key: value for key, value in raw.items()
                    if key.endswith("_at") or key in ("retry_deadline",)},
            "monotonic": None,
        }
        body = {key: copy.deepcopy(raw[key]) for key in exact if key in raw}
        if "contract_provenance" in exact:
            body["contract_provenance"] = copy.deepcopy(bound_original["contract_provenance"])
        if "state" in body:
            body["state"].pop("deadline_at")
            body["state"]["original_budget_reference"] = copy.deepcopy(bound_original["verification_reference"])
        is_original = tag.endswith((".definition.local.v1", ".original.local.v1"))
        is_request = tag.endswith((".transition.local.v1", ".promotion.local.v1", ".route-input.local.v1"))
        local[tag] = {
            "schema_version": tag, "payload": body, "original_time": copy.deepcopy(bound_original),
            "decision": None if is_original or is_request else copy.deepcopy(decision),
            "transaction": None if is_original or is_request else copy.deepcopy(transaction),
            "diagnostics": diagnostics,
        }
        assert set(body) == set(exact), (tag, set(exact) - set(body))
    return local


def _b_decode_domain(tag, payload):
    import importlib

    decoders = {
        "visual.bootstrap.definition.local.v1": ("repositories.event_autonomy.visual_bootstrap", "VisualBootstrapDefinition", "from_payload"),
        "visual.bootstrap.record.local.v1": ("repositories.event_autonomy.visual_bootstrap", "VisualBootstrapRecord", "from_payload"),
        "visual.bootstrap.transition.local.v1": ("repositories.event_autonomy.visual_bootstrap", "VisualBootstrapTransitionInput", "from_payload"),
        "visual.bootstrap.promotion.local.v1": ("repositories.event_autonomy.visual_bootstrap", "VisualBootstrapPromotionInput", "from_payload"),
        "visual.supervision.definition.local.v1": ("repositories.event_autonomy.visual_supervision", "VisualSupervisionDefinition", "from_payload"),
        "visual.supervision.record.local.v1": ("repositories.event_autonomy.visual_supervision", "VisualSupervisionRecord", "from_payload"),
        "visual.supervision.transition.local.v1": ("repositories.event_autonomy.visual_supervision", "VisualSupervisionTransitionInput", "from_payload"),
        "visual.owner.original.local.v1": ("repositories.event_autonomy.visual_owner", None, "original_from_payload"),
        "visual.owner.grounding.local.v1": ("repositories.event_autonomy.visual_owner", None, "grounding_from_payload"),
        "visual.owner.publication.local.v1": ("repositories.event_autonomy.visual_owner", "VisualOwnerPublicationRecord", "from_payload"),
        "visual.verification.route-input.local.v1": ("repositories.event_autonomy.visual_verification", "VisualVerificationRouteInput", "from_payload"),
        "visual.verification.route.local.v1": ("repositories.event_autonomy.visual_verification", "VisualVerificationRouteRecord", "__call__"),
        "visual.verification.effect-completion.local.v1": ("repositories.event_autonomy.visual_verification", "VisualEffectCompletion", "from_payload"),
        "recovery.verification-budget.local.v1": ("edge.recovery.lifecycle", "LocalVerificationBudgetRecord", "from_payload"),
        "recovery.retry-budget.local.v1": ("vision.local_temporal", "LocalEnvelope", "from_payload"),
    }
    suffix, type_name, method = decoders[tag]
    module = importlib.import_module("cloud_edge_robot_arm." + suffix)
    assert type_name is None or hasattr(module, type_name), f"R158 missing local domain type {tag}"
    target = module if type_name is None else getattr(module, type_name)
    if method == "__call__":
        return target(payload)
    assert hasattr(target, method), f"R158 missing local domain decoder {tag}"
    return getattr(target, method)(payload)


def _b_duplicate_mapping(value):
    from collections.abc import Mapping

    pairs = list(value.items())
    pairs.append(pairs[0])

    class DuplicateMapping(Mapping):
        def __getitem__(self, key):
            return value[key]

        def __iter__(self):
            return (key for key, _ in pairs)

        def __len__(self):
            return len(pairs)

        def items(self):
            return iter(pairs)

    return DuplicateMapping()


@pytest.mark.parametrize("family", ["bootstrap", "supervision", "owner_grounding", "route_completion_budget"])
def test_b_local_temporal_schema_roundtrip(monkeypatch, tmp_path, family):
    api = _b_api()
    legacy = _b_legacy_sources(monkeypatch)
    original, current = _b_detached_original(legacy)
    cases = _b_local_cases(legacy, original, current)
    prefixes = {
        "bootstrap": ("visual.bootstrap.",),
        "supervision": ("visual.supervision.",),
        "owner_grounding": ("visual.owner.",),
        "route_completion_budget": ("visual.verification.", "recovery."),
    }
    selected = {tag: payload for tag, payload in cases.items() if tag.startswith(prefixes[family])}
    assert len(selected) == {"bootstrap": 4, "supervision": 3, "owner_grounding": 3, "route_completion_budget": 5}[family]
    for tag, payload in selected.items():
        envelope = api.LocalEnvelope.from_payload(payload)
        assert envelope.to_payload() == payload
        assert len(envelope.digest()) == 64
        assert api.LocalEnvelope.from_payload(envelope.to_payload()).digest() == envelope.digest()
        domain = _b_decode_domain(tag, payload)
        assert domain.to_payload() == payload, f"domain codec lost local semantic envelope: {tag}"
        assert set(payload) == {"schema_version", "payload", "original_time", "decision", "transaction", "diagnostics"}
        assert set(payload["payload"]) == set(_b_fields()[tag])
        assert _b_canonical(domain.to_payload()) == _b_canonical(payload)
        exported = envelope.to_payload()
        exported["original_time"]["source_hashes"]["caller.py"] = "f" * 64
        assert envelope.to_payload() == payload
        for section in (None, "payload", "original_time", "diagnostics"):
            for key in payload if section is None else payload[section]:
                bad = copy.deepcopy(payload)
                del (bad if section is None else bad[section])[key]
                with pytest.raises((ValueError, TypeError)):
                    api.LocalEnvelope.from_payload(bad)
            bad = copy.deepcopy(payload)
            (bad if section is None else bad[section])["unexpected"] = None
            with pytest.raises((ValueError, TypeError)):
                api.LocalEnvelope.from_payload(bad)
        for section in (None, "payload"):
            bad = copy.deepcopy(payload)
            if section is None:
                bad = _b_duplicate_mapping(bad)
            else:
                bad[section] = _b_duplicate_mapping(bad[section])
            with pytest.raises((ValueError, TypeError)):
                api.LocalEnvelope.from_payload(bad)
        for value in (float("nan"), float("inf"), float("-inf"), object()):
            bad = copy.deepcopy(payload)
            bad["diagnostics"]["monotonic"] = value
            with pytest.raises((ValueError, TypeError)):
                api.LocalEnvelope.from_payload(bad)
        for mutate in (
            lambda p: p["original_time"]["app_domain"].__setitem__("startup_counter_ns", True),
            lambda p: p["original_time"]["task_reference"].__setitem__("budget_ns", True),
            lambda p: p["original_time"]["verification_reference"]["domain"].__setitem__("startup_nonce", "foreign-equal-ns"),
            lambda p: p["original_time"]["task_reference"]["parents"].append("unissued-parent"),
        ):
            bad = copy.deepcopy(payload)
            mutate(bad)
            with pytest.raises((ValueError, TypeError)):
                api.LocalEnvelope.from_payload(bad)
    (tmp_path / f"local-{family}.json").write_bytes(_b_canonical(selected) + b"\n")


def test_b_local_codec_cannot_mint_live_authority(monkeypatch, tmp_path):
    api = _b_api()
    from cloud_edge_robot_arm.simulation_runtime import operational_lease
    from cloud_edge_robot_arm.vision import operational_windows

    registries = [
        operational_windows._OWNERS, operational_windows._PENDING, operational_windows._HANDOFFS,
        operational_windows._SCOPES, operational_windows._TRANSITIONS,
        operational_lease._SESSIONS, operational_lease._VIEWS, operational_lease._PROPOSALS,
        operational_lease._ACKS,
    ]
    before = [dict(registry) for registry in registries]
    legacy = _b_legacy_sources(monkeypatch)
    original, current = _b_detached_original(legacy)
    for tag, payload in _b_local_cases(legacy, original, current).items():
        detached = _b_decode_domain(tag, api.LocalEnvelope.from_payload(payload).to_payload())
        for symbol in ("execution_permission", "method_admitted", "execution_admitted",
                       "evaluate_locked", "confirm_locked", "NEW_COMMIT"):
            assert not hasattr(detached, symbol), (tag, symbol)
        for reference in (original["task_reference"], original["verification_reference"]):
            assert operational_windows._check_reference(reference).status == "UNKNOWN"
        assert [dict(registry) for registry in registries] == before
    assert operational_windows._current_owner() is None
    assert [dict(registry) for registry in registries] == before
    (tmp_path / "codec-registry-denial.json").write_bytes(
        _b_canonical({"registries_unchanged": True, "private_owner": None, "new_commit": False}) + b"\n"
    )


def test_b_local_original_hash_stable_across_lease_renewal(monkeypatch, tmp_path):
    api = _b_api()
    legacy = _b_legacy_sources(monkeypatch)
    original, current = _b_detached_original(legacy)
    detached = api.LocalOriginalTime.from_payload(original)
    old_digest = detached.digest()
    first = api.LocalAuthorityDecision.from_payload(_b_decision(original, current, 1))
    renewed = api.LocalAuthorityDecision.from_payload(_b_decision(original, current, 2))
    assert first.to_payload()["lease_generation"] == 1
    assert renewed.to_payload()["lease_generation"] == 2
    assert first.to_payload()["original_time_hash"] == renewed.to_payload()["original_time_hash"] == old_digest
    assert detached.digest() == old_digest and detached.to_payload() == original
    assert set(original["lease_identity"]) == {
        "job_id", "run_id", "worker_id", "lease_id", "attempt", "epoch", "source_identity", "original_acquisition"
    }
    envelope = _b_local_cases(legacy, original, current)["recovery.verification-budget.local.v1"]
    for mutate in (
        lambda p: p["original_time"]["lease_identity"].__setitem__("generation", 2),
        lambda p: p["original_time"].__setitem__("task_origin_event_id", "renewed-task-origin"),
        lambda p: p["original_time"]["verification_reference"].__setitem__("event_id", "renewed-verification-origin"),
        lambda p: p["original_time"]["source_hashes"].__setitem__("caller.py", "f" * 64),
        lambda p: p["original_time"]["verification_reference"]["hard_deadlines"][1].__setitem__("budget_ns", 41_000_000_000),
        lambda p: p["original_time"]["recovery_reference"]["domain"].__setitem__("startup_nonce", "foreign-equal-ns"),
        lambda p: p["payload"]["state"]["limits"].__setitem__("max_reobservations", 4),
        lambda p: p["decision"].__setitem__("original_time_hash", "d" * 64),
    ):
        bad = copy.deepcopy(envelope)
        mutate(bad)
        with pytest.raises((ValueError, TypeError)):
            api.LocalEnvelope.from_payload(bad)
    (tmp_path / "original-renewal.json").write_bytes(
        _b_canonical({"original_digest": old_digest, "first": first.to_payload(), "renewed": renewed.to_payload()}) + b"\n"
    )


def test_b_legacy_v1_v2_codec_bytes_and_utc_rules(monkeypatch, tmp_path):
    import os
    from pathlib import Path
    from datetime import timedelta

    from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
    from cloud_edge_robot_arm.edge.recovery import verification_router
    from cloud_edge_robot_arm.repositories.event_autonomy import visual_owner, visual_verification
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests import test_visual_verification_repository as route_fixture

    legacy = _b_legacy_sources(monkeypatch)
    goldens = {}
    for tag, source in legacy["sources"].items():
        raw = source.model_dump(mode="json") if tag == "recovery.retry-budget.v1" else source.to_payload()
        if tag == "recovery.retry-budget.v1":
            replay = type(source).model_validate_json(_b_canonical(raw))
            actual = replay.model_dump(mode="json")
        elif tag == "visual.owner.original.v1":
            actual = visual_owner.original_from_payload(raw).to_payload()
        elif tag == "visual.owner.grounding.v1":
            actual = visual_owner.grounding_from_payload(raw).to_payload()
        elif tag == "visual.verification.route.v1":
            actual = visual_verification.VisualVerificationRouteRecord(raw).to_payload()
        else:
            actual = type(source).from_payload(raw).to_payload()
        assert _b_canonical(actual) == _b_canonical(raw), tag
        goldens[tag] = _b_canonical(raw).decode()
    destination = Path(os.environ["BIGSMALL_R158_LEGACY_GOLDENS"])
    phase = os.environ["BIGSMALL_R158_COMMAND"]
    if phase != "t1_red":
        assert phase in {"t1_green", "final_new23"}
        assert destination.read_bytes() == _b_canonical(goldens) + b"\n"
    data = legacy["data"]
    request = route_fixture.request_for(data)
    original = data["original"]
    state = legacy["state"]
    at_deadline = state.deadline_at
    _b_utc(monkeypatch, at_deadline)
    assert verification_router.route_verification([], state, {DecisionAction.REOBSERVE}) == DecisionAction.STOP
    assert state.exhausted_reason == "deadline_exhausted"
    with pytest.raises(ValueError, match="deadline expired"):
        visual_owner.publication(
            original, data["source_checkpoint"], data["publication"].verification_budget,
            legacy["retry"], revision=2, generation=1, source_revision=1, operation_hash="a" * 64,
        )
    for offset, expected in ((timedelta(seconds=1), None), (timedelta(seconds=-6), "frame_ttl_expired")):
        changed = copy.deepcopy(request.to_payload())
        changed["online"]["observation"]["captured_at"] = (legacy["basis"] + offset).isoformat()
        changed["online"]["observation"]["checksum_sha256"] = ""
        changed["online"]["observation"] = RGBDObservation.model_validate(
            changed["online"]["observation"]
        ).model_dump(mode="json")
        checked = visual_verification.VisualVerificationRouteInput.from_payload(changed)
        assert checked.online().observation.captured_at == legacy["basis"] + offset
        _b_utc(monkeypatch, legacy["basis"])
        from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
        repo = InMemoryEventAutonomyRepository()
        try:
            repo.initialize_visual_owner_if_absent(
                original, data["source_checkpoint"], legacy["sources"]["visual.owner.publication.v1"].verification_budget.state,
                legacy["retry"],
            )
            # Rejoin the actual repository publication rather than forge a CAS.
            checked_payload = checked.to_payload()
            checked_payload["publication"] = repo.get_visual_owner_publication(original.identity.task_id).to_payload()
            before_hash = checked_payload["publication"]["publication_hash"]
            result = repo.route_visual_verification_if_current(
                request=visual_verification.VisualVerificationRouteInput.from_payload(checked_payload)
            )
            if expected is None:
                assert result is None, "strict legacy route rejects a future frame before write"
                assert repo.get_visual_owner_publication(original.identity.task_id).digest() == before_hash
            else:
                assert result is not None and result.record.route == "STOP"
                assert expected in result.record.reasons
        finally:
            repo.close()
    if phase == "t1_red":
        with destination.open("xb") as out:
            out.write(_b_canonical(goldens) + b"\n")
    (tmp_path / "legacy-golden-control.json").write_bytes(_b_canonical({"tags": sorted(goldens), "golden_byte_match": True}) + b"\n")
