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
    import json
    import os
    import threading
    import traceback
    import uuid
    from pathlib import Path
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

    original_init = InMemoryEventAutonomyRepository.__init__
    original_close = InMemoryEventAutonomyRepository.close
    observed_fields = ("_events", "_budgets", "_active_contracts", "_checkpoints")
    close_required_fields = (
        "_lock", "_events", "_event_hashes", "_events_by_task", "_budgets",
        "_states", "_transitions", "_failure_summaries", "_failure_hashes",
        "_completion_summaries", "_completion_hashes", "_replan_requests",
        "_replan_request_hashes", "_replan_idempotency", "_replan_results",
        "_replan_result_hashes", "_outbox", "_outbox_hashes", "_outbox_idempotency",
        "_plan_versions", "_active_contracts", "_contract_versions", "_checkpoints",
        "_checkpoint_hashes", "_checkpoints_by_task", "_apply_records",
        "_apply_by_request", "_apply_hashes", "_acks_by_key", "_ack_hashes", "_audit",
    )
    call_id = uuid.uuid4().hex
    call_pid = os.getpid()
    call_thread = threading.get_ident()
    current_test = os.environ.get("PYTEST_CURRENT_TEST")
    records = []
    tracked = []
    untracked_close_calls = []
    failures = []
    result = None

    def error_details(error):
        return {
            "type": type(error).__name__, "message": str(error),
            "traceback": "".join(traceback.format_exception(error)),
        }

    def record_for(instance):
        return next((record for candidate, record in tracked if candidate is instance), None)

    def mark_primary(instance):
        record = record_for(instance)
        assert record is not None and record["initialized"] is True
        record["role"] = "primary"

    def observed_init(instance, *args, **kwargs):
        record = {
            "object_id": id(instance), "class_module": type(instance).__module__,
            "class_qualname": type(instance).__qualname__, "role": "transitive",
            "init_attempted": True, "initialized": False, "init_error": None,
            "init_thread": threading.get_ident(), "init_native_thread": threading.get_native_id(),
            "close_calls": [], "successful_close_observed": False,
        }
        records.append(record)
        tracked.append((instance, record))
        try:
            returned = original_init(instance, *args, **kwargs)
        except BaseException as error:
            record["init_error"] = error_details(error)
            record["safe_real_close_available"] = all(
                hasattr(instance, name) for name in close_required_fields
            )
            raise
        record["initialized"] = True
        record["init_return_type"] = type(returned).__name__
        record["safe_real_close_available"] = all(
            hasattr(instance, name) for name in close_required_fields
        )
        return returned

    def observed_close(instance, *args, **kwargs):
        record = record_for(instance)
        attempt = {
            "thread": threading.get_ident(), "native_thread": threading.get_native_id(),
            "returned": False, "successful": False, "error": None,
            "post_close_field_counts": None,
        }
        if record is None:
            untracked_close_calls.append({"object_id": id(instance), "attempt": attempt})
        else:
            record["close_calls"].append(attempt)
        try:
            returned = original_close(instance, *args, **kwargs)
            attempt["returned"] = True
            attempt["return_type"] = type(returned).__name__
            attempt["return_value"] = None if returned is None else repr(returned)
            with instance._lock:
                counts = {name: len(getattr(instance, name)) for name in observed_fields}
            attempt["post_close_field_counts"] = counts
            assert all(count == 0 for count in counts.values()), (
                "real Memory close did not clear its four observed fields", counts
            )
            attempt["successful"] = True
            if record is not None:
                record["successful_close_observed"] = True
            return returned
        except BaseException as error:
            attempt["error"] = error_details(error)
            raise

    def build_legacy_sources():
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
        mark_primary(repo)
        try:
            publication = repo.initialize_visual_owner_if_absent(
                original, data["source_checkpoint"], state, retry
            )
            initial_publication = publication
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
            historical_completion = route_fixture.software_completion(data)
            route_result = repo.route_visual_verification_if_current(request=route_input_v2)
            assert route_result is not None, "legacy fixture must enter the actual source route"
            assert route_result.write_disposition == "NEW_COMMIT"
            historical_route_payload = route_result.record.to_payload()
            assert historical_route_payload["input"] == route_input_v2.to_payload()
            assert route_input_v2.to_payload()["publication"] == initial_publication.to_payload()
            current_publication = repo.get_visual_owner_publication(original.identity.task_id)
            current_pool = repo.get_verification_budget(original.identity.task_id)
            current_retry = repo.get_retry_budget(original.identity.task_id)
            current_checkpoint = repo.get_latest_execution_checkpoint(original.identity.task_id)
            assert all(value is not None for value in (
                current_publication, current_pool, current_retry, current_checkpoint
            )), "actual current task source group must remain complete"
            assert current_publication.owner_revision == initial_publication.owner_revision + 1
            assert current_publication.state_generation == initial_publication.state_generation + 1
            assert historical_route_payload["produced_publication_hash"] == current_publication.digest()
            assert historical_route_payload["produced_publication"] == current_publication.to_payload()
            assert current_publication.identity == original.identity == initial_publication.identity
            assert current_publication.original_plan_hash == initial_publication.original_plan_hash == original.digest()
            assert current_pool.content_hash == current_publication.verification_budget.content_hash
            assert _b_canonical(current_pool.to_payload()) == _b_canonical(
                current_publication.verification_budget.to_payload()
            )
            assert _b_canonical(current_pool.to_payload()) == _b_canonical(
                historical_route_payload["after_verification_budget"]
            )
            assert current_pool.state.remaining_reobservations == (
                initial_publication.verification_budget.state.remaining_reobservations - 1
            )
            assert current_pool.state.remaining_retries == initial_publication.verification_budget.state.remaining_retries
            assert current_pool.state.limits == initial_publication.verification_budget.state.limits
            assert current_pool.state.deadline_at == original.verification_deadline_at
            assert _b_canonical(current_retry.model_dump(mode="json")) == _b_canonical(
                current_publication.retry_budget.model_dump(mode="json")
            ) == _b_canonical(retry.model_dump(mode="json"))
            assert current_checkpoint.checkpoint_hash == current_publication.checkpoint.checkpoint_hash
            assert current_checkpoint.checkpoint_hash == initial_publication.checkpoint.checkpoint_hash
            assert grounding.owner_revision == data["owner_revision"]
            assert grounding.state_generation == data["state_generation"]
            # The previous request/binding stay historical. Public getters supply
            # the distinct current snapshot consumed by supervision and exports.
            publication = current_publication
            data["publication"] = current_publication
            completion = historical_completion
            supervision_module = importlib.import_module(
                "cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision"
            )
            supervision_definition = supervision_module.VisualSupervisionDefinition(
                original=original, publication=publication, lease=lease,
                task_started_at=original.registered_at, task_timeout_s=60.0,
                supervision_period_s=0.2, model_snapshot_hash="1" * 64, role_bundle=bundle,
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
                "recovery.verification-budget.v1": current_pool,
                "recovery.retry-budget.v1": current_retry,
            }
            return {
                "sources": sources, "data": data, "basis": basis, "state": current_pool.state,
                "retry": current_retry, "promoted_original": promoted_original,
                "bootstrap_retry": bootstrap_retry,
                "historical_initial_publication": initial_publication,
                "historical_route_input_v1": route_input_v1,
                "historical_route_input_v2": route_input_v2,
                "historical_route_result": route_result.record,
                "historical_grounding": grounding,
                "current_publication": current_publication,
                "current_pool": current_pool, "current_checkpoint": current_checkpoint,
            }
        finally:
            repo.close()

    try:
        with monkeypatch.context() as lifetime_patch:
            lifetime_patch.setattr(InMemoryEventAutonomyRepository, "__init__", observed_init)
            lifetime_patch.setattr(InMemoryEventAutonomyRepository, "close", observed_close)
            try:
                result = build_legacy_sources()
            except BaseException as error:
                failures.append(error)
            finally:
                for instance, record in tracked:
                    if not record["successful_close_observed"]:
                        required_present = all(
                            hasattr(instance, name) for name in close_required_fields
                        )
                        record["safe_real_close_available"] = required_present
                        if not required_present:
                            error = AssertionError(
                                "Memory initialization incomplete; genuine close requires missing fields"
                            )
                            record["incomplete_cleanup"] = error_details(error)
                            failures.append(error)
                            continue
                        try:
                            instance.close()
                        except BaseException as error:
                            failures.append(error)
                instance = record = None
    except BaseException as error:
        failures.append(error)
    finally:
        restored = {
            "__init__": InMemoryEventAutonomyRepository.__init__ is original_init,
            "close": InMemoryEventAutonomyRepository.close is original_close,
        }
        counts = {
            "allocation_attempts": sum(record["init_attempted"] for record in records),
            "initialized": sum(record["initialized"] for record in records),
            "init_failed": sum(record["init_error"] is not None for record in records),
            "primary": sum(record["role"] == "primary" for record in records),
            "transitive": sum(record["role"] == "transitive" for record in records),
            "close_attempts": sum(len(record["close_calls"]) for record in records),
            "close_returns": sum(attempt["returned"] for record in records for attempt in record["close_calls"]),
            "close_errors": sum(attempt["error"] is not None for record in records for attempt in record["close_calls"]),
            "initialized_successfully_closed": sum(
                record["initialized"] and record["successful_close_observed"] for record in records
            ),
        }
        local_checks = {
            "all_initialized_successfully_closed": counts["initialized"] == counts["initialized_successfully_closed"],
            "no_init_failures": counts["init_failed"] == 0,
            "no_close_errors": counts["close_errors"] == 0,
            "primary_exactly_one": counts["primary"] == 1,
            "transitive_at_least_one": counts["transitive"] >= 1,
            "methods_restored": all(restored.values()),
        }
        for name, passed in local_checks.items():
            if not passed:
                failures.append(AssertionError("R175 Memory lifecycle check failed: " + name))
        observation = {
            "schema_version": "bigsmall.r175-memory-lifecycle.v1",
            "call_id": call_id, "pid": call_pid, "thread": call_thread,
            "native_thread": threading.get_native_id(), "PYTEST_CURRENT_TEST": current_test,
            "nodeid": None if current_test is None else current_test.rsplit(" (", 1)[0],
            "repository_class_module": InMemoryEventAutonomyRepository.__module__,
            "repository_class_qualname": InMemoryEventAutonomyRepository.__qualname__,
            "original_method_ids": {"__init__": id(original_init), "close": id(original_close)},
            "restored_method_ids": {
                "__init__": id(InMemoryEventAutonomyRepository.__init__),
                "close": id(InMemoryEventAutonomyRepository.close),
            },
            "observed_fields": list(observed_fields), "counts": counts,
            "objects": records, "untracked_close_calls": untracked_close_calls,
            "methods_restored": restored, "local_checks": local_checks,
            "failures": [error_details(error) for error in failures],
            "success": not failures and all(local_checks.values()),
            "unobserved": {"worker_lifecycles": None, "broker_threads": None,
                "heartbeat_threads": None, "model_calls": None, "network_calls": None,
                "GPU_native_calls": None},
            "scope": "Only actual Memory allocation/init/close and method restoration observed.",
        }
        try:
            sink = os.environ.get("BIGSMALL_R175_RESOURCE_DIR")
            if sink:
                directory = Path(sink)
                assert directory.is_absolute() and directory.is_dir() and not directory.is_symlink()
                assert all(not parent.is_symlink() for parent in directory.parents)
                sidecar = directory / (call_id + ".json")
                encoded = (json.dumps(observation, allow_nan=False, sort_keys=True,
                    ensure_ascii=False, indent=2) + "\n").encode()
                with sidecar.open("xb") as stream:
                    stream.write(encoded)
        except BaseException as error:
            failures.append(error)
        finally:
            tracked.clear()
            instance = record = None
    if failures:
        if len(failures) == 1:
            raise failures[0]
        raise BaseExceptionGroup("R175 Memory fixture lifecycle failures", failures)
    return result


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
                # Caller-created SOURCE_ONLY descriptor in the unchanged raw broker shape.
                "original_acquisition": {
                    "domain": lease_domain, "event_id": lease_token.event_identity,
                    "lower_ns": acquisition.lower_ns, "upper_ns": acquisition.upper_ns,
                    "budget_ns": 1_000_000_000,
                    "deadline_ns": acquisition.lower_ns + 1_000_000_000,
                    "end_exclusive": True,
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
    # Caller-created UNKNOWN shape controls; these are not live broker receipts.
    segment = copy.deepcopy(acquisition)
    if generation > 1:
        shift = (generation - 1) * 1_000_000
        segment["event_id"] = "r158-caller-segment-" + str(generation)
        segment["lower_ns"] = acquisition["lower_ns"] + shift
        segment["upper_ns"] = acquisition["upper_ns"] + shift
        segment["deadline_ns"] = segment["lower_ns"] + segment["budget_ns"]
    exact_receipt_fields = {"domain", "event_id", "lower_ns", "upper_ns",
                            "deadline_ns", "budget_ns", "end_exclusive"}
    assert set(acquisition) == set(segment) == exact_receipt_fields
    assert segment["budget_ns"] == acquisition["budget_ns"]
    assert generation == 1 or segment != acquisition
    assert acquisition == original["lease_identity"]["original_acquisition"]
    lease_observation = {
        "status": "UNKNOWN", "reasons": ["detached_codec_fixture_no_broker_authority"],
        "domain": acquisition["domain"], "original_acquisition": acquisition,
        "segment": segment,
        "current": {"domain": acquisition["domain"],
                    "lower_ns": segment["upper_ns"], "upper_ns": segment["upper_ns"]},
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
    import json
    import hashlib

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
        legacy_raw_payload = source.model_dump(mode="json") if old_tag == "recovery.retry-budget.v1" else source.to_payload()
        raw = json.loads(json.dumps(
            legacy_raw_payload, allow_nan=False, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False,
        ))
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
        if tag == "recovery.verification-budget.local.v1":
            legacy_budget_payload = copy.deepcopy(raw)
            local_budget_binding = {
                "schema_version": tag, "task_id": body["task_id"],
                "state": body["state"], "revision": body["revision"],
            }
            body["content_hash"] = _b_sha(local_budget_binding)
            assert body["content_hash"] != legacy_budget_payload["content_hash"]
            assert set(local_budget_binding) == {"schema_version", "task_id", "state", "revision"}
            assert source.to_payload() == legacy_raw_payload
            assert json.loads(json.dumps(
                source.to_payload(), allow_nan=False, sort_keys=True,
                separators=(",", ":"), ensure_ascii=False,
            )) == legacy_budget_payload
            assert body["state"]["original_budget_reference"] == bound_original["verification_reference"]
            assert body["state"]["limits"] == legacy_budget_payload["state"]["limits"]
            for counter in (
                "remaining_reobservations", "remaining_retries", "consecutive_no_progress",
                "verification_rounds", "previous_conditions", "exhausted_reason",
            ):
                assert body["state"][counter] == legacy_budget_payload["state"][counter]
            assert body["revision"] == legacy_budget_payload["revision"]
        if tag == "visual.owner.publication.local.v1":
            content = copy.deepcopy(body)
            content.pop("publication_hash")
            body["publication_hash"] = hashlib.sha256(json.dumps({
                "schema_version": tag, "payload": content,
                "original_time": bound_original,
            }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            assert source.to_payload() == legacy_raw_payload
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


# R179 caller-created detached audit regressions; no builder installs authority.
def _r179_hash(value):
    import hashlib
    import json

    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _r179_projection(value):
    if isinstance(value, list):
        return [_r179_projection(item) for item in value]
    if isinstance(value, dict):
        if (value.get("schema_version") in _b_fields()
                and set(value) == {"schema_version", "payload", "original_time",
                                   "decision", "transaction", "diagnostics"}):
            return {
                "schema_version": value["schema_version"],
                "payload": _r179_projection(value["payload"]),
                "original_time": copy.deepcopy(value["original_time"]),
            }
        return {key: _r179_projection(item) for key, item in value.items()}
    return value


def _r179_state_hash(record):
    body = copy.deepcopy(record["payload"])
    body.pop("history")
    return _r179_hash({
        "schema_version": record["schema_version"],
        "payload": _r179_projection(body),
        "original_time": record["original_time"],
    })


def _r179_publication_hash(record):
    body = copy.deepcopy(record["payload"])
    body.pop("publication_hash")
    return _r179_hash({
        "schema_version": "visual.owner.publication.local.v1",
        "payload": _r179_projection(body),
        "original_time": record["original_time"],
    })


def _r179_envelope(tag, body, original, current):
    request = tag.endswith((".definition.local.v1", ".transition.local.v1",
                            ".promotion.local.v1", ".route-input.local.v1"))
    decision = None if request else _b_decision(original, current)
    return {
        "schema_version": tag, "payload": copy.deepcopy(body),
        "original_time": copy.deepcopy(original), "decision": decision,
        "transaction": None if request else _b_transaction(decision),
        "diagnostics": {"utc": {}, "monotonic": None},
    }


def _r179_pool(raw, original, current):
    import json

    raw = json.loads(json.dumps(raw, allow_nan=False))
    body = {key: copy.deepcopy(raw[key]) for key in _b_fields()[
        "recovery.verification-budget.local.v1"]}
    body["state"].pop("deadline_at", None)
    body["state"]["original_budget_reference"] = copy.deepcopy(
        original["verification_reference"])
    body["content_hash"] = _r179_hash({
        "schema_version": "recovery.verification-budget.local.v1",
        "task_id": body["task_id"], "state": body["state"], "revision": body["revision"],
    })
    return _r179_envelope("recovery.verification-budget.local.v1", body, original, current)


def _r179_retry(raw, original, current):
    body = {key: copy.deepcopy(raw[key]) for key in _b_fields()[
        "recovery.retry-budget.local.v1"]}
    return _r179_envelope("recovery.retry-budget.local.v1", body, original, current)


def _r179_publication(raw, original, current, verification=None, retry=None):
    body = {key: copy.deepcopy(raw[key]) for key in _b_fields()[
        "visual.owner.publication.local.v1"]}
    body["verification_budget"] = (verification if verification is not None else
        _r179_pool(raw["verification_budget"], original, current))
    body["retry_budget"] = (retry if retry is not None else
        _r179_retry(raw["retry_budget"], original, current))
    record = _r179_envelope("visual.owner.publication.local.v1", body, original, current)
    record["payload"]["publication_hash"] = _r179_publication_hash(record)
    return record


def _r179_fixture(monkeypatch):
    legacy = _b_legacy_sources(monkeypatch)
    original, current = _b_detached_original(legacy)
    cases = _b_local_cases(legacy, original, current)
    publication = _r179_publication(
        legacy["data"]["publication"].to_payload(), original, current)
    route = copy.deepcopy(cases["visual.verification.route.local.v1"])
    body = route["payload"]
    before = _r179_pool(body["before_verification_budget"], original, current)
    after = _r179_pool(body["after_verification_budget"], original, current)
    request = copy.deepcopy(cases["visual.verification.route-input.local.v1"])
    request["diagnostics"] = {"utc": {}, "monotonic": None}
    request["payload"]["publication"] = _r179_publication(
        body["input"]["publication"], original, current, verification=before)
    body["input"] = request
    body["input_hash"] = _r179_hash(request)
    body["semantic_hash"] = _r179_route_semantic(request)
    source = legacy["sources"]["visual.verification.route-input.v2"]
    prior = legacy["data"]["original"]
    observation = source.online().observation
    body["source_key"] = _r179_hash({
        "schema_version": "visual.verification.source-key.local.v1",
        "original_time_hash": _r179_hash(original), "original_plan_hash": prior.digest(),
        "task_id": prior.identity.task_id, "step_id": request["payload"]["step_id"],
        "attempt": request["payload"]["attempt"], "phase": request["payload"]["phase"],
        "frame_id": observation.observation_id, "frame_checksum": observation.checksum_sha256,
        "plan_version": prior.contract.plan_version, "command_seq": prior.contract.command_seq,
        "requirements_hash": prior.requirements[request["payload"]["step_id"]].digest(),
    })
    body["before_verification_budget"], body["after_verification_budget"] = before, after
    if body["produced_publication"] is not None:
        body["produced_publication"] = _r179_publication(
            body["produced_publication"], original, current, verification=after)
        body["produced_publication_hash"] = body["produced_publication"]["payload"]["publication_hash"]
    route["diagnostics"] = {"utc": {}, "monotonic": None}
    return {"legacy": legacy, "original": original, "current": current,
            "cases": cases, "publication": publication, "route": route}


def _r179_route_semantic(request):
    body = copy.deepcopy(request["payload"])
    body.pop("event_key")
    return _r179_hash({
        "schema_version": "visual.verification.route-input.local.v1",
        "payload": _r179_projection(body), "original_time": request["original_time"],
    })


def _r179_accepted(record):
    from cloud_edge_robot_arm.vision.local_temporal import LocalEnvelope

    decoded = LocalEnvelope.from_payload(record)
    assert decoded.to_payload() == record, "R179 complete baseline must decode before mutation"
    domain = _b_decode_domain(record["schema_version"], record)
    assert domain.to_payload() == record
    return domain


def _r179_evidence(tmp_path, seed, changed, target):
    import json

    with (tmp_path / "r179-case.json").open("x") as stream:
        json.dump({"target": target, "seed": seed, "mutation": changed,
                   "seed_sha256": _r179_hash(seed),
                   "mutation_sha256": _r179_hash(changed),
                   "claim": "Caller-created detached data; no issuer/NEW_COMMIT proof."},
                  stream, allow_nan=False, sort_keys=True, indent=2)


def _r179_initial(fixture, family):
    tag = "visual." + family + ".record.local.v1"
    record = copy.deepcopy(fixture["cases"][tag])
    body = record["payload"]
    body["revision"], body["history"] = 0, []
    record["diagnostics"] = {"utc": {}, "monotonic": None}
    if family == "bootstrap":
        limits = body["definition"]["verification_limits"]
        body["state"].update(
            remaining_reobservations=limits["max_reobservations"],
            remaining_retries=limits["max_retries"], consecutive_no_progress=0,
            previous_conditions={}, exhausted_reason=None, verification_rounds=0)
        body.update(initial_capture_claimed=False, pending=None, observation=None,
                    camera_descriptor_hash=None, draft=None, planning_source_usable=False,
                    proposal_hash=None, terminal_reason=None, adopted_original_hash=None)
    else:
        body.update(captures_reserved=0, supervisor_calls_reserved=0,
                    last_capture_cursor=0, last_wait_cursor=0, wait_seconds_reserved=0.0,
                    claims={})
    return record


def _r179_history_request(fixture, record, family, kind, event_key):
    tag = "visual." + family + ".transition.local.v1"
    request = copy.deepcopy(fixture["cases"][tag])
    request["original_time"] = copy.deepcopy(record["original_time"])
    request["diagnostics"] = {"utc": {}, "monotonic": None}
    body = request["payload"]
    body.update(kind=kind, event_key=event_key,
                definition_hash=_r179_hash(record["payload"]["definition"]),
                expected_record_hash=_r179_state_hash(record), claim_id=None,
                observation=None)
    if family == "bootstrap":
        definition = record["payload"]["definition"]
        lease = definition["lease"]
        body["bootstrap_id"] = _r179_hash([
            "visual.bootstrap.job-run.v1", lease["job_id"], lease["run_id"]])
        body["draft"] = None
    else:
        body.update(expected_revision=record["payload"]["revision"], cursor=1,
                    context=None, decision=None, wait_duration_s=None, wait_elapsed_s=None)
        if kind == "RESERVE_WAIT":
            body["wait_duration_s"] = 0.1
    return request


def _r179_history_event(record, request, post):
    operation = _r179_hash({
        "schema_version": "visual.local-history-operation.v1",
        "request": _r179_projection(request),
    })
    decision = copy.deepcopy(record["decision"])
    decision.update(operation_id=request["payload"]["event_key"],
                    operation_sha256=operation)
    transaction = _b_transaction(decision)
    transaction.update(event_key=request["payload"]["event_key"],
                       event_kind=request["schema_version"],
                       expected_event_revision=record["payload"]["revision"],
                       event_revision=post["payload"]["revision"],
                       event_record_hash=_r179_state_hash(post))
    return {"request": request, "decision": decision, "transaction": transaction,
            "resulting_record_hash": _r179_state_hash(post)}


def _r179_reserved(fixture, family="bootstrap"):
    initial = _r179_initial(fixture, family)
    kind = "RESERVE_INITIAL_CAPTURE" if family == "bootstrap" else "RESERVE_WAIT"
    request = _r179_history_request(fixture, initial, family, kind, "r179-reserve-" + family)
    post = copy.deepcopy(initial)
    body = post["payload"]
    body["revision"] = 1
    if family == "bootstrap":
        claim_id = _r179_hash([
            request["payload"]["bootstrap_id"], _r179_state_hash(initial), kind])
        body.update(initial_capture_claimed=True,
                    pending={"claim_id": claim_id, "effect": "CAPTURE"})
    else:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import _bundle

        source = request["payload"]
        definition = body["definition"]
        publication = source["publication"]
        claim_id = _r179_hash([
            "visual.supervision.claim.v1", source["definition_hash"], "WAIT", source["cursor"]])
        body.update(last_wait_cursor=1, wait_seconds_reserved=0.1)
        # Preserve semantic claim fields; no caller-created current UTC timestamp.
        body["claims"][claim_id] = {
            "kind": "WAIT", "cursor": 1, "step_id": source["step_id"],
            "publication_hash": publication["publication_hash"],
            "checkpoint_hash": publication["checkpoint"]["checkpoint_hash"],
            "state_generation": publication["state_generation"],
            "observation": None, "context": None, "decision": None,
            "model_snapshot_hash": source["model_snapshot_hash"],
            "cloud_snapshot": copy.deepcopy(definition["role_bundle"]["cloud_snapshot"]),
            "cloud_snapshot_hash": _bundle(definition["role_bundle"]).cloud_snapshot.digest(),
            "source_hashes": copy.deepcopy(source["original"]["source_hashes"]),
            "wait_duration_s": 0.1, "wait_elapsed_s": None, "status": "WAIT_PENDING",
        }
    event = _r179_history_event(initial, request, post)
    body["history"] = [event]
    post["decision"], post["transaction"] = copy.deepcopy(event["decision"]), copy.deepcopy(event["transaction"])
    return initial, post, claim_id


def _r179_completed(fixture, family):
    initial, reserved, claim_id = _r179_reserved(fixture, family)
    kind = "COMPLETE_CAPTURE" if family == "bootstrap" else "COMPLETE_WAIT"
    request = _r179_history_request(fixture, reserved, family, kind, "r179-complete-" + family)
    request["payload"]["claim_id"] = claim_id
    post = copy.deepcopy(reserved)
    post["payload"]["revision"] = 2
    if family == "bootstrap":
        observation = copy.deepcopy(fixture["cases"][
            "visual.bootstrap.record.local.v1"]["payload"]["observation"])
        assert observation is not None
        request["payload"]["observation"] = observation
        camera = {"schema_version": "visual.rgbd.camera-source-descriptor.v1",
                  **{key: observation[key] for key in (
                      "source", "width", "height", "intrinsics", "camera_to_world",
                      "depth_convention", "calibration_version")}}
        post["payload"].update(observation=observation,
                               camera_descriptor_hash=_r179_hash(camera), pending=None)
    else:
        request["payload"]["wait_elapsed_s"] = 0.05
        post["payload"]["claims"][claim_id].update(
            status="WAIT_COMPLETE", wait_elapsed_s=0.05)
    event = _r179_history_event(reserved, request, post)
    post["payload"]["history"].append(event)
    post["decision"], post["transaction"] = copy.deepcopy(event["decision"]), copy.deepcopy(event["transaction"])
    return initial, reserved, post


@pytest.mark.parametrize("mutation", [
    "request_event", "operation", "request_kind", "result_hash",
    "cas_prestate", "transaction_event", "final_state",
])
def test_r179_history_binding_rejects(monkeypatch, tmp_path, mutation):
    fixture = _r179_fixture(monkeypatch)
    initial, seed, _ = _r179_reserved(fixture)
    _r179_accepted(initial)
    _r179_accepted(seed)
    changed = copy.deepcopy(seed)
    event = changed["payload"]["history"][0]
    if mutation == "request_event":
        event["request"]["payload"]["event_key"] = "r179-unbound-request-event"
    elif mutation == "operation":
        event["decision"]["operation_sha256"] = "d" * 64
        event["transaction"]["operation_sha256"] = "d" * 64
        changed["decision"]["operation_sha256"] = "d" * 64
        changed["transaction"]["operation_sha256"] = "d" * 64
    elif mutation == "request_kind":
        wrong = _r179_history_request(
            fixture, initial, "supervision", "RESERVE_WAIT",
            event["request"]["payload"]["event_key"])
        event["request"] = wrong
    elif mutation == "result_hash":
        event["resulting_record_hash"] = "e" * 64
        event["transaction"]["event_record_hash"] = "e" * 64
        changed["transaction"]["event_record_hash"] = "e" * 64
    elif mutation == "cas_prestate":
        event["request"]["payload"]["expected_record_hash"] = "f" * 64
        operation = _r179_hash({
            "schema_version": "visual.local-history-operation.v1",
            "request": _r179_projection(event["request"])})
        for decision in (event["decision"], changed["decision"]):
            decision["operation_sha256"] = operation
        for transaction in (event["transaction"], changed["transaction"]):
            transaction["operation_sha256"] = operation
    elif mutation == "transaction_event":
        event["transaction"]["event_key"] = "r179-foreign-transaction-event"
        changed["transaction"]["event_key"] = "r179-foreign-transaction-event"
    else:
        changed["payload"]["initial_capture_claimed"] = False
        result = _r179_state_hash(changed)
        event["resulting_record_hash"] = result
        event["transaction"]["event_record_hash"] = result
        changed["transaction"]["event_record_hash"] = result
    _r179_evidence(tmp_path, seed, changed, "I1:" + mutation)
    with pytest.raises(ValueError, match="history|request|operation|event|state|CAS|claim|bootstrap|supervision|result"):
        _r179_accepted(changed)


@pytest.mark.parametrize("utc_mode", ["without_utc", "with_utc", "partial_utc"])
def test_r179_publication_hash_rejects(monkeypatch, tmp_path, utc_mode):
    fixture = _r179_fixture(monkeypatch)
    seed = copy.deepcopy(fixture["publication"])
    raw = fixture["legacy"]["data"]["publication"].to_payload()
    if utc_mode != "without_utc":
        seed["diagnostics"]["utc"]["published_at"] = raw["published_at"]
    if utc_mode == "with_utc":
        seed["diagnostics"]["utc"]["effective_deadline_at"] = raw["effective_deadline_at"]
    _r179_accepted(seed)
    changed = copy.deepcopy(seed)
    changed["payload"]["operation_hash"] = "d" * 64
    assert _r179_publication_hash(changed) != seed["payload"]["publication_hash"]
    _r179_evidence(tmp_path, seed, changed, "I2:" + utc_mode)
    with pytest.raises(ValueError, match="publication|content|hash"):
        _r179_accepted(changed)


@pytest.mark.parametrize("label", ["semantic_hash", "source_key"])
def test_r179_route_labels_recomputed(monkeypatch, tmp_path, label):
    seed = _r179_fixture(monkeypatch)["route"]
    _r179_accepted(seed)
    changed = copy.deepcopy(seed)
    changed["payload"][label] = "d" * 64
    assert changed["payload"][label] != seed["payload"][label]
    _r179_evidence(tmp_path, seed, changed, "I3:" + label)
    with pytest.raises(ValueError, match="semantic|source|hash|label"):
        _r179_accepted(changed)


@pytest.mark.parametrize("location", [
    "publication_verification", "publication_retry", "route_before", "route_after",
])
def test_r179_nested_original_rejects(monkeypatch, tmp_path, location):
    fixture = _r179_fixture(monkeypatch)
    seed = fixture["publication"] if location.startswith("publication") else fixture["route"]
    _r179_accepted(seed)
    changed = copy.deepcopy(seed)
    key = {"publication_verification": "verification_budget", "publication_retry": "retry_budget",
           "route_before": "before_verification_budget", "route_after": "after_verification_budget"}[location]
    nested = changed["payload"][key]
    alternate = copy.deepcopy(nested["original_time"])
    alternate["verification_reference"]["window_id"] += "-same-task-other-original"
    nested["original_time"] = alternate
    nested["decision"]["original_time_hash"] = _r179_hash(alternate)
    if key != "retry_budget":
        nested["payload"]["state"]["original_budget_reference"] = copy.deepcopy(
            alternate["verification_reference"])
        body = nested["payload"]
        body["content_hash"] = _r179_hash({
            "schema_version": nested["schema_version"], "task_id": body["task_id"],
            "state": body["state"], "revision": body["revision"]})
    _r179_accepted(nested)
    if location.startswith("publication"):
        changed["payload"]["publication_hash"] = _r179_publication_hash(changed)
    _r179_evidence(tmp_path, seed, changed, "I4:" + location)
    with pytest.raises(ValueError, match="original|reference|causal|budget"):
        _r179_accepted(changed)


def _r179_causal_seed(fixture, case):
    original = copy.deepcopy(fixture["original"])
    if case in {"app_hard", "lease_acquisition"}:
        if case == "app_hard":
            for name in ("task_reference", "verification_reference", "recovery_reference"):
                ref = original[name]
                for hard in ref["hard_deadlines"]:
                    hard["deadline_ns"] += 100
                ref["deadline_ns"] += 100
                ref["effective_upper"]["value_ns"] += 100
        else:
            acquisition = original["lease_identity"]["original_acquisition"]
            acquisition.update(lower_ns=100, upper_ns=110,
                               deadline_ns=100 + acquisition["budget_ns"])
    current = {**copy.deepcopy(fixture["current"]), "lower_ns": 90, "upper_ns": 120}
    decision = _b_decision(original, current)
    decision.update(disposition="VALID", reasons=[],
                    app_verdict={"status": "VALID", "reasons": []})
    observation = decision["lease_observation"]
    observation.update(status="VALID", reasons=[])
    observation["current"].update(lower_ns=120, upper_ns=120)
    if case == "lease_acquisition":
        observation["segment"].update(lower_ns=0, upper_ns=120,
                                     deadline_ns=observation["segment"]["budget_ns"])
    if case == "lease_segment":
        observation["segment"].update(event_id="r179-renewed-segment",
            lower_ns=100, upper_ns=110, deadline_ns=100 + observation["segment"]["budget_ns"])
        observation["generation"] = decision["lease_generation"] = decision["lease_row_revision"] = 2
    if case == "app_age":
        ref = copy.deepcopy(original["task_reference"])
        ref.update(window_id="r179-capture-age", kind="capture", kind_policy="AGE_CLOSED",
                   budget_semantics="AGE_CLOSED", budget_ns=1000,
                   event_id="r179-capture-event", parents=[original["task_reference"]["window_id"]],
                   age_constraints=[{
                       "event_id": "r179-capture-event", "source_id": "r179-capture-age",
                       "lower_ns": 100, "upper_ns": 110, "max_age_ns": 1000,
                       "upper_age_inclusive": True, "expiry_upper_ns": 1100}],
                   effective_upper={"value_ns": 1100, "inclusive": True})
        decision["app_references"].append(ref)
    return decision


@pytest.mark.parametrize("case", ["app_hard", "app_age", "lease_acquisition", "lease_segment"])
def test_r179_valid_causal_lower_bound(monkeypatch, tmp_path, case):
    from cloud_edge_robot_arm.vision.local_temporal import LocalAuthorityDecision

    fixture = _r179_fixture(monkeypatch)
    seed = _r179_causal_seed(fixture, case)
    assert LocalAuthorityDecision.from_payload(seed).to_payload() == seed
    changed = copy.deepcopy(seed)
    bracket = changed["app_current"] if case.startswith("app") else changed["lease_observation"]["current"]
    bracket.update(lower_ns=99, upper_ns=99)
    _r179_evidence(tmp_path, seed, changed, "I5:" + case)
    with pytest.raises(ValueError, match="causal|origin|lower|source|acquisition|segment"):
        LocalAuthorityDecision.from_payload(changed)


def test_r179_scope_null_rejected(monkeypatch, tmp_path):
    fixture = _r179_fixture(monkeypatch)
    seeds = fixture["cases"]
    for tag, seed in seeds.items():
        if "scope" not in _b_fields()[tag]:
            continue
        _r179_accepted(seed)
        changed = copy.deepcopy(seed)
        changed["payload"]["scope"] = None
        with pytest.raises(ValueError, match="scope"):
            _r179_accepted(changed)
    _r179_evidence(tmp_path, sorted(seeds), None, "M1:exact-required-scope")


def _r179_registries():
    from cloud_edge_robot_arm.simulation_runtime import operational_lease
    from cloud_edge_robot_arm.vision import operational_windows

    return [
        operational_windows._OWNERS, operational_windows._PENDING,
        operational_windows._HANDOFFS, operational_windows._SCOPES,
        operational_windows._TRANSITIONS, operational_lease._SESSIONS,
        operational_lease._VIEWS, operational_lease._PROPOSALS, operational_lease._ACKS,
    ]


@pytest.mark.parametrize("family", ["bootstrap", "supervision"])
def test_r179_history_replay_positive(monkeypatch, tmp_path, family):
    registries = _r179_registries()
    before = [dict(registry) for registry in registries]
    fixture = _r179_fixture(monkeypatch)
    initial, reserved, complete = _r179_completed(fixture, family)
    for record in (initial, reserved, complete):
        _r179_accepted(record)
    assert complete["payload"]["revision"] == 2
    events = complete["payload"]["history"]
    for index, event in enumerate(events):
        assert set(event) == {"request", "decision", "transaction", "resulting_record_hash"}
        assert event["transaction"]["event_revision"] == index + 1
        assert event["transaction"]["event_record_hash"] == event["resulting_record_hash"]
        if index:
            assert event["request"]["payload"]["expected_record_hash"] == events[index - 1]["resulting_record_hash"]
    assert events[0]["request"]["payload"]["expected_record_hash"] == _r179_state_hash(initial)
    assert events[-1]["resulting_record_hash"] == _r179_state_hash(complete)
    assert [dict(registry) for registry in registries] == before
    _r179_evidence(tmp_path, initial, complete, "I1:legal-two-phase-" + family)


@pytest.mark.parametrize("mutation", ["outer_diagnostics", "nested_diagnostics", "nested_renewal"])
def test_r179_semantic_projection_invariant(monkeypatch, tmp_path, mutation):
    fixture = _r179_fixture(monkeypatch)
    seed = fixture["route"]["payload"]["input"]
    decoded = _r179_accepted(seed)
    changed = copy.deepcopy(seed)
    nested = changed["payload"]["publication"]
    if mutation == "outer_diagnostics":
        changed["diagnostics"]["monotonic"] = 123.0
    elif mutation == "nested_diagnostics":
        nested["payload"]["verification_budget"]["diagnostics"]["monotonic"] = 123.0
    else:
        pool = nested["payload"]["verification_budget"]
        pool["decision"] = _b_decision(pool["original_time"], fixture["current"], 2)
        pool["transaction"] = _b_transaction(pool["decision"])
    changed_domain = _r179_accepted(changed)
    assert _r179_route_semantic(seed) == _r179_route_semantic(changed)
    assert decoded.semantic_hash() == changed_domain.semantic_hash()
    assert decoded.source_key() == changed_domain.source_key()
    assert _r179_publication_hash(seed["payload"]["publication"]) == _r179_publication_hash(nested)
    assert _r179_hash(seed) != _r179_hash(changed)
    assert decoded.digest() != changed_domain.digest()
    substantive = copy.deepcopy(changed)
    substantive["payload"]["publication"]["payload"]["operation_hash"] = "d" * 64
    substantive["payload"]["publication"]["payload"]["publication_hash"] = _r179_publication_hash(
        substantive["payload"]["publication"])
    substantive_domain = _r179_accepted(substantive)
    assert substantive_domain.semantic_hash() != changed_domain.semantic_hash()
    _r179_evidence(tmp_path, seed, changed, "I3:permitted-" + mutation)


def test_r179_causal_overlap_positive(monkeypatch, tmp_path):
    from cloud_edge_robot_arm.vision.local_temporal import LocalAuthorityDecision

    seed = _r179_causal_seed(_r179_fixture(monkeypatch), "app_age")
    assert seed["app_current"]["lower_ns"] < seed["app_references"][-1]["age_constraints"][0]["upper_ns"]
    assert LocalAuthorityDecision.from_payload(seed).to_payload() == seed
    _r179_evidence(tmp_path, seed, None, "I5:overlap-allowed")


def test_r179_cross_domain_causality_rejected(monkeypatch, tmp_path):
    from cloud_edge_robot_arm.vision.local_temporal import LocalAuthorityDecision

    seed = _r179_causal_seed(_r179_fixture(monkeypatch), "app_age")
    assert LocalAuthorityDecision.from_payload(seed).to_payload() == seed
    changed = copy.deepcopy(seed)
    changed["app_references"][-1]["domain"]["startup_nonce"] = "r179-foreign-same-numeric-bracket"
    with pytest.raises(ValueError, match="domain|same original"):
        LocalAuthorityDecision.from_payload(changed)
    _r179_evidence(tmp_path, seed, changed, "I5:foreign-domain")


@pytest.mark.parametrize("variant", ["local", "legacy"])
def test_r179_publication_history_getters(monkeypatch, tmp_path, variant):
    from cloud_edge_robot_arm.contracts.models import RecoveryBudget
    from cloud_edge_robot_arm.edge.recovery.lifecycle import (
        LocalRetryBudgetRecord, LocalVerificationBudgetRecord, VerificationBudgetRecord,
    )

    registries = _r179_registries()
    before = [dict(registry) for registry in registries]
    fixture = _r179_fixture(monkeypatch)
    seed = copy.deepcopy(fixture["publication"])
    if variant == "legacy":
        source = fixture["legacy"]["data"]["publication"].to_payload()
        seed["payload"]["verification_budget"] = copy.deepcopy(source["verification_budget"])
        seed["payload"]["retry_budget"] = copy.deepcopy(source["retry_budget"])
        seed["payload"]["publication_hash"] = _r179_publication_hash(seed)
    domain = _r179_accepted(seed)
    verification = domain.verification_budget_history
    retry = domain.retry_budget_history
    if variant == "local":
        assert type(verification) is LocalVerificationBudgetRecord
        assert type(retry) is LocalRetryBudgetRecord
        assert verification.state.original_budget_reference == seed["original_time"]["verification_reference"]
        assert retry.original_recovery_reference == seed["original_time"]["recovery_reference"]
        for name, value in seed["payload"]["retry_budget"]["payload"].items():
            assert getattr(retry, name) == value, name
        with pytest.raises(ValueError, match="history"):
            _ = domain.verification_budget
        with pytest.raises(ValueError, match="history"):
            _ = domain.retry_budget
        exported = retry.to_payload()
        exported["payload"]["event_retry_counts"]["caller"] = 1
        assert retry.to_payload() == seed["payload"]["retry_budget"]
        derived = retry.original_recovery_reference
        derived["window_id"] = "caller"
        assert retry.original_recovery_reference == seed["original_time"]["recovery_reference"]
    else:
        assert type(verification) is VerificationBudgetRecord
        assert type(retry) is RecoveryBudget
        assert domain.verification_budget.to_payload() == verification.to_payload()
        assert domain.retry_budget.model_dump(mode="json") == retry.model_dump(mode="json")
    for key in ("verification_budget", "retry_budget"):
        changed = copy.deepcopy(seed)
        changed["payload"][key]["schema_version"] = "unsupported.r179.v1"
        changed["payload"]["publication_hash"] = _r179_publication_hash(changed)
        with pytest.raises(ValueError, match="tag|schema|source|publication|budget|field|semantic"):
            _r179_accepted(changed)
    assert [dict(registry) for registry in registries] == before
    _r179_evidence(tmp_path, seed, None, "M2:direct-history-getters-" + variant)


def test_r179_local_publication_positive(monkeypatch, tmp_path):
    registries = _r179_registries()
    before = [dict(registry) for registry in registries]
    fixture = _r179_fixture(monkeypatch)
    seed = fixture["publication"]
    raw = fixture["legacy"]["data"]["publication"].to_payload()
    for utc in ({}, {"published_at": raw["published_at"],
                    "effective_deadline_at": raw["effective_deadline_at"]}):
        candidate = copy.deepcopy(seed)
        candidate["diagnostics"]["utc"] = utc
        _r179_accepted(candidate)
        assert candidate["payload"]["publication_hash"] == _r179_publication_hash(candidate)
        assert candidate["payload"]["verification_budget"]["original_time"] == candidate["original_time"]
        assert candidate["payload"]["retry_budget"]["original_time"] == candidate["original_time"]
    assert [dict(registry) for registry in registries] == before
    _r179_evidence(tmp_path, seed, None, "I2/I4:local-publication-positive")


# R158 T2: private two-authority publication; all earlier bytes stay frozen.
def _b_t2_api():
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
    from cloud_edge_robot_arm.vision.operational_windows import OperationalWindowOwner
    from cloud_edge_robot_arm.vision.worker_runtime import VisualWorkerRuntime

    annotation = inspect.signature(SimulationWorker).parameters["operational_time_mode"].annotation
    assert "LOCAL_TEMPORAL_PUBLICATION_V1" in str(annotation), (
        "R158 T2 planned missing LOCAL_TEMPORAL_PUBLICATION_V1"
    )
    required = (
        (OperationalWindowOwner, ("_check_app_live", "_check_local_locked")),
        (SQLiteSimulationJobRepository, ("_local_read_scope", "read_local_publication",
                                        "reconcile_local_publications")),
        (VisualWorkerRuntime, ("_local_publication_scope",)),
    )
    for cls, names in required:
        for name in names:
            assert callable(getattr(cls, name, None)), f"R158 T2 planned missing {cls.__name__}.{name}"


@contextmanager
def _b_t2_attempt(request):
    import sys

    previous_profile = sys.getprofile()
    value = {
        "schema_version": "bigsmall.r158-t2-resource.v1",
        "command_id": os.environ.get("BIGSMALL_R158_COMMAND"),
        "nodeid": request.node.nodeid, "pid": os.getpid(),
        "scenario": request.node.name, "entered_contract_guard": True,
        "entered_behavior": False, "allocation_attempts": 0, "resources": [],
        "worker_lifecycles": [],
        "cleanup_errors": [], "observations": {"assertions_completed": False,
                                              "observers_restored": False, "scenarios": []},
        "unobserved": {"OS_handles": None, "external_models": None, "GPU_native": None,
                       "network_calls": None},
    }
    try:
        yield value
        value["observations"]["assertions_completed"] = True
    finally:
        error_type, error, _ = sys.exc_info()
        value["observations"]["exit_exception"] = None if error_type is None else {
            "type": error_type.__name__, "message": str(error),
        }
        value["allocation_attempts"] = len(value["resources"])
        if not value["entered_behavior"]:
            value["observations"]["observers_restored"] = sys.getprofile() is previous_profile
        sink = os.environ.get("BIGSMALL_R158_T2_RESOURCE_DIR")
        assert sink, "T2 requires the exact ROOT-approved per-command resource sink"
        directory = Path(sink)
        assert directory.is_dir() and not directory.is_symlink()
        name = hashlib.sha256(request.node.nodeid.encode()).hexdigest() + ".json"
        with (directory / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")


@contextmanager
def _b_t2_observe(monkeypatch, value):
    """Observe real constructors, connections and issuer clocks; no permission mocks."""
    import sys
    import time
    from types import SimpleNamespace
    from cloud_edge_robot_arm.research.operational_time_v1 import _open_clock_for_test
    from cloud_edge_robot_arm.repositories.event_autonomy import (
        InMemoryEventAutonomyRepository, SQLiteEventAutonomyRepository,
    )
    from cloud_edge_robot_arm.simulation_runtime import operational_lease as lease_module
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker
    from cloud_edge_robot_arm.vision import operational_windows

    guard = threading.RLock()
    objects, methods, clocks, release_events, worker_refs, session_refs = {}, {}, [], [], [], []
    session_owners = {}
    sample_counts = {"runtime_samples": 0}
    value["observations"]["observer_sampling"] = sample_counts
    sequence = 0
    poll_context = threading.local()
    real_poll = SimulationWorker.poll_once
    poll_code = real_poll.__code__
    fault = {"operation_id": None, "database": None, "phase": None, "fired": False}
    previous_profile, previous_thread_profile = sys.getprofile(), threading.getprofile()

    def tick():
        nonlocal sequence
        with guard:
            sequence += 1
            return sequence

    def add(obj, kind, **details):
        with guard:
            key = id(obj)
            if key in objects:
                return objects[key][1]
            record = {
                "resource_id": key, "kind": kind, "class_module": type(obj).__module__,
                "class_name": type(obj).__qualname__, "pid": os.getpid(),
                "creating_thread": threading.get_ident(), "creating_native_thread": threading.get_native_id(),
                "initialization_attempted": True, "initialized": False, "initialization_error": None,
                "close_attempts": [], "cleanup_observed": None, **details,
            }
            if kind == "worker":
                record.update(poll_ids=[], initial_active_job_id=None, final_active_job_id=None,
                              session_observed=None, heartbeat_observed=None, cleanup_basis=None,
                              session_resource_ids=[], broker_resource_ids=[], heartbeat_resource_ids=[],
                              broker_peak_alive=None, heartbeat_peak_alive=None)
            objects[key] = (obj, record)
            value["resources"].append(record)
            if kind == "worker":
                worker_refs.append(obj)
            return record

    def close_wrapper(original, kind):
        def close(obj, *args, **kwargs):
            record = add(obj, kind)
            call = {"thread": threading.get_ident(), "native_thread": threading.get_native_id(),
                    "returned": False, "error": None}
            record["close_attempts"].append(call)
            try:
                result = original(obj, *args, **kwargs)
            except BaseException as error:
                call["error"] = {"type": type(error).__name__, "message": str(error)}
                raise
            else:
                call["returned"] = True
                record["cleanup_observed"] = True
                return result
        return close

    def init_wrapper(original, kind):
        def initialize(obj, *args, **kwargs):
            record = add(obj, kind)
            if kind == "lease_session":
                record["constructor_outcome"] = "ENTERED"
            try:
                result = original(obj, *args, **kwargs)
            except BaseException as error:
                if kind == "lease_session":
                    record["constructor_outcome"] = "RAISED"
                record["initialization_error"] = {"type": type(error).__name__, "message": str(error)}
                if kind == "worker":
                    record["initial_active_job_id"] = getattr(obj, "active_job_id", None)
                    record["initial_state_observation"] = "constructor_exception"
                    sample_runtime(obj)
                raise
            else:
                record["initialized"] = True
                if kind == "lease_session":
                    record["constructor_outcome"] = "RETURNED"
                if kind == "worker":
                    record["initial_active_job_id"] = getattr(obj, "active_job_id", None)
                    record["initial_state_observation"] = "constructor_return"
                    sample_runtime(obj)
                return result
        return initialize

    def sample_runtime(worker, session=None):
        with guard:
            sample_runtime_locked(worker, session)

    def sample_runtime_locked(worker, session=None):
        sample_counts["runtime_samples"] += 1
        record = objects[id(worker)][1]
        current = getattr(worker, "_operational_lease_session", None)
        for candidate in (session, current):
            if candidate is None:
                continue
            owner = getattr(candidate, "worker", worker)
            assert owner is worker, "session actual worker identity changed"
            known = session_owners.get(id(candidate))
            assert known is None or known is worker, "session observer owner identity changed"
            if known is None:
                session_owners[id(candidate)] = worker
                session_refs.append(candidate)
            session_record = add(candidate, "lease_session")
            if id(candidate) not in record["session_resource_ids"]:
                record["session_resource_ids"].append(id(candidate))
            session_record["worker_resource_id"] = id(worker)
        sessions = [objects[item][0] for item in record["session_resource_ids"]]
        field_observed = hasattr(worker, "_operational_lease_session")
        if field_observed or sessions:
            record["session_observed"] = bool(sessions)
        for attribute, kind, key, peak_key in (
            ("_broker", "broker_thread", "broker_resource_ids", "broker_peak_alive"),
            ("_heartbeat_thread", "heartbeat_thread", "heartbeat_resource_ids", "heartbeat_peak_alive"),
        ):
            for owned_session in sessions:
                thread = getattr(owned_session, attribute, None)
                if thread is not None:
                    thread_record = add(thread, kind)
                    thread_record["initialized"] = thread.ident is not None
                    thread_record["worker_resource_id"] = id(worker)
                    thread_record["session_resource_id"] = id(owned_session)
                    if id(thread) not in record[key]:
                        record[key].append(id(thread))
            if (record[key] or (field_observed and not sessions)
                    or any(hasattr(item, attribute) for item in sessions)):
                alive = sum(int(objects[item][0].is_alive()) for item in record[key])
                record[peak_key] = max(record[peak_key] or 0, alive)
        if field_observed or any(hasattr(item, "_heartbeat_thread") for item in sessions):
            record["heartbeat_observed"] = bool(record["heartbeat_resource_ids"])

    def observe_session(session, worker=None):
        if session is None:
            return
        with guard:
            known = session_owners.get(id(session))
            owner = getattr(session, "worker", worker)
            if owner is None:
                owner = known
            if known is not None:
                assert owner is known, "session lifecycle actual owner changed"
            registered = objects.get(id(owner))
            if registered is not None and registered[0] is owner and registered[1]["kind"] == "worker":
                sample_runtime_locked(owner, session)

    def poll_once(worker, *args, **kwargs):
        record = add(worker, "worker")
        with guard:
            call = {"poll_id": len(value["worker_lifecycles"]) + 1,
                    "worker_resource_id": id(worker), "attempted": True, "entered": False,
                    "returned_normally": False, "return_value": None, "exception": None,
                    "start_sequence": tick(), "entry_sequence": None, "end_sequence": None,
                    "thread_id": None, "native_thread_id": None}
            value["worker_lifecycles"].append(call)
            record["poll_ids"].append(call["poll_id"])
        previous_call = getattr(poll_context, "call", None)
        poll_context.call = call
        try:
            result = real_poll(worker, *args, **kwargs)
        except BaseException as error:
            call["exception"] = {"type": type(error).__name__, "message": str(error)}
            raise
        else:
            call["returned_normally"] = True
            call["return_value"] = result
            return result
        finally:
            sample_runtime(worker)
            call["end_sequence"] = tick()
            poll_context.call = previous_call

    def after_commit(conn, entrance):
        if fault["fired"] or fault["operation_id"] is None:
            return
        record = objects[id(conn)][1]
        if record["database"] != fault["database"]:
            return
        table = ("visual_local_publications_v1" if fault["database"] == "event"
                 else "simulation_local_publications_v1")
        rows = [dict(row) for row in conn.execute(
            f"SELECT * FROM {table} WHERE operation_id=?", (fault["operation_id"],)
        )]
        if not any(row["phase"] == fault["phase"] for row in rows):
            return
        assert conn.in_transaction is False
        fault["fired"] = True
        evidence = {
            "kind": "TRUE_COMMIT_THEN_SAME_CONNECTION_CLOSE", "entrance": entrance,
            "resource_id": id(conn), "database_path": record["path"],
            "operation_id": fault["operation_id"], "phase": fault["phase"], "durable_rows": rows,
            "thread": threading.get_ident(), "native_thread": threading.get_native_id(),
            "in_transaction_after_commit": conn.in_transaction,
        }
        value["observations"]["scenarios"].append(evidence)
        conn.close()
        try:
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError as error:
            evidence["actual_closed_connection_error"] = {
                "type": type(error).__name__, "message": str(error),
            }
            raise
        raise AssertionError("closed SQLite connection unexpectedly executed SQL")

    class _b_t2_Connection(sqlite3.Connection):
        def __init__(self, database, *args, **kwargs):
            path = str(Path(database).resolve())
            record = add(self, "sqlite_connection", path=path,
                         database="event" if Path(path).name == "events.db" else "job")
            try:
                super().__init__(database, *args, **kwargs)
            except BaseException as error:
                record["initialization_error"] = {"type": type(error).__name__, "message": str(error)}
                raise
            record["initialized"] = True

        def execute(self, sql, parameters=(), /):
            result = super().execute(sql, parameters)
            if sql.strip().rstrip(";").upper() in {"COMMIT", "END", "END TRANSACTION"}:
                after_commit(self, "execute")
            return result

        def commit(self):
            active = self.in_transaction
            result = super().commit()
            if active:
                after_commit(self, "commit")
            return result

        def __exit__(self, kind, error, traceback):
            active = self.in_transaction
            result = super().__exit__(kind, error, traceback)
            if kind is None and active:
                after_commit(self, "__exit__")
            return result

        def close(self):
            return close_wrapper(sqlite3.Connection.close, "sqlite_connection")(self)

    actual_connect = sqlite3.connect

    def connect(*args, **kwargs):
        assert "factory" not in kwargs, "T2 observer requires the actual default SQLite factory seam"
        return actual_connect(*args, factory=_b_t2_Connection, **kwargs)

    context = monkeypatch.context()
    patcher = context.__enter__()

    def patch(cls, name, replacement):
        key = (cls, name)
        if key not in methods:
            methods[key] = getattr(cls, name)
            patcher.setattr(cls, name, replacement)

    def clock_factory(destination):
        raw = _Counter()
        marker = SimpleNamespace()
        record = add(marker, "OC1_clock", domain_kind=destination)
        try:
            clock = _open_clock_for_test(raw)
        except BaseException as error:
            record["initialization_error"] = {"type": type(error).__name__, "message": str(error)}
            raise
        del objects[id(marker)]
        objects[id(clock)] = (clock, record)
        record.update(resource_id=id(clock), class_module=type(clock).__module__,
                      class_name=type(clock).__qualname__, initialized=True,
                      issuer_thread=threading.get_ident(), issuer_native_thread=threading.get_native_id())
        clocks.append((clock, raw, destination))
        if (type(clock), "close") not in methods:
            patch(type(clock), "close", close_wrapper(type(clock).close, "OC1_clock"))
        return clock

    session_code = lease_module.OperationalLeaseSession.__init__.__code__
    thread_start_code = threading.Thread.start.__code__
    heartbeat_install_code = lease_module._install_heartbeat_thread.__code__
    session_close_code = lease_module._close_worker_lease_session.__code__

    def profile(frame, event, arg):
        code = frame.f_code
        if code is poll_code and event in ("call", "return"):
            call = getattr(poll_context, "call", None)
            if call is not None and frame.f_locals.get("self") is objects[call["worker_resource_id"]][0]:
                if event == "call":
                    call["entered"] = True
                    call["entry_sequence"] = tick()
                    call["thread_id"] = threading.get_ident()
                    call["native_thread_id"] = threading.get_native_id()
                sample_runtime(frame.f_locals["self"])
        elif code is session_code and event in ("call", "return"):
            session = frame.f_locals["self"]
            observe_session(session, frame.f_locals.get("worker"))
        elif code is thread_start_code and event in ("call", "return"):
            thread = frame.f_locals.get("self")
            for session in tuple(session_refs):
                if (thread is not None and
                        (thread is getattr(session, "_broker", None)
                         or thread is getattr(session, "_heartbeat_thread", None))):
                    observe_session(session)
                    break
        elif code is heartbeat_install_code and event == "return":
            observe_session(frame.f_locals.get("session"))
        elif code is session_close_code and event in ("call", "return"):
            observe_session(frame.f_locals.get("session"))
        callback = state.wait_observer
        if callback is not None:
            callback(frame, event, arg)

    state = SimpleNamespace(value=value, fault=fault, clocks=clocks, objects=objects,
                            release_events=release_events, workers=worker_refs, sessions=session_refs,
                            wait_observer=None, add=add)
    try:
        patcher.setattr(sqlite3, "connect", connect)
        for cls, kind in (
            (InMemoryEventAutonomyRepository, "memory_repository"),
            (SQLiteEventAutonomyRepository, "event_repository"),
            (SQLiteSimulationJobRepository, "job_repository"),
            (SimulationWorker, "worker"),
            (lease_module.OperationalLeaseSession, "lease_session"),
        ):
            patch(cls, "__init__", init_wrapper(cls.__init__, kind))
        patch(SimulationWorker, "poll_once", poll_once)
        for cls, kind in ((InMemoryEventAutonomyRepository, "memory_repository"),
                          (SQLiteEventAutonomyRepository, "event_repository")):
            patch(cls, "close", close_wrapper(cls.close, kind))
        patcher.setattr(lease_module, "open_operational_clock", lambda: clock_factory("D_lease"))
        patcher.setattr(operational_windows, "open_operational_clock", lambda: clock_factory("D_app"))
        sys.setprofile(profile)
        threading.setprofile(profile)
        yield state
    finally:
        state.wait_observer = None
        for released in release_events:
            released.set()
        for session in session_refs:
            try:
                if not getattr(session, "_closed", False):
                    lease_module._close_worker_lease_session(session, reason="T2-finally")
                record = objects[id(session)][1]
                broker = getattr(session, "_broker", None)
                record["broker_alive"] = None if broker is None else broker.is_alive()
                record["cleanup_observed"] = (
                    getattr(session, "_closed", False) is True and broker is not None and not broker.is_alive()
                )
            except BaseException as error:
                value["cleanup_errors"].append({"resource_id": id(session),
                    "type": type(error).__name__, "message": str(error)})
        for clock, _, _ in clocks:
            if (not clock._closed
                    and objects[id(clock)][1]["issuer_thread"] == threading.get_ident()):
                try:
                    clock.close()
                except BaseException as error:
                    value["cleanup_errors"].append({"resource_id": id(clock),
                        "type": type(error).__name__, "message": str(error)})
        for obj, record in list(objects.values()):
            try:
                kind = record["kind"]
                if kind in {"memory_repository", "event_repository", "sqlite_connection"}:
                    if record["initialized"] and record["cleanup_observed"] is not True:
                        obj.close()
                elif kind == "OC1_clock":
                    record["cleanup_observed"] = obj._closed is True
                elif kind == "job_repository":
                    record["TLS_connection"] = getattr(obj._transactions, "connection", None) is not None
                    owned = [row for _, row in objects.values()
                             if row["kind"] == "sqlite_connection"
                             and row.get("path") == str(obj.database_path.resolve())]
                    record["cleanup_observed"] = not record["TLS_connection"] and all(
                        row["cleanup_observed"] is True for row in owned)
                elif kind == "worker":
                    sample_runtime(obj)
                    session = getattr(obj, "_operational_lease_session", None)
                    heartbeat = None if session is None else getattr(session, "_heartbeat_thread", None)
                    record["heartbeat_alive"] = None if heartbeat is None else heartbeat.is_alive()
                    record["final_active_job_id"] = getattr(obj, "active_job_id", None)
                    calls = [call for call in value["worker_lifecycles"]
                             if call["worker_resource_id"] == id(obj)]
                    if not calls:
                        record["cleanup_basis"] = "never_polled_no_owned_runtime"
                        record["cleanup_observed"] = (
                            record["initial_active_job_id"] == ""
                            and record["final_active_job_id"] == ""
                            and record["session_observed"] is False
                            and record["heartbeat_observed"] is False
                            and session is None and heartbeat is None
                            and not record["close_attempts"])
                    else:
                        record["cleanup_basis"] = "poll_finished_runtime_released"
                        sessions = [objects[item][0] for item in record["session_resource_ids"]]
                        threads = [objects[item][0] for item in
                                   record["broker_resource_ids"] + record["heartbeat_resource_ids"]]
                        record["cleanup_observed"] = (
                            all(call["end_sequence"] is not None for call in calls)
                            and record["final_active_job_id"] == ""
                            and record["session_observed"] is not None
                            and record["heartbeat_observed"] is not None
                            and all(getattr(item, "_closed", False) is True for item in sessions)
                            and all(not item.is_alive() for item in threads)
                            and (session is None or getattr(session, "_closed", False) is True)
                            and (heartbeat is None or not heartbeat.is_alive()))
                elif kind in {"helper_thread", "broker_thread", "heartbeat_thread"}:
                    if obj.ident is not None and obj is not threading.current_thread():
                        obj.join(timeout=2)
                    record["thread_ident"] = obj.ident
                    record["native_thread_id"] = obj.native_id
                    record["alive_after_join"] = obj.is_alive()
                    record["cleanup_observed"] = not obj.is_alive()
            except BaseException as error:
                value["cleanup_errors"].append({"resource_id": record["resource_id"],
                    "type": type(error).__name__, "message": str(error)})
        sys.setprofile(previous_profile)
        threading.setprofile(previous_thread_profile)
        context.__exit__(None, None, None)
        restored = all(getattr(cls, name) is original for (cls, name), original in methods.items())
        value["observations"]["observers_restored"] = (
            restored and sys.getprofile() is previous_profile
            and threading.getprofile() is previous_thread_profile and sqlite3.connect is actual_connect)
        value["observations"]["method_restoration"] = restored
        value["allocation_attempts"] = len(value["resources"])
        objects.clear()


def _b_t2_plain(value):
    from collections.abc import Mapping
    from dataclasses import fields

    codec = getattr(value, "to_payload", None)
    if callable(codec):
        return _b_t2_plain(codec())
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _b_t2_plain(model_dump(mode="json"))
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _b_t2_plain(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _b_t2_plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_b_t2_plain(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError(f"T2 semantic snapshot has unsupported {type(value).__name__}")


def _b_t2_snapshot(events, reads):
    def rows(connection):
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        return {name: sorted(
            [dict(row) for row in connection.execute('SELECT * FROM "' + name.replace('"', '""') + '"')],
            key=lambda row: json.dumps(row, sort_keys=True, allow_nan=False),
        ) for name in tables}

    event_rows = (rows(reads["event"]) if "event" in reads else {
        name: _b_t2_plain(item) for name, item in vars(events).items()
        if isinstance(item, dict) and name != "_visual_supervision_verified_bytes"
    })
    return {"event": event_rows, "job": rows(reads["job"])}


def _b_t2_digest(value):
    return hashlib.sha256(json.dumps(
        _b_t2_plain(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


def _b_t2_bootstrap_request(record, kind, key, *, claim=None, observation=None, draft=None):
    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import VisualBootstrapTransitionInput

    raw = record.to_payload()
    assert raw["schema_version"] == "visual.bootstrap.record.local.v1"
    definition = record.definition
    payload = {
        "scope": "BOOTSTRAP_SOURCE_ONLY", "bootstrap_id": definition.bootstrap_id,
        "definition_hash": _b_t2_digest(raw["payload"]["definition"]),
        "expected_record_hash": _r179_state_hash(raw), "kind": kind, "event_key": key,
        "robot_state": RobotState(connected=True).model_dump(mode="json"),
        "claim_id": claim, "observation": _b_t2_plain(observation),
        "draft": _b_t2_plain(draft),
    }
    request = {
        "schema_version": "visual.bootstrap.transition.local.v1", "payload": payload,
        "original_time": copy.deepcopy(raw["original_time"]), "decision": None, "transaction": None,
        "diagnostics": {"utc": {}, "monotonic": None},
    }
    return VisualBootstrapTransitionInput.from_payload(request)


def _b_t2_transition(runtime, events, request):
    operation_id = request.to_payload()["payload"]["event_key"]
    with runtime._local_publication_scope(
        operation_id=operation_id, operation_sha256=_b_t2_digest(request)
    ):
        result = events.transition_visual_bootstrap_if_current(request=request)
    assert result is not None
    assert result.record.to_payload()["schema_version"] == "visual.bootstrap.record.local.v1"
    return result.record


def _b_t2_capture_and_unusable_plan(runtime, events, key):
    from datetime import UTC, datetime
    from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
    from cloud_edge_robot_arm.contracts import RobotState
    from tests.test_visual_bootstrap import frame

    assert runtime.source.event_repository is events
    record = runtime.bootstrap
    original = copy.deepcopy(record.to_payload()["original_time"])
    assert record.to_payload()["schema_version"] == "visual.bootstrap.record.local.v1"
    robot_state = RobotState(connected=True)
    claim = runtime.reserve_capture(robot_state, initial=True)
    reserved = runtime.bootstrap
    assert reserved.to_payload()["schema_version"] == "visual.bootstrap.record.local.v1"
    assert reserved.to_payload()["payload"]["pending"]["claim_id"] == claim
    assert reserved.to_payload()["original_time"] == original
    # CPU model diagnostic only: this UTC input is never a local lease/origin/deadline.
    capture_timestamp = datetime.now(UTC)
    observation = frame((None, None, capture_timestamp), frame_id=key + ":frame", at=capture_timestamp)
    observation_payload = observation.model_dump(mode="json")
    observation_payload.update(episode_id=record.definition.episode_id, checksum_sha256="")
    observation = type(observation).model_validate(observation_payload)
    runtime.complete_capture(claim, observation, robot_state)
    captured = runtime.bootstrap
    assert captured.to_payload()["original_time"] == original
    claim = runtime.reserve_plan(robot_state)
    planned = runtime.bootstrap
    assert planned.to_payload()["payload"]["pending"]["claim_id"] == claim
    assert planned.to_payload()["original_time"] == original
    draft = PlannerDraft(
        raw_text="R158 T2 CPU fixture: request another observation",
        parsed_json={"_sentinel": "REQUEST_MORE_OBSERVATION"},
        observation_evidence={**observation.evidence(),
                              "model_snapshot_hash": record.definition.model_snapshot_hash,
                              "role_bundle_hash": record.definition.role_bundle_hash},
    )
    runtime.complete_plan(claim, draft, robot_state)
    finished = runtime.bootstrap
    assert finished.to_payload()["schema_version"] == "visual.bootstrap.record.local.v1"
    assert finished.to_payload()["payload"]["planning_source_usable"] is False
    assert finished.to_payload()["payload"]["state"]["original_budget_reference"] == (
        original["verification_reference"])
    assert finished.to_payload()["original_time"] == original
    return finished


def _b_t2_exercise(monkeypatch, directory, backend, observed, callback):
    from cloud_edge_robot_arm.repositories.event_autonomy import InMemoryEventAutonomyRepository
    from cloud_edge_robot_arm.simulation_runtime import operational_lease
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
    from tests.test_visual_worker_factory import software_factory

    directory.mkdir(parents=True, exist_ok=False)
    outcomes, errors, reads = [], [], {}
    received = None
    events = None

    def episode(worker, repo, job, source_root):
        runtime = received[0][3].worker_runtime
        session = worker._operational_lease_session
        assert type(repo) is SQLiteSimulationJobRepository
        assert runtime.source.event_repository is events
        assert runtime._operational_owner is not None and session is not None
        for thread, kind in ((session._broker, "broker_thread"),
                             (getattr(worker, "_heartbeat_thread", None), "heartbeat_thread")):
            if thread is not None:
                record = observed.add(thread, kind)
                record["initialized"] = True
        try:
            outcomes.append(callback(runtime, session, worker, repo, job, events, reads, observed))
        except BaseException as error:
            errors.append(error)
            raise

    with monkeypatch.context() as scoped:
        data = software_factory(scoped, directory, during_episode=episode)
        repo, job, worker, calls, received, _, original_events = data
        events = original_events
        if backend == "memory":
            original_events.close()
            events = InMemoryEventAutonomyRepository()
            worker.visual_event_repository = events
        worker.operational_time_mode = "LOCAL_TEMPORAL_PUBLICATION_V1"
        try:
            # All independent connections exist BEFORE any tested job view/event lock.
            reads["job"] = sqlite3.connect(repo.database_path)
            reads["job"].row_factory = sqlite3.Row
            if backend == "sqlite":
                reads["event"] = sqlite3.connect(events.path)
                reads["event"].row_factory = sqlite3.Row
            assert worker.poll_once()
            if errors:
                raise errors[0]
            assert len(outcomes) == 1, repo.get_job(job.job_id).error_message
            assert calls.count("episode") == 1
            return outcomes[0]
        finally:
            observed.wait_observer = None
            for event in observed.release_events:
                event.set()
            session = getattr(worker, "_operational_lease_session", None)
            if session is not None and not session._closed:
                operational_lease._close_worker_lease_session(session, reason="T2-exercise-finally")
            events.close()
            for connection in reads.values():
                connection.close()


def _b_t2_wait_for_event_lock(runtime, session, repo, events, observed, counter_kind, *, clock_start):
    import queue
    import sys
    import time
    from cloud_edge_robot_arm.simulation_runtime.operational_lease import LockedLeaseView, _view_record

    event_lock = events._lock if hasattr(events, "_lock") else events._write_lock
    entered, held, emergency = queue.Queue(), threading.Event(), threading.Event()
    observed.release_events.append(emergency)
    main_ident, main_native = threading.get_ident(), threading.get_native_id()
    function = type(runtime)._local_publication_scope
    coordinator = function.__wrapped__.__code__
    history, holder_errors = [], []
    state = {"returned": False, "callsite": None, "offset": None, "view": None}
    original = runtime.bootstrap.to_payload()["original_time"]
    if counter_kind == "D_app":
        deadline = original["task_reference"]["deadline_ns"]
    else:
        deadline = session.ttl_ns

    def observer(frame, event, arg):
        if threading.get_ident() != main_ident:
            return
        if getattr(arg, "__self__", None) is not event_lock or getattr(arg, "__name__", None) != "acquire":
            return
        if event == "c_call":
            assert frame.f_code is coordinator
            view = frame.f_locals["view"]
            assert type(view) is LockedLeaseView
            binding = _view_record(view)
            assert binding.repository is repo and binding.session is session
            assert binding.connection.in_transaction is True
            assert binding.thread_id == main_ident and binding.native_thread_id == main_native
            assert event_lock.locked() and held.is_set()
            state.update(callsite=frame, offset=frame.f_lasti, view=view)
            packet = {
                "event": "real_lock_acquire_c_call", "builtin_self_id": id(arg.__self__),
                "lock_id": id(event_lock), "job_view_id": id(view), "connection_id": id(binding.connection),
                "connection_in_transaction": binding.connection.in_transaction,
                "main_ident": main_ident, "main_native": main_native, "call_offset": frame.f_lasti,
                "coordinator_code": frame.f_code.co_qualname,
            }
            history.append(packet)
            entered.put(packet)
        elif event == "c_return":
            state["returned"] = True
            history.append({"event": "real_lock_acquire_c_return", "main_ident": main_ident})

    def holder():
        try:
            with event_lock:
                held.set()
                history.append({"event": "holder_owns_real_lock", "ident": threading.get_ident(),
                                "native": threading.get_native_id(), "lock_id": id(event_lock)})
                entered.get(timeout=4)
                limit = time.monotonic() + 4
                while time.monotonic() < limit and not emergency.is_set():
                    top = sys._current_frames().get(main_ident)
                    if (top is state["callsite"] and top.f_code is coordinator
                            and top.f_lasti == state["offset"] and not state["returned"]):
                        assert event_lock.locked()
                        history.append({"event": "main_returned_from_profile_inside_real_acquire",
                                        "frame_id": id(top), "offset": top.f_lasti,
                                        "no_c_return_yet": True, "holder_still_owns_lock": True})
                        matching = [item for item in observed.clocks[clock_start:] if item[2] == counter_kind]
                        assert len(matching) == 1
                        clock, raw, _ = matching[0]
                        assert clock._closed is False
                        before = raw.now
                        raw.now = max(raw.now, deadline)
                        history.append({"event": "advance_original_counter", "kind": counter_kind,
                                        "before": before, "after": raw.now,
                                        "identity": asdict(raw.current_identity)})
                        break
                    time.sleep(0.001)
                else:
                    raise AssertionError("true main-thread blocking acquire entry was not observed")
        except BaseException as error:
            holder_errors.append(error)
        finally:
            history.append({"event": "holder_releases_real_lock", "ident": threading.get_ident()})

    thread = threading.Thread(target=holder, name="r158-t2-real-event-lock-holder")
    record = observed.add(thread, "helper_thread")
    record["initialized"] = True
    observed.wait_observer = observer
    thread.start()
    assert held.wait(timeout=4)
    return history, holder_errors, thread, state


def _b_t2_case_evidence(directory, name, value):
    path = directory / (name + ".json")
    with path.open("x", encoding="utf-8") as stream:
        json.dump(_b_t2_plain(value), stream, sort_keys=True, ensure_ascii=False,
                  allow_nan=False, indent=2)
        stream.write("\n")
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _b_t2_operation(runtime, events, request):
    raw = request.to_payload()
    with runtime._local_publication_scope(
        operation_id=raw["payload"]["event_key"], operation_sha256=_b_t2_digest(raw)
    ):
        result = events.transition_visual_bootstrap_if_current(request=request)
    assert result is not None
    assert result.write_disposition in {"NEW_COMMIT", "HISTORICAL_DUPLICATE"}
    return result


def _b_t2_operation_rows(reads, operation_id):
    return {
        database: [dict(row) for row in connection.execute(
            "SELECT * FROM " + table + " WHERE operation_id=?", (operation_id,)
        )]
        for database, connection, table in (
            ("event", reads["event"], "visual_local_publications_v1"),
            ("job", reads["job"], "simulation_local_publications_v1"),
        )
    }


def _b_t2_find_local_bootstraps(value, original):
    found = []
    if isinstance(value, str):
        if value.startswith(("{", "[")):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                return found
            return _b_t2_find_local_bootstraps(decoded, original)
    elif isinstance(value, dict):
        if (value.get("schema_version") == "visual.bootstrap.record.local.v1"
                and value.get("original_time") == original):
            found.append(value)
        for item in value.values():
            found.extend(_b_t2_find_local_bootstraps(item, original))
    elif isinstance(value, (tuple, list)):
        for item in value:
            found.extend(_b_t2_find_local_bootstraps(item, original))
    return found


def _b_t2_retained_spend(snapshot, before_record, debit):
    original = before_record["original_time"]
    records = _b_t2_find_local_bootstraps(snapshot["event"], original)
    assert records, "actual event storage must retain the original local bootstrap"
    latest = max(records, key=lambda item: item["payload"]["revision"])
    before, after = before_record["payload"]["state"], latest["payload"]["state"]
    assert latest["original_time"] == original
    assert after["original_budget_reference"] == before["original_budget_reference"]
    assert after["remaining_reobservations"] == before["remaining_reobservations"] - debit
    assert after["remaining_retries"] == before["remaining_retries"]
    assert after["limits"] == before["limits"]
    assert after["verification_rounds"] == before["verification_rounds"] + debit
    return latest


def _b_t2_detached_read(repo, run_id, operation_id, *, expected_job_phase, expected_job_rows):
    summary = repo.read_local_publication(run_id)
    exported = _b_t2_plain(summary)
    assert isinstance(exported, list), "actual durable publication row list required"
    assert all(isinstance(row, dict) for row in exported), "actual durable publication rows required"
    assert expected_job_phase in (None, "EVENT_COMMITTED", "COMPLETE")
    assert isinstance(expected_job_rows, list) and all(isinstance(row, dict) for row in expected_job_rows)
    assert all(row.get("operation_id") == operation_id for row in expected_job_rows)
    metadata = {"write_disposition": "HISTORICAL_ONLY", "confirmation_state": "UNKNOWN",
                "accepted": False, "live_authority": False}
    for row in exported:
        assert row.get("write_disposition") == "HISTORICAL_ONLY"
        assert row.get("confirmation_state") == "UNKNOWN"
        assert row.get("accepted") is False
        assert row.get("live_authority") is False
    selected = [row for row in exported if row.get("operation_id") == operation_id]
    if expected_job_phase is None:
        assert expected_job_rows == [] and selected == [], "event-only commit has no job receipt"
    else:
        assert len(expected_job_rows) == len(selected) == 1, "one exact target job receipt required"
        expected = expected_job_rows[0]
        assert expected["phase"] == selected[0]["phase"] == expected_job_phase
        assert set(selected[0]) == set(expected) | set(metadata), "detached row columns differ"
        assert {key: selected[0][key] for key in expected} == expected, "detached row differs from SQL"

    def check(value):
        if isinstance(value, dict):
            assert value.get("write_disposition") != "NEW_COMMIT"
            for key in ("authorizes_effect", "new_commit", "live_authority"):
                assert value.get(key) in (None, False)
            for item in value.values():
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    check(exported)
    changed = copy.deepcopy(exported)
    if isinstance(changed, dict):
        changed["caller_only"] = "cannot-mint-private-scope"
    else:
        changed.append({"caller_only": "cannot-mint-private-scope"})
    assert _b_t2_plain(repo.read_local_publication(run_id)) == exported
    return exported


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_memory_sqlite_publication_wait_requires_current_d(monkeypatch, tmp_path, request, backend):
    with _b_t2_attempt(request) as attempt:
        _b_t2_api()
        attempt["entered_behavior"] = True
        with _b_t2_observe(monkeypatch, attempt) as observed:
            for domain in ("D_app", "D_lease"):
                directory = tmp_path / (backend + "-wait-" + domain)
                clock_start = len(observed.clocks)

                def exercise(runtime, session, worker, repo, job, events, reads, observed):
                    from cloud_edge_robot_arm.contracts import RobotState
                    from cloud_edge_robot_arm.simulation_runtime.operational_lease import OperationalLeaseError

                    initial = runtime.bootstrap.to_payload()
                    before = _b_t2_snapshot(events, reads)
                    operation_id = backend + ":blocked:" + domain
                    transition = _b_t2_bootstrap_request(
                        runtime.bootstrap, "RESERVE_INITIAL_CAPTURE", operation_id
                    )
                    history, errors, holder, state = _b_t2_wait_for_event_lock(
                        runtime, session, repo, events, observed, domain, clock_start=clock_start
                    )
                    try:
                        with pytest.raises((RuntimeError, ValueError),
                                           match="expired|deadline|invalid|bound|live|domain|authority") as first_denial:
                            _b_t2_operation(runtime, events, transition)
                    finally:
                        observed.wait_observer = None
                        for release in observed.release_events:
                            release.set()
                        holder.join(timeout=5)
                        assert not holder.is_alive()
                        assert not errors, errors
                    names = [item["event"] for item in history]
                    for earlier, later in zip((
                        "holder_owns_real_lock", "real_lock_acquire_c_call",
                        "main_returned_from_profile_inside_real_acquire", "advance_original_counter",
                    ), (
                        "real_lock_acquire_c_call", "main_returned_from_profile_inside_real_acquire",
                        "advance_original_counter", "holder_releases_real_lock",
                    )):
                        assert names.index(earlier) < names.index(later)
                    assert state["returned"] is True
                    after = _b_t2_snapshot(events, reads)
                    retained = _b_t2_retained_spend(after, initial, 0)
                    assert retained["payload"]["revision"] == initial["payload"]["revision"]
                    assert retained["payload"]["pending"] == initial["payload"]["pending"]
                    job_rows = [dict(row) for row in reads["job"].execute(
                        "SELECT * FROM simulation_local_publications_v1 WHERE operation_id=?",
                        (operation_id,),
                    )]
                    assert not any(row["phase"] == "COMPLETE" for row in job_rows)
                    if domain == "D_lease":
                        advances = [item for item in history
                                    if item["event"] == "advance_original_counter"
                                    and item["kind"] == "D_lease"]
                        assert len(advances) == 1
                        assert advances[0]["before"] < session.ttl_ns <= advances[0]["after"]
                        with pytest.raises(
                            OperationalLeaseError,
                            match=r"^session is closed, revoked or unregistered$",
                        ) as subsequent_denial:
                            runtime.reserve_capture(RobotState(connected=True), initial=True)
                        assert type(subsequent_denial.value) is OperationalLeaseError
                    else:
                        with pytest.raises((RuntimeError, ValueError),
                                           match="expired|deadline|invalid|bound|live|domain|authority") as subsequent_denial:
                            runtime.reserve_capture(RobotState(connected=True), initial=True)
                    _b_t2_case_evidence(directory, "after-both-lock-denial", {
                        "domain": domain, "backend": backend, "before": before, "after": after,
                        "initial": initial, "retained": retained, "history": history,
                        "job_rows": job_rows, "worker_id": id(worker), "session_id": id(session),
                        "job_repository_id": id(repo), "event_repository_id": id(events),
                        "clock_identities": [asdict(raw.current_identity)
                                             for _, raw, _ in observed.clocks],
                        "first_denial": {"type": type(first_denial.value).__name__,
                                         "message": str(first_denial.value)},
                        "subsequent_denial": {"type": type(subsequent_denial.value).__name__,
                                              "message": str(subsequent_denial.value)},
                    })
                    return operation_id

                assert _b_t2_exercise(monkeypatch, directory, backend, observed, exercise)


def test_dual_database_order_and_partial_commit(monkeypatch, tmp_path, request):
    with _b_t2_attempt(request) as attempt:
        _b_t2_api()
        attempt["entered_behavior"] = True
        with _b_t2_observe(monkeypatch, attempt) as observed:
            cases = (("event", "PENDING"), ("job", "EVENT_COMMITTED"),
                     ("event", "COMPLETE"), ("job", "COMPLETE"))
            for index, (database, phase) in enumerate(cases):
                directory = tmp_path / ("commit-seam-" + str(index))

                def exercise(runtime, session, worker, repo, job, events, reads, observed):
                    before_record = _b_t2_capture_and_unusable_plan(runtime, events, "seam-setup")
                    before = _b_t2_snapshot(events, reads)
                    operation_id = "commit-seam:" + str(index)
                    transition = _b_t2_bootstrap_request(
                        before_record, "RESERVE_REOBSERVATION", operation_id
                    )
                    observed.fault.update(operation_id=operation_id, database=database,
                                          phase=phase, fired=False)
                    try:
                        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                            _b_t2_operation(runtime, events, transition)
                    finally:
                        observed.fault["operation_id"] = None
                    assert observed.fault["fired"] is True
                    faults = [item for item in attempt["observations"]["scenarios"]
                              if item.get("operation_id") == operation_id
                              and item.get("kind") == "TRUE_COMMIT_THEN_SAME_CONNECTION_CLOSE"]
                    assert len(faults) == 1
                    assert faults[0]["in_transaction_after_commit"] is False
                    assert faults[0]["actual_closed_connection_error"]["type"] == "ProgrammingError"
                    rows = _b_t2_operation_rows(reads, operation_id)
                    assert rows[database] and any(row["phase"] == phase for row in rows[database])
                    identity = before_record.to_payload()["original_time"]["lease_identity"]
                    for row in rows["event"] + rows["job"]:
                        assert row["operation_id"] == operation_id
                        assert row["operation_sha256"] == _b_t2_digest(transition)
                        for field in ("job_id", "lease_id", "attempt", "epoch"):
                            assert row[field] == identity[field]
                        assert type(row["event_record_hash"]) is str and len(row["event_record_hash"]) == 64
                    if index == 0:
                        assert rows["job"] == [], "event PENDING COMMIT must precede the job receipt"
                    both_complete = all(any(row["phase"] == "COMPLETE" for row in value)
                                        for value in rows.values())
                    assert both_complete is (index == 3)
                    if index < 2:
                        assert not any(row["phase"] == "COMPLETE" for row in rows["event"])
                    if index == 2:
                        assert not any(row["phase"] == "COMPLETE" for row in rows["job"])
                    after = _b_t2_snapshot(events, reads)
                    _b_t2_retained_spend(after, before_record.to_payload(), 1)
                    _b_t2_case_evidence(directory, "true-commit-loss", {
                        "database": database, "phase": phase, "before": before, "after": after,
                        "rows": rows, "fault": faults[0], "both_complete": both_complete,
                        "operation_id": operation_id, "operation_sha256": _b_t2_digest(transition),
                        "original": before_record.to_payload()["original_time"],
                        "returned_NEW_COMMIT": False,
                    })
                    return {"operation_id": operation_id, "run_id": runtime.source.run_id,
                            "job_path": str(repo.database_path), "event_path": str(events.path),
                            "before_record": before_record.to_payload(), "request": transition.to_payload()}

                saved = _b_t2_exercise(monkeypatch, directory, "sqlite", observed, exercise)
                # A new repository has no live owner/session. Reconciliation is evidence only.
                from cloud_edge_robot_arm.repositories.event_autonomy import SQLiteEventAutonomyRepository
                from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
                    VisualBootstrapTransitionInput,
                )
                from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository

                restarted_job = SQLiteSimulationJobRepository(Path(saved["job_path"]))
                restarted_event = SQLiteEventAutonomyRepository(Path(saved["event_path"]))
                job_read = event_read = None
                try:
                    job_read = sqlite3.connect(saved["job_path"])
                    event_read = sqlite3.connect(saved["event_path"])
                    job_read.row_factory = event_read.row_factory = sqlite3.Row
                    read_map = {"job": job_read, "event": event_read}
                    before_restart = _b_t2_snapshot(restarted_event, read_map)
                    expected_job_phase = (None, "EVENT_COMMITTED", "EVENT_COMMITTED", "COMPLETE")[index]
                    before_rows = _b_t2_operation_rows(read_map, saved["operation_id"])
                    if expected_job_phase is None:
                        assert before_rows["job"] == []
                    else:
                        assert len(before_rows["job"]) == 1
                        assert before_rows["job"][0]["phase"] == expected_job_phase
                    detached = _b_t2_detached_read(
                        restarted_job, saved["run_id"], saved["operation_id"],
                        expected_job_phase=expected_job_phase, expected_job_rows=before_rows["job"],
                    )
                    reconciliation = _b_t2_plain(restarted_job.reconcile_local_publications())
                    with pytest.raises((RuntimeError, ValueError), match="owner|scope|private|authority|session"):
                        restarted_event.transition_visual_bootstrap_if_current(
                            request=VisualBootstrapTransitionInput.from_payload(saved["request"])
                        )
                    after_restart = _b_t2_snapshot(restarted_event, read_map)
                    _b_t2_retained_spend(after_restart, saved["before_record"], 1)
                    new_rows = _b_t2_operation_rows(read_map, saved["operation_id"])
                    assert new_rows["job"] == before_rows["job"]
                    if index != 3:
                        assert not all(any(row["phase"] == "COMPLETE" for row in value)
                                       for value in new_rows.values())
                    _b_t2_case_evidence(directory, "restart-no-authority", {
                        "before": before_restart, "after": after_restart, "detached": detached,
                        "reconciliation": reconciliation, "rows": new_rows,
                        "expected_job_phase": expected_job_phase,
                        "independent_job_rows_before": before_rows["job"],
                    })
                finally:
                    restarted_event.close()
                    if job_read is not None:
                        job_read.close()
                    if event_read is not None:
                        event_read.close()

            directory = tmp_path / "same-live-owner"

            def continue_live(runtime, session, worker, repo, job, events, reads, observed):
                before = _b_t2_capture_and_unusable_plan(runtime, events, "live-setup")
                transition = _b_t2_bootstrap_request(before, "RESERVE_REOBSERVATION", "live-exact-operation")
                committed = _b_t2_operation(runtime, events, transition)
                assert committed.write_disposition == "NEW_COMMIT"
                rows = _b_t2_operation_rows(reads, "live-exact-operation")
                assert all(any(row["phase"] == "COMPLETE" for row in value) for value in rows.values())
                for row in rows["event"] + rows["job"]:
                    assert row["operation_sha256"] == _b_t2_digest(transition)
                    assert row["job_id"] == runtime.source.job_id
                    assert row["lease_id"] == before.to_payload()["original_time"]["lease_identity"]["lease_id"]
                state = committed.record.to_payload()
                duplicate = _b_t2_operation(runtime, events, transition)
                assert duplicate.write_disposition == "HISTORICAL_DUPLICATE"
                assert duplicate.record.to_payload()["payload"] == state["payload"]
                assert duplicate.record.to_payload()["original_time"] == state["original_time"]
                assert len(rows["job"]) == 1 and rows["job"][0]["phase"] == "COMPLETE"
                _b_t2_detached_read(
                    repo, runtime.source.run_id, "live-exact-operation",
                    expected_job_phase="COMPLETE", expected_job_rows=rows["job"],
                )
                changed = copy.deepcopy(transition.to_payload())
                changed["payload"]["robot_state"]["connected"] = False
                from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import VisualBootstrapTransitionInput
                with pytest.raises((RuntimeError, ValueError), match="changed|hash|conflict|identity|source"):
                    _b_t2_operation(runtime, events, VisualBootstrapTransitionInput.from_payload(changed))
                after = _b_t2_snapshot(events, reads)
                _b_t2_retained_spend(after, before.to_payload(), 1)
                _b_t2_case_evidence(directory, "same-owner-exact-history", {
                    "before": before.to_payload(), "current": state, "rows": rows,
                    "after": after, "duplicate_disposition": duplicate.write_disposition,
                    "expected_job_phase": "COMPLETE", "independent_job_rows_before": rows["job"],
                })
                return True

            assert _b_t2_exercise(monkeypatch, directory, "sqlite", observed, continue_live)


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_original_budget_debit_not_refilled_by_retry(monkeypatch, tmp_path, request, backend):
    with _b_t2_attempt(request) as attempt:
        _b_t2_api()
        attempt["entered_behavior"] = True
        with _b_t2_observe(monkeypatch, attempt) as observed:
            for lost_response in (False, True):
                directory = tmp_path / (backend + ("-ack-loss" if lost_response else "-one-CAS"))

                def exercise(runtime, session, worker, repo, job, events, reads, observed):
                    import time
                    from cloud_edge_robot_arm.contracts import RobotState

                    record = _b_t2_capture_and_unusable_plan(runtime, events, "budget-setup")
                    before = record.to_payload()
                    operation_id = backend + ":budget:" + str(lost_response)
                    transition = _b_t2_bootstrap_request(record, "RESERVE_REOBSERVATION", operation_id)
                    if lost_response:
                        observed.fault.update(operation_id=operation_id, database="job",
                                              phase="COMPLETE", fired=False)
                        try:
                            with pytest.raises(sqlite3.ProgrammingError, match="closed"):
                                _b_t2_operation(runtime, events, transition)
                        finally:
                            observed.fault["operation_id"] = None
                        assert observed.fault["fired"] is True
                    else:
                        first = _b_t2_operation(runtime, events, transition)
                        assert first.write_disposition == "NEW_COMMIT"
                    spent = runtime.bootstrap.to_payload()
                    assert spent["payload"]["revision"] == before["payload"]["revision"] + 1
                    _b_t2_retained_spend(_b_t2_snapshot(events, reads), before, 1)
                    duplicate = _b_t2_operation(runtime, events, transition)
                    assert duplicate.write_disposition == "HISTORICAL_DUPLICATE"
                    assert duplicate.record.to_payload()["payload"] == spent["payload"]
                    assert duplicate.record.to_payload()["original_time"] == before["original_time"]
                    assert runtime.bootstrap.to_payload()["payload"] == spent["payload"]
                    # The true installed heartbeat thread performs renewal; no permission callback.
                    lease_before = dict(reads["job"].execute(
                        "SELECT * FROM simulation_operational_leases_v1 WHERE lease_id=?", (session.lease_id,)
                    ).fetchone())
                    limit = time.monotonic() + min(60.0, worker.lease_ttl_seconds / 3 + 5.0)
                    renewed = None
                    while time.monotonic() < limit:
                        row = dict(reads["job"].execute(
                            "SELECT * FROM simulation_operational_leases_v1 WHERE lease_id=?", (session.lease_id,)
                        ).fetchone())
                        if row["generation"] > lease_before["generation"]:
                            renewed = row
                            break
                        time.sleep(0.01)
                    assert renewed is not None, "actual installed heartbeat renewal was not observed"
                    assert runtime.bootstrap.to_payload()["original_time"] == before["original_time"]
                    assert runtime.bootstrap.to_payload()["payload"]["state"] == spent["payload"]["state"]
                    with pytest.raises((RuntimeError, ValueError), match="pending|claimed|source|claim|replay"):
                        runtime.reserve_capture(RobotState(connected=True))
                    assert runtime.bootstrap.to_payload()["payload"]["state"] == spent["payload"]["state"]
                    with pytest.raises((RuntimeError, ValueError), match="owner|scope|private|authority|operational"):
                        events.initialize_visual_bootstrap_if_absent(record.definition)
                    after = _b_t2_snapshot(events, reads)
                    _b_t2_retained_spend(after, before, 1)
                    _b_t2_case_evidence(directory, "one-CAS-no-refund", {
                        "before": before, "spent": spent, "after": after,
                        "lost_response": lost_response, "duplicate": duplicate.write_disposition,
                        "lease_before": lease_before, "actual_renewed_row": renewed,
                        "original_time": runtime.bootstrap.to_payload()["original_time"],
                        "session_id": id(session), "worker_id": id(worker),
                    })
                    return True

                assert _b_t2_exercise(monkeypatch, directory, backend, observed, exercise)


def _b_t2_writer_json(value):
    from collections.abc import Mapping
    from dataclasses import fields

    if hasattr(value, "to_payload"):
        return _b_t2_writer_json(value.to_payload())
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _b_t2_writer_json(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _b_t2_writer_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_b_t2_writer_json(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if value is None or type(value) in (str, int, float, bool):
        return value
    raise TypeError(f"unsupported exact writer evidence {type(value).__name__}")


def _b_t2_writer_call(runtime, events, name, args=(), kwargs=None):
    kwargs = {} if kwargs is None else kwargs
    source = {"method": name, "args": _b_t2_writer_json(args),
              "kwargs": _b_t2_writer_json(kwargs)}
    with runtime._local_publication_scope(
        operation_id="writer-baseline:" + name,
        operation_sha256=_b_t2_digest(source),
    ):
        result = getattr(events, name)(*args, **kwargs)
    return result


def _b_t2_adopt_writer_task(runtime, events, key):
    from datetime import UTC, datetime, timedelta
    from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
    from cloud_edge_robot_arm.contracts import RobotState, TaskContract
    from tests.test_visual_bootstrap import frame
    from tests.test_visual_owner_repository import fresh_source_values

    original_time = copy.deepcopy(runtime.bootstrap.to_payload()["original_time"])
    definition = runtime.bootstrap.definition
    robot = RobotState(connected=True)
    capture_claim = runtime.reserve_capture(robot, initial=True)
    captured_at = datetime.now(UTC)
    observation = frame((None, None, captured_at), frame_id=key + ":owned-frame", at=captured_at)
    raw = observation.model_dump(mode="json")
    raw.update(episode_id=definition.episode_id, checksum_sha256="")
    observation = type(observation).model_validate(raw)
    runtime.complete_capture(capture_claim, observation, robot)
    plan_claim = runtime.reserve_plan(robot)
    prototype = fresh_source_values()["original"].contract.model_dump(mode="json")
    now = datetime.now(UTC)
    prototype.update(task_id=definition.episode_id, user_instruction=definition.user_instruction,
                     issued_at=now.isoformat(), timestamp=now.isoformat(),
                     valid_until=(now + timedelta(seconds=min(
                         definition.task_timeout_s, definition.verification_limits.deadline_s
                     ))).isoformat())
    proposal = TaskContract.model_validate(prototype)
    draft = PlannerDraft(
        raw_text="R158 T2 CPU planning data, no executor/action",
        parsed_json=proposal.model_dump(mode="json"),
        observation_evidence={**observation.evidence(),
                              "model_snapshot_hash": definition.model_snapshot_hash,
                              "role_bundle_hash": definition.role_bundle_hash},
    )
    runtime.complete_plan(plan_claim, draft, robot)
    assert runtime.bootstrap.planning_source_usable is True
    contract, publication = runtime.adopt_plan(robot)
    assert publication.to_payload()["schema_version"] == "visual.owner.publication.local.v1"
    assert publication.identity.task_id == contract.task_id == definition.episode_id
    assert publication.to_payload()["original_time"] == original_time
    assert runtime.bootstrap.to_payload()["original_time"] == original_time
    assert runtime.bootstrap.terminal_reason == "original_adopted"
    return contract, publication, observation, robot


def _b_t2_writer_inputs(runtime, events, contract, publication, observation, robot):
    from dataclasses import replace
    from datetime import UTC, datetime
    from cloud_edge_robot_arm.contracts.models import (
        CommandAck, CompletionSummary, EdgeEvent, FailureSummary, LocalReplanningRequest,
        LocalReplanningResponse, PendingMessage, ReplanApplyRecord,
    )
    from cloud_edge_robot_arm.edge.evidence.conditions import OnlineEvidenceSnapshot
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryRecord, checkpoint_digest
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import VisualBootstrapPromotionInput
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import VisualVerificationRouteInput

    now = datetime.now(UTC)
    original = runtime.original
    checkpoint = publication.checkpoint
    pool = events.get_verification_budget(contract.task_id)
    retry = events.get_retry_budget(contract.task_id)
    assert pool.task_id == retry.task_id == contract.task_id
    assert pool.state.original_budget_reference == original.local_time.to_payload()["verification_reference"]
    assert retry.original_recovery_reference == original.local_time.to_payload()["recovery_reference"]
    common = dict(task_id=contract.task_id, plan_version=contract.plan_version,
                  command_seq=contract.command_seq, timestamp=now)
    event = EdgeEvent(**common, event_id="t2-writer-event", event_type="GRASP_FAILED",
                      step_id=checkpoint.current_step_id, severity="ERROR")
    _b_t2_writer_call(runtime, events, "save_event", (event,))
    recovery = RecoveryRecord(
        "t2-writer-recovery", event.event_id, contract.task_id, runtime.source.run_id,
        "DETECTED", pool.state, "", None, "", "CPU source detection only",
        task_budget_revision=pool.revision, plan_version=contract.plan_version,
        command_seq=contract.command_seq, failure_plan_version=contract.plan_version,
        failure_command_seq=contract.command_seq, episode_id=publication.identity.episode_id,
        step_id=checkpoint.current_step_id,
        skill=contract.steps[checkpoint.current_step_index].skill.value,
        payload_hash=publication.contract_hash, checkpoint_hash=checkpoint.checkpoint_hash,
        conditions=original.requirements[checkpoint.current_step_id].postconditions,
    )
    recovery = _b_t2_writer_call(runtime, events, "initialize_recovery_if_absent", (recovery,))
    replan = LocalReplanningRequest(
        request_id="t2-writer-replan", trigger_event_id=event.event_id,
        robot_id=publication.identity.robot_id, task_id=contract.task_id,
        plan_id=publication.identity.plan_id, current_plan_version=contract.plan_version,
        current_command_seq=contract.command_seq,
    )
    _b_t2_writer_call(runtime, events, "save_replan_request", (replan,))
    apply = ReplanApplyRecord(
        apply_id="t2-writer-apply", request_id=replan.request_id, task_id=contract.task_id,
        plan_id=publication.identity.plan_id, robot_id=publication.identity.robot_id,
        previous_plan_version=contract.plan_version, previous_command_seq=contract.command_seq,
        new_plan_version=contract.plan_version + 1, new_command_seq=contract.command_seq + 1,
        checkpoint_id=checkpoint.checkpoint_id, checkpoint_hash=checkpoint.checkpoint_hash,
        status="APPLIED", reason="diagnostic source record only; no edge activation",
    )
    apply = _b_t2_writer_call(runtime, events, "save_replan_apply_record", (apply,))
    message = PendingMessage(message_id="t2-writer-outbox", task_id=contract.task_id,
                             event_id=event.event_id, request_id=replan.request_id,
                             message_type="LOCAL_REPLAN_REQUEST", payload=replan.model_dump(mode="json"))
    _b_t2_writer_call(runtime, events, "enqueue_outbox", (message,))
    claimed = _b_t2_writer_call(runtime, events, "claim_outbox_message")
    assert claimed is not None and claimed.message_id == message.message_id
    replacement = checkpoint.model_copy(update={"updated_at": now, "checkpoint_hash": ""}, deep=True)
    replacement = type(checkpoint).model_validate(replacement.model_dump(mode="json"))
    replacement = replacement.model_copy(update={"checkpoint_hash": checkpoint_digest(replacement)})
    response = LocalReplanningResponse(request_id=replan.request_id, new_steps=contract.steps,
                                      new_plan_version=contract.plan_version + 1,
                                      new_command_seq=contract.command_seq + 1)
    failure = FailureSummary(**common, failure_event_id=event.event_id,
                             failed_step_id=checkpoint.current_step_id, reason="CPU input",
                             local_retry_count=0, recovery_hint="no physical execution")
    completion = CompletionSummary(**common, summary_id="t2-unauthorized-success",
                                   final_plan_version=contract.plan_version, result="SUCCESS")
    ack = CommandAck(**common, accepted=False, status="REJECTED", request_id=replan.request_id)
    # All these are complete concrete model inputs. Their diagnostic UTC is never a local lease.
    for model in (event, replan, apply, message, replacement, response, failure, completion, ack, contract):
        assert type(model).model_validate_json(model.model_dump_json()) == model
    bootstrap_raw = runtime.bootstrap.to_payload()
    history = bootstrap_raw["payload"]["history"]
    assert all(set(item) == {"request", "decision", "transaction", "resulting_record_hash"}
               for item in history)
    promotions = [item["request"] for item in history
                  if item["request"]["schema_version"] == "visual.bootstrap.promotion.local.v1"]
    assert len(promotions) == 1
    promotion = VisualBootstrapPromotionInput.from_payload(promotions[0])
    assert promotion.to_payload() == promotions[0]
    assert promotion.to_payload()["original_time"] == bootstrap_raw["original_time"]
    online = OnlineEvidenceSnapshot(
        observation, robot, {}, contract.plan_version, contract.command_seq, checkpoint.checkpoint_hash
    )
    route_payload = {
        "schema_version": "visual.verification.route-input.local.v1",
        "payload": {"scope": "SOURCE_ROUTE_ONLY", "original": original.to_payload(),
                    "publication": publication.to_payload(), "online": {
                        "observation": _b_t2_writer_json(online.observation),
                        "robot_state": _b_t2_writer_json(online.robot_state),
                        "visual_facts": _b_t2_writer_json(online.visual_facts),
                        "plan_version": online.plan_version, "command_seq": online.command_seq,
                        "context_hash": online.context_hash,
                    },
                    "step_id": checkpoint.current_step_id, "attempt": 1, "phase": "PRECONDITION",
                    "event_key": "t2-writer-route", "execution_contract": contract.model_dump(mode="json"),
                    "completion": None, "grounding_receipt": None},
        "original_time": original.local_time.to_payload(), "decision": None, "transaction": None,
        "diagnostics": {"utc": {}, "monotonic": None},
    }
    route = VisualVerificationRouteInput.from_payload(route_payload)
    assert route.to_payload() == route_payload
    # Registration is the minimum source producer, without invoking supervisor/camera effects.
    period, _ = runtime._runtime_option_sources()
    supervision = runtime.initialize_supervision(period, robot)
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import VisualSupervisionTransitionInput
    sraw = supervision.to_payload()
    supervision_request = VisualSupervisionTransitionInput.from_payload({
        "schema_version": "visual.supervision.transition.local.v1",
        "payload": {"scope": "SUPERVISION_SOURCE_ONLY", "task_id": contract.task_id,
                    "definition_hash": _b_t2_digest(sraw["payload"]["definition"]),
                    "expected_revision": supervision.revision, "expected_record_hash": _r179_state_hash(sraw),
                    "original": original.to_payload(), "publication": publication.to_payload(),
                    "robot_state": robot.model_dump(mode="json"), "step_id": checkpoint.current_step_id,
                    "cursor": 1, "kind": "RESERVE_CAPTURE", "event_key": "t2-public-supervision",
                    "model_snapshot_hash": runtime.bootstrap.definition.model_snapshot_hash,
                    "role_bundle": runtime.role_binding.bundle.evidence(), "claim_id": None,
                    "observation": None, "context": None, "decision": None,
                    "wait_duration_s": None, "wait_elapsed_s": None},
        "original_time": original.local_time.to_payload(), "decision": None, "transaction": None,
        "diagnostics": {"utc": {}, "monotonic": None},
    })
    return dict(original=original, checkpoint=checkpoint, replacement=replacement, pool=pool, retry=retry,
                event=event, recovery=recovery, replan=replan, response=response, apply=apply,
                message=message, failure=failure, completion=completion, ack=ack,
                promotion=promotion, route=route, supervision=supervision,
                supervision_request=supervision_request, online=online)


def _b_t2_writer_authorization(data, contract, publication):
    from datetime import UTC, datetime, timedelta
    from cloud_edge_robot_arm.edge.evidence.models import (
        ActionEvidenceContract, CommitContext, DecisionEnvelope, VisualEvidence,
    )
    from cloud_edge_robot_arm.edge.recovery.lifecycle import RecoveryAuthorizationEvidence

    recovery, online = data["recovery"], data["online"]
    observation = online.observation
    now = datetime.now(UTC)
    # Canonical CPU input, deliberately no registered local authority or successful verdict mock.
    visual = VisualEvidence(observation.observation_id, observation.calibration_version,
                            observation.captured_at, 0.001, 0.0, "CONFIRMED", "VALID")
    requirement = data["original"].requirements[recovery.step_id]
    assert data["original"].contract == contract
    step = next(item for item in contract.steps if item.step_id == recovery.step_id)
    assert requirement.expected_duration_s >= max(step.timeout_ms, step.expected_duration_ms) / 1000
    action = ActionEvidenceContract(
        evidence=visual, expected_duration_s=requirement.expected_duration_s,
        ordinary_ttl_s=requirement.ordinary_ttl_s, allowed_error_m=requirement.allowed_error_m,
        sensor_requirements=requirement.sensor_requirements, preconditions=requirement.preconditions,
        postconditions=requirement.postconditions, plan_version=contract.plan_version,
        command_seq=contract.command_seq, context_hash=data["checkpoint"].checkpoint_hash,
    )
    decision = DecisionEnvelope(
        "t2-CPU-data-not-private-permission", contract.task_id, publication.identity.episode_id,
        observation.observation_id, contract.plan_version, contract.command_seq, contract.scene_version,
        data["checkpoint"].checkpoint_hash, publication.contract_hash, "LOCAL_RECOVER",
        "CPU-input", "CPU-input", now, now + timedelta(seconds=1),
    )
    current = CommitContext(
        contract.task_id, publication.identity.episode_id, observation.observation_id,
        contract.plan_version, contract.command_seq, contract.scene_version,
        data["checkpoint"].checkpoint_hash, publication.contract_hash, False,
    )
    return RecoveryAuthorizationEvidence(recovery.recovery_id, decision, current, action, online,
                                         evidence_scope="SOFTWARE_ONLY")


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_b_local_writer_requires_private_scope(monkeypatch, tmp_path, request, backend):
    with _b_t2_attempt(request) as attempt:
        _b_t2_api()
        attempt["entered_behavior"] = True
        with _b_t2_observe(monkeypatch, attempt) as observed:
            directory = tmp_path / (backend + "-writer-fence")

            def exercise(runtime, session, worker, repo, job, events, reads, observed):
                from datetime import UTC, datetime
                from cloud_edge_robot_arm.edge.recovery.lifecycle import (
                    RecoveryReservationEvidence, RecoveryTransitionEvidence,
                )

                initial = runtime.bootstrap
                raw_before = _b_t2_snapshot(events, reads)
                initial_request = _b_t2_bootstrap_request(
                    initial, "RESERVE_INITIAL_CAPTURE", "unowned-bootstrap-claim"
                )
                for name, args, kwargs in (
                    ("initialize_visual_bootstrap_if_absent", (initial.definition,), {}),
                    ("transition_visual_bootstrap_if_current", (), {"request": initial_request}),
                ):
                    with pytest.raises((RuntimeError, ValueError), match="private|operational|registered|owner|scope"):
                        getattr(events, name)(*args, **kwargs)
                    assert _b_t2_snapshot(events, reads)["event"] == raw_before["event"]
                contract, publication, observation, robot = _b_t2_adopt_writer_task(runtime, events, "writer")
                data = _b_t2_writer_inputs(runtime, events, contract, publication, observation, robot)
                task = contract.task_id
                checkpoint, recovery = data["checkpoint"], data["recovery"]
                authorization = _b_t2_writer_authorization(data, contract, publication)
                reservation = RecoveryReservationEvidence(robot, checkpoint.checkpoint_hash,
                                                           datetime.now(UTC), evidence_scope="SOFTWARE_ONLY")
                boundary = dict(task_id=task, owner_epoch=publication.identity.owner_epoch,
                                expected_owner_revision=publication.owner_revision,
                                expected_contract_hash=publication.contract_hash,
                                expected_checkpoint_hash=checkpoint.checkpoint_hash,
                                checkpoint=data["replacement"], grounding=None,
                                state_generation=publication.state_generation)
                inventory = [
                    ("initialize_visual_owner_if_absent", (data["original"], checkpoint,
                      data["pool"].state, data["retry"]), {"bootstrap_promotion": data["promotion"]}),
                    ("publish_visual_boundary_if_current", (), boundary),
                    ("route_visual_verification_if_current", (), {"request": data["route"]}),
                    ("initialize_visual_supervision_if_absent", (data["supervision"].definition,), {}),
                    ("transition_visual_supervision_if_current", (), {"request": data["supervision_request"]}),
                    ("save_event", (data["event"],), {}),
                    ("mark_event_handled", (data["event"].event_id,), {}),
                    ("save_retry_budget", (data["retry"],), {}),
                    ("initialize_retry_budget_if_absent", (data["retry"],), {}),
                    ("consume_retry_if_available", (task, recovery.step_id, recovery.skill,
                      data["retry"].retry_count_used, data["event"].event_id), {}),
                    ("initialize_verification_budget_if_absent", (task, data["pool"].state), {}),
                    ("initialize_recovery_if_absent", (recovery,), {}),
                    ("advance_recovery_if_current", (recovery,), dict(
                        expected_state=recovery.state, expected_revision=recovery.revision,
                        expected_budget_revision=data["pool"].revision,
                        verified_transition=RecoveryTransitionEvidence(recovery.state))),
                    ("reserve_reobservation_if_current", (), dict(
                        recovery_id=recovery.recovery_id, expected_revision=recovery.revision,
                        expected_budget_revision=data["pool"].revision, reservation=reservation)),
                    ("consume_retry_and_authorize_recovery_if_current", (), dict(
                        recovery_id=recovery.recovery_id, expected_recovery_revision=recovery.revision,
                        expected_verification_budget_revision=data["pool"].revision,
                        expected_retry_count=data["retry"].retry_count_used,
                        step_id=recovery.step_id, skill=recovery.skill, authorization=authorization)),
                    ("save_state", (task, "RUNNING", "unowned-positive"), {}),
                    ("save_state_transition", (task, "PAUSED", "RUNNING", "unowned-positive"), {}),
                    ("save_failure_summary", (data["failure"],), {}),
                    ("save_completion_summary", (data["completion"],), {}),
                    ("save_replan_request", (data["replan"],), {}),
                    ("save_replan_result", (data["response"],), {}),
                    ("save_active_contract", (contract,), dict(plan_id=publication.identity.plan_id,
                                                               robot_id=publication.identity.robot_id)),
                    ("advance_active_contract_if_current", (), dict(
                        task_id=task, expected_plan_version=contract.plan_version,
                        expected_command_seq=contract.command_seq, new_contract=contract,
                        plan_id=publication.identity.plan_id, robot_id=publication.identity.robot_id,
                        based_on_plan_version=contract.plan_version)),
                    ("save_execution_checkpoint", (data["replacement"],), {}),
                    ("compare_and_set_checkpoint", (), dict(checkpoint_id=checkpoint.checkpoint_id,
                        expected_checkpoint_hash=checkpoint.checkpoint_hash, new_checkpoint=data["replacement"])),
                    ("save_replan_apply_record", (data["apply"],), {}),
                    ("update_replan_apply_record_if_current", (data["apply"],), {"expected_status": data["apply"].status}),
                    ("save_command_ack", (data["ack"],), {}),
                    ("enqueue_outbox", (data["message"],), {}),
                    ("claim_outbox_message", (), {}),
                    ("mark_outbox_sent", (data["message"].message_id,), {}),
                    ("mark_outbox_failed", (data["message"].message_id, "unowned-positive"), {}),
                    ("advance_plan_version_if_current", (task, contract.plan_version, contract.command_seq,
                                                        contract.plan_version + 1, contract.command_seq + 1), {}),
                    ("record_audit_event", (task, "unowned-positive", {"claim": "not-private"}), {}),
                ]
                assert len({name for name, _, _ in inventory}) == len(inventory)
                denied = []
                mode = worker.operational_time_mode
                try:
                    # The poll's registered/frozen mode, not this public attribute, owns the boundary.
                    worker.operational_time_mode = "UTC_LEGACY_VETO"
                    for name, args, kwargs in inventory:
                        before = _b_t2_snapshot(events, reads)
                        with pytest.raises((RuntimeError, ValueError),
                                           match="private|operational|registered|owner|scope") as error:
                            getattr(events, name)(*args, **kwargs)
                        after = _b_t2_snapshot(events, reads)
                        assert after["event"] == before["event"], name
                        assert after["job"]["simulation_local_publications_v1"] == (
                            before["job"]["simulation_local_publications_v1"]), name
                        denied.append({"method": name, "args": _b_t2_writer_json(args),
                                       "kwargs": _b_t2_writer_json(kwargs),
                                       "exception": {"type": type(error.value).__name__, "message": str(error.value)},
                                       "before": before, "after": after,
                                       "event_rowhash": _b_t2_digest(before["event"])})
                finally:
                    worker.operational_time_mode = mode
                detached = repo.read_local_publication(runtime.source.run_id)
                with pytest.raises((RuntimeError, ValueError, TypeError), match="session|private|registered|scope"):
                    with repo._local_read_scope(detached, job_id=runtime.source.job_id,
                                                purpose="publication", operation_sha256=_b_t2_digest(detached)):
                        pytest.fail("detached SQL history minted a genuine private job view")
                budget_before = _b_t2_writer_json(events.get_verification_budget(task))
                retry_before = _b_t2_writer_json(events.get_retry_budget(task))
                events.save_state(task, "CANCELLED", "exact-negative-only-cancellation")
                assert events.get_state(task) == "CANCELLED"
                assert _b_t2_writer_json(events.get_verification_budget(task)) == budget_before
                assert _b_t2_writer_json(events.get_retry_budget(task)) == retry_before
                with pytest.raises((RuntimeError, ValueError), match="private|operational|registered|owner|scope|cancel"):
                    events.save_state(task, "RUNNING", "cannot-reactivate")
                with pytest.raises((RuntimeError, ValueError), match="private|operational|registered|owner|scope"):
                    events.save_state(task, "COMPLETED", "cannot-assert-success")
                assert events.get_state(task) == "CANCELLED"
                _b_t2_case_evidence(directory, "complete-writer-inventory", {
                    "backend": backend, "task_id": task, "original": data["original"].to_payload(),
                    "publication": publication.to_payload(), "initial_source": initial.to_payload(),
                    "denied": denied, "detached": _b_t2_writer_json(detached),
                    "negative_cancel": {"state": events.get_state(task), "pool": budget_before,
                                        "retry": retry_before},
                    "full_final_snapshot": _b_t2_snapshot(events, reads),
                    "background_job_rows": "Recorded in full; independent heartbeat rows may advance."
                })
                return True

            assert _b_t2_exercise(monkeypatch, directory, backend, observed, exercise)
