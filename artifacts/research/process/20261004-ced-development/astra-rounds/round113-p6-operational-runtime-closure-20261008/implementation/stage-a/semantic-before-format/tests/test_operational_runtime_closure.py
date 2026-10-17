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
from contextlib import closing
from dataclasses import asdict
from pathlib import Path

import pytest

MODE = "OPERATIONAL_LEASE_FOUNDATION_V1"
MODULE = "cloud_edge_robot_arm.simulation_runtime.operational_lease"


def _api():
    path = Path(__file__).resolve().parents[1] / ("src/" + MODULE.replace(".", "/") + ".py")
    assert path.exists(), "R113 planned missing operational_lease broker/transaction API"
    module = importlib.import_module(MODULE)
    for name in (
        "OperationalLeaseSession", "LockedLeaseView", "LeaseProposal", "LeaseCommitAck",
        "_open_worker_lease_session", "_worker_lease_scope", "_close_worker_lease_session",
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
        return [dict(row) for row in conn.execute(
            "SELECT * FROM simulation_operational_leases_v1 ORDER BY lease_id"
        )]


def _all_sql(repo):
    with closing(sqlite3.connect(repo.database_path)) as conn, conn:
        return tuple(tuple(conn.execute(f"SELECT * FROM {table} ORDER BY rowid")) for table in (
            "simulation_jobs", "simulation_job_leases", "simulation_job_events",
            "simulation_job_attempts", "simulation_operational_leases_v1",
        ))


def _tx(repo, session, job, purpose="inspect"):
    return repo._operational_transaction(
        session, job_id=job.job_id, purpose=purpose,
        operation_sha256=hashlib.sha256(purpose.encode()).hexdigest(),
    )


def _evidence(tmp_path, name, payload):
    (tmp_path / f"{name}.json").write_text(json.dumps(payload, default=str, indent=2) + "\n")


def _exercise(monkeypatch, tmp_path, callback, *, initialize=None):
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
    monkeypatch.setattr(operational_windows, "open_operational_clock", lambda: clock_factory(app_raw))
    received = []

    def run(worker, repo, job, root):
        try:
            runtime = received[0][3].worker_runtime
            session = worker._operational_lease_session
            assert session is not None
            assert runtime._operational_owner is not None
            assert runtime._operational_owner.task_window is not None
            sessions.append(session)
            results.append(callback(module, session, runtime, broker_raw[0], app_raw[0],
                                    worker, repo, job))
        except BaseException as error:
            errors.append(error)
            raise

    data = software_factory(monkeypatch, tmp_path, during_initialize=initialize, during_episode=run)
    repo, job, worker, calls, received, backend, events = data
    worker.operational_time_mode = MODE
    try:
        assert worker.poll_once()
        if errors:
            raise errors[0]
        assert results, repo.get_job(job.job_id).error_message
        assert sessions[0]._closed
        assert all(owner._closed for owner in clocks)
        _evidence(tmp_path, "lifecycle", {
            "rows": _rows(repo), "calls": calls,
            "broker_identity": asdict(broker_raw[0].current_identity),
            "app_identity": asdict(app_raw[0].current_identity),
            "session_closed": sessions[0]._closed,
        })
        return results[0], data
    finally:
        events.close()
        if worker._operational_lease_session is not None:
            module._close_worker_lease_session(worker._operational_lease_session, reason="test-finally")


def test_two_issuer_threads_keep_domains_distinct(monkeypatch, tmp_path):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        from cloud_edge_robot_arm.research.operational_time_v1 import OperationalTimeError
        from cloud_edge_robot_arm.simulation_runtime.worker import VISUAL_WORKER_FACTORY_SOURCE_PATHS

        assert lease_raw.now == app_raw.now == 0
        assert lease_raw.current_identity.thread_id != app_raw.current_identity.thread_id
        assert lease_raw.current_identity.native_thread_id != app_raw.current_identity.native_thread_id
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


@pytest.mark.parametrize("variant", ["dict", "copy", "foreign_repo", "foreign_thread"],
                         ids=["dict", "copy", "foreign_repo", "foreign_thread"])
def test_caller_cannot_register_locked_view(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository

        before = _all_sql(repo)
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
                other = SQLiteSimulationJobRepository(repo.database_path)
                with pytest.raises(module.OperationalLeaseError):
                    with _tx(other, session, job) as foreign:
                        session.propose_locked(foreign, ttl_ns=session.ttl_ns)
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
        return variant
    _exercise(monkeypatch, tmp_path, check)


@pytest.mark.parametrize("variant", ["rollback", "cas_zero", "connection_close", "commit_close", "replay"],
                         ids=["rollback", "cas_zero", "connection_close", "commit_close", "replay"])
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
                    "UPDATE simulation_operational_leases_v1 SET row_revision=row_revision+1 WHERE job_id=?",
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
        _evidence(tmp_path, "terminal-view", {"variant": variant, "state": view.state,
                                              "rows": _rows(repo)})
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
        monkeypatch, tmp_path, during_episode=episode,
    )
    worker.operational_time_mode = MODE
    def holder():
        try:
            with repo.publication_guard():
                with closing(sqlite3.connect(repo.database_path, isolation_level=None)) as conn, conn:
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
        task_matches = [item.deadline for item in owner._hard
                        if item.source_id == owner._startup.job_source + ":task"]
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
        assert all(current.deadline is saved for current, saved in zip(
            owner._hard, original_hard, strict=True))
        assert row["attempt"] == repo.list_attempts(job.run_id)[0].attempt
        assert row["lifecycle"] == "ATTEMPT_BOUND"
        # Live producer identities are actual ingress records, not caller context copies.
        assert any(item["role"] == "heartbeat" for item in session.ingress_history)
        assert any(item["role"] == "main" for item in session.ingress_history)
        assert any(item["lifecycle"] == "ACQUIRED" and item["purpose"] == "heartbeat"
                   for item in session.ingress_history)
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
        assert not owner.clock.before_deadline(original_deadline,
                                               owner.clock.read_current(after=original_token))
        _evidence(tmp_path, "renewal", {"original": original, "row": row,
                                       "ingress": session.ingress_history})
        return original
    _exercise(monkeypatch, tmp_path, check)


@pytest.mark.parametrize("variant", ["expired", "cancelled", "reassigned"],
                         ids=["expired", "cancelled", "reassigned"])
def test_late_heartbeat_cannot_revive(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        before = _rows(repo)[0]
        if variant == "expired":
            lease_raw.now = json.loads(before["segment_json"])["deadline_ns"]
        elif variant == "cancelled":
            repo.request_cancel(job.job_id)
        else:
            current = repo.get_job(job.job_id)
            assert repo.update_status_cas(
                job.job_id, expected=current.status, next_status=current.status,
                reason_code="test-reassignment", worker_id="other", lease_id="other-lease",
            ) is not None
        generation = _rows(repo)[0]["generation"]
        with pytest.raises(module.OperationalLeaseError):
            repo.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
        assert _rows(repo)[0]["generation"] == generation
        from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
        other = SQLiteSimulationJobRepository(repo.database_path)
        with pytest.raises(module.OperationalLeaseError):
            other.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
        repo.release_lease(session.lease_id)
        assert _rows(repo)[0]["durable_phase"] in {"REVOKED", "TERMINATED"}
        return variant
    _exercise(monkeypatch, tmp_path, check)


@pytest.mark.parametrize("variant", ["rollback", "cas_zero", "confirmation_lost"],
                         ids=["rollback", "cas_zero", "confirmation_lost"])
def test_pending_proposal_requires_commit_confirmation(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        before = _rows(repo)[0]
        with _tx(repo, session, job, "heartbeat") as view:
            proposal = session.propose_locked(view, ttl_ns=session.ttl_ns)
            if variant == "rollback":
                view._connection.execute("ROLLBACK")
            elif variant == "cas_zero":
                view._connection.execute(
                    "UPDATE simulation_operational_leases_v1 SET row_revision=row_revision+1 WHERE job_id=?",
                    (job.job_id,),
                )
                with pytest.raises(module.OperationalLeaseError):
                    repo._commit_operational_proposal(view, proposal)
            else:
                ack = repo._commit_operational_proposal(view, proposal)
                assert _rows(repo)[0]["durable_phase"] == "COMMITTED"
                session.invalidate("confirmation-lost")
                with pytest.raises(module.OperationalLeaseError):
                    session.confirm_committed(ack)
        assert proposal.state != "ACTIVE"
        with pytest.raises(module.OperationalLeaseError):
            repo.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
        rows = _rows(repo)
        if variant != "confirmation_lost":
            assert rows[0]["generation"] == before["generation"]
        _evidence(tmp_path, "unacknowledged", {"variant": variant, "rows": rows,
                                               "proposal_state": proposal.state})
        return variant
    _exercise(monkeypatch, tmp_path, check)


@pytest.mark.parametrize("variant", ["recovery_service", "manual_retry"],
                         ids=["recovery_service", "manual_retry"])
def test_restart_terminates_without_reissue(monkeypatch, tmp_path, variant):
    captured = []
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        owner = runtime._operational_owner
        assert owner is not None and owner.task_window is not None
        captured.append((session, owner.export_record(owner.task_window), _rows(repo)[0]))
        return session.epoch
    _, data = _exercise(monkeypatch, tmp_path, check)
    repo, job, worker, calls, received, backend, events = data
    module = _api()
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.recovery import ArtifactRecoveryService
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository

    new = SQLiteSimulationJobRepository(repo.database_path)
    before_attempts = new.list_attempts(job.run_id)
    if variant == "recovery_service":
        ArtifactRecoveryService(repository=new, artifact_root=tmp_path,
                                requeue_recoverable=True).recover_interrupted_jobs()
    else:
        new.terminate_orphaned_operational_attempts()
        with pytest.raises(ValueError, match="operational"):
            new.retry_job(job.job_id)
    current = new.get_job(job.job_id)
    assert current.status != RuntimeJobStatus.QUEUED
    assert new.update_status_cas(
        job.job_id, expected=current.status, next_status=RuntimeJobStatus.QUEUED,
        reason_code="forbidden-requeue", worker_id="", lease_id="",
    ) is None
    assert new.list_attempts(job.run_id) == before_attempts
    with pytest.raises(module.OperationalLeaseError):
        captured[0][0].evaluate_locked(dict(captured[0][2]))
    # A still-live foreign identity is UNKNOWN; registry absence alone is insufficient.
    with new.publication_guard(), closing(sqlite3.connect(new.database_path)) as conn, conn:
        conn.execute("UPDATE simulation_operational_leases_v1 SET pid=?, epoch=?, durable_phase='COMMITTED'",
                     (os.getppid(), "unknown-foreign-live"))
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
        conn.execute("UPDATE simulation_jobs SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE job_id=?",
                     (legacy_job.job_id,))
    ArtifactRecoveryService(repository=legacy, artifact_root=legacy_path,
                            requeue_recoverable=True).recover_interrupted_jobs()
    assert legacy.get_job(legacy_job.job_id).status == RuntimeJobStatus.QUEUED
    _evidence(tmp_path, "restart", {"variant": variant, "attempts": before_attempts,
                                   "current": current.model_dump(mode="json")})
