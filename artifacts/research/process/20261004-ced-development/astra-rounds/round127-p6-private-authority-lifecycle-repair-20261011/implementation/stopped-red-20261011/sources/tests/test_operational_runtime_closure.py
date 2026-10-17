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


def _evidence(tmp_path, name, payload):
    (tmp_path / f"{name}.json").write_text(json.dumps(payload, default=str, indent=2) + "\n")


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
            with repo.publication_guard(), closing(sqlite3.connect(repo.database_path)) as conn, conn:
                conn.execute("UPDATE simulation_jobs SET worker_id=?, lease_id=? WHERE job_id=?",
                             ("other", "other-lease", job.job_id))
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
            "attempts": before_attempts,
            "current": current.model_dump(mode="json"),
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
            observations.append({"cancelled_before_release": requests[0].cancelled.is_set(),
                                 "unusable_before_release": session._unusable.is_set()})
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
        return {"observations": observations, "late_reply_error": str(requests[0].error),
                "broker_thread": session.domain.owner_thread_id, "wait_cap": session.wait_cap}
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
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository

    clone = SQLiteSimulationJobRepository(database)
    assert captured[0][0]._closed and captured[0][0]._unusable.is_set()
    assert clone.list_attempts(job.run_id)[0].ended_at is None
    _evidence(tmp_path, "crash-snapshot-provenance", {"original_database": str(repo.database_path),
              "snapshot_database": str(database), "epoch_ended": captured[0][0]._closed,
              "snapshot_row": captured[0][2], "snapshot_attempts": clone.list_attempts(job.run_id)})
    return clone, job, *captured[0]


def _denied_with_unchanged_rows(repo, operation, *, status_none_allowed=False):
    before = _all_sql(repo)
    try:
        value = operation()
    except _api().OperationalLeaseError as error:
        rejection = {"kind": "OperationalLeaseError", "reason": str(error)}
    else:
        assert status_none_allowed and value is None, "authority exception required for void mutation"
        rejection = {"kind": "documented-status-CAS-None"}
    assert _all_sql(repo) == before, "denied operation changed persisted effects"
    return rejection


@pytest.mark.parametrize("variant", ["worker_mismatch", "lease_mismatch", "revoked_cleanup"],
                         ids=["worker_mismatch", "lease_mismatch", "revoked_cleanup"])
def test_operational_status_cas_cannot_grant_without_session(monkeypatch, tmp_path, variant):
    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_runtime.state_machine import ALLOWED_TRANSITIONS

    def revoked_check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        current = repo.get_job(job.job_id)
        assert current.status == RuntimeJobStatus.RUNNING
        assert current.worker_id == worker.worker_id and current.lease_id == session.lease_id
        assert RuntimeJobStatus.FINALIZING in ALLOWED_TRANSITIONS[current.status]
        session.invalidate("negative-only-cleanup-test")
        rejection = _denied_with_unchanged_rows(repo, lambda: repo.update_status_cas(
            job.job_id, expected=current.status, next_status=RuntimeJobStatus.FINALIZING,
            reason_code="forbidden-success", worker_id=worker.worker_id, lease_id=session.lease_id,
            expected_worker_id=current.worker_id, expected_lease_id=current.lease_id),
            status_none_allowed=True)
        # The legal-state positive challenge is completed before negative cancellation.
        repo.request_cancel(job.job_id)
        operations = [
            lambda: repo.save_metrics(job.job_id, [{"metric": "forbidden-success"}]),
            lambda: repo.save_artifacts(job.job_id, {"result": "forbidden-success.json"}),
            lambda: repo.finish_attempt(job.job_id, attempt=1, result="SUCCEEDED", error="",
                                       artifact_paths={"result": "forbidden-success.json"}),
        ]
        payload_rejections = [_denied_with_unchanged_rows(repo, operation) for operation in operations]
        repo.release_lease(session.lease_id)
        _evidence(tmp_path, "revoked-legal-source-denials", {"source": current.model_dump(mode="json"),
                  "positive_rejection": rejection, "payload_rejections": payload_rejections})
        return variant

    if variant == "revoked_cleanup":
        _exercise(monkeypatch, tmp_path, revoked_check)
        return
    trials = [(RuntimeJobStatus.RUNNING, RuntimeJobStatus.FINALIZING),
              (RuntimeJobStatus.FINALIZING, RuntimeJobStatus.SUCCEEDED)]
    for source, target in trials:
        trial_root = tmp_path / source.value.lower()
        trial_root.mkdir()
        def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
            current = repo.get_job(job.job_id)
            assert current.status == RuntimeJobStatus.RUNNING
            if source == RuntimeJobStatus.FINALIZING:
                # This preparation is actual authorized main-thread status CAS, never foreign success.
                prepared = repo.update_status_cas(job.job_id, expected=RuntimeJobStatus.RUNNING,
                    next_status=RuntimeJobStatus.FINALIZING, reason_code="legal-positive-source-preparation",
                    worker_id=worker.worker_id, lease_id=session.lease_id,
                    expected_worker_id=current.worker_id, expected_lease_id=current.lease_id)
                assert prepared is not None and prepared.status == RuntimeJobStatus.FINALIZING
            current = repo.get_job(job.job_id)
            assert current.status == source and target in ALLOWED_TRANSITIONS[source]
            assert current.worker_id == worker.worker_id and current.lease_id == session.lease_id
            errors, results = [], []
            def foreign():
                try:
                    proposed_worker = "changed-worker" if variant == "worker_mismatch" else worker.worker_id
                    proposed_lease = "changed-lease" if variant == "lease_mismatch" else session.lease_id
                    results.append(_denied_with_unchanged_rows(repo, lambda: repo.update_status_cas(
                        job.job_id, expected=source, next_status=target, reason_code="forbidden-positive-owner",
                        worker_id=proposed_worker, lease_id=proposed_lease,
                        expected_worker_id=current.worker_id, expected_lease_id=current.lease_id),
                        status_none_allowed=True))
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
                _evidence(trial_root, "legal-source-positive-challenge", {
                    "variant": variant, "source": current.model_dump(mode="json"),
                    "target": target.value, "rejections": results})
            finally:
                thread.join(timeout=2)
            return variant
        _exercise(monkeypatch, trial_root, check)


@pytest.mark.parametrize("variant", ["direct_legacy", "forged_tls", "nested_foreign_job"],
                         ids=["direct_legacy", "forged_tls", "nested_foreign_job"])
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
            foreign = repo.create_job(run_id="actual-second-operational", batch_id="", backend="MUJOCO",
                scenario_id=job.scenario_id, control_mode=job.control_mode, seed=job.seed,
                manifest_id=job.manifest_id, reproducibility_hash=job.reproducibility_hash,
                draft=job.draft, timeout_seconds=job.timeout_seconds, max_attempts=1,
                artifact_root="actual-second-operational", source_commit=job.source_commit,
                source_tree_hash=job.source_tree_hash)
            repo.update_status_cas(foreign.job_id, expected=RuntimeJobStatus.CREATED,
                next_status=RuntimeJobStatus.QUEUED, reason_code="second-actual-job",
                worker_id="", lease_id="")
            second = SimulationWorker(worker_id="second-actual-worker", backend="MUJOCO", repository=repo,
                artifact_root=tmp_path, planner_factory=worker.planner_factory,
                visual_role_binding=worker.visual_role_binding, visual_event_repository=worker.visual_event_repository,
                visual_robot_id=worker.visual_robot_id, operational_time_mode=MODE)
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
                    module._close_worker_lease_session(second._operational_lease_session, reason="second-test-finally")
            assert any(r["job_id"] == foreign.job_id for r in _rows(repo))
            with _tx(repo, session, job) as view:
                assert session.evaluate_locked(view).status == "VALID"
                before = tuple(tuple(view._connection.execute(f"SELECT * FROM {table} ORDER BY rowid"))
                               for table in ("simulation_metrics", "simulation_jobs"))
                with pytest.raises(module.OperationalLeaseError):
                    repo.save_metrics(foreign.job_id, [{"metric": "cross-job-nested"}])
                after = tuple(tuple(view._connection.execute(f"SELECT * FROM {table} ORDER BY rowid"))
                              for table in ("simulation_metrics", "simulation_jobs"))
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
            monkeypatch.setattr(session._queue, "get", fault_get)
        return owner
    monkeypatch.setattr(module, "open_operational_clock", broker_clock)
    original_connect = repo._connect
    def after_commit(conn):
        rows = [dict(row) for row in conn.execute("SELECT * FROM simulation_operational_leases_v1")]
        if not rows:
            return
        row = rows[0]
        if variant == "initial_heartbeat_failed" and not committed:
            committed.append({"row": row, "attempts": repo.list_attempts(job.run_id)})
        elif not faults and ((variant == "acquire_ack_lost" and row["attempt"] is None)
                             or (variant == "bind_ack_lost" and row["lifecycle"] == "ATTEMPT_BOUND")):
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
    monkeypatch.setattr(repo, "_connect", connections)
    errors = []
    try:
        try:
            worker.poll_once()
        except (module.OperationalLeaseError, sqlite3.Error) as error:
            errors.append(str(error))
        assert faults and committed, "actual requested commit/queue fault did not occur"
        assert sessions and sessions[0]._unusable.is_set() and sessions[0]._closed
        assert all(clock._closed for clock in clocks)
        _evidence(tmp_path, "actual-failure-cleanup", {"variant": variant, "committed": committed,
                  "faults": faults, "errors": errors, "after": _rows(repo)})
        return data, committed, sessions
    finally:
        events.close()
        if worker._operational_lease_session is not None:
            module._close_worker_lease_session(worker._operational_lease_session, reason="fault-test-finally")


@pytest.mark.parametrize("variant", ["bind_ack_lost", "initial_heartbeat_failed", "acquire_ack_lost"],
                         ids=["bind_ack_lost", "initial_heartbeat_failed", "acquire_ack_lost"])
def test_operational_failure_cleanup_closes_actual_attempt(monkeypatch, tmp_path, variant):
    data, committed, sessions = _faulted_poll(monkeypatch, tmp_path, variant)
    repo, job, worker, calls, received, backend, events = data
    if variant == "bind_ack_lost":
        assert committed[0]["attempts"] and committed[0]["attempts"][0].ended_at is None
    else:
        assert committed[0]["row"]["lifecycle"] == "ACQUIRED"
    assert all(a.ended_at is not None and a.result == "INTERRUPTED" for a in repo.list_attempts(job.run_id))
    assert repo.get_job(job.job_id).status.value not in {"LEASED", "STARTING", "RUNNING", "FINALIZING"}
    assert all(lease.released_at is not None for lease in repo.list_leases(job.run_id))
    assert _rows(repo)[0]["durable_phase"] in {"REVOKED", "TERMINATED"}
    before = repo.list_attempts(job.run_id)
    with pytest.raises(ValueError, match="operational"):
        repo.retry_job(job.job_id)
    assert repo.list_attempts(job.run_id) == before


@pytest.mark.parametrize("variant", ["committed", "revoked", "terminated"],
                         ids=["committed", "revoked", "terminated"])
def test_orphan_terminal_cleanup_covers_durable_phase(monkeypatch, tmp_path, variant):
    repo, job, session, original, crash = _unfinished_clone(monkeypatch, tmp_path)
    module = _api()
    phases = {"committed": "COMMITTED", "revoked": "REVOKED", "terminated": "TERMINATED"}
    statuses = {"committed": "RUNNING", "revoked": "CANCEL_REQUESTED", "terminated": "FINALIZING"}
    with repo.publication_guard(), closing(sqlite3.connect(repo.database_path)) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE simulation_jobs SET status=? WHERE job_id=?", (statuses[variant], job.job_id))
        row = dict(conn.execute("SELECT * FROM simulation_operational_leases_v1").fetchone())
        row.update(durable_phase=phases[variant], lifecycle="TERMINAL" if variant != "committed" else "ATTEMPT_BOUND")
        row["job_snapshot_json"] = repo._job_snapshot(conn, job.job_id)
        row["proposed_row_digest"] = module._canonical(row)
        conn.execute("UPDATE simulation_operational_leases_v1 SET durable_phase=?,lifecycle=?,"
                     "job_snapshot_json=?,proposed_row_digest=? WHERE job_id=?",
                     (row["durable_phase"], row["lifecycle"], row["job_snapshot_json"], row["proposed_row_digest"], job.job_id))
    assert repo.list_attempts(job.run_id)[0].ended_at is None
    assert session._closed and session._unusable.is_set()
    assert repo.terminate_orphaned_operational_attempts() == [job.job_id]
    attempts = repo.list_attempts(job.run_id)
    assert len(attempts) == 1 and attempts[0].ended_at is not None and attempts[0].result == "INTERRUPTED"
    assert repo.get_job(job.job_id).status.value == "INTERRUPTED"
    assert _rows(repo)[0]["durable_phase"] == "TERMINATED"
    assert _rows(repo)[0]["original_acquisition_json"] == crash["original_acquisition_json"]
    before = _all_sql(repo)
    assert repo.terminate_orphaned_operational_attempts() == []
    assert _all_sql(repo) == before
    _evidence(tmp_path, "durable-orphan", {"variant": variant, "before": row, "after": _rows(repo), "attempts": attempts})


@pytest.mark.parametrize("variant", ["purpose", "operation_digest", "identity_snapshot", "lifecycle_replay"],
                         ids=["purpose", "operation_digest", "identity_snapshot", "lifecycle_replay"])
def test_locked_view_issued_bindings_cannot_be_retargeted(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
        other = SQLiteSimulationJobRepository(tmp_path / "foreign-issued-view.db")
        if variant == "purpose":
            mutations = [("purpose", "heartbeat")]
        elif variant == "operation_digest":
            mutations = [("operation_sha256", "0" * 64)]
        elif variant == "lifecycle_replay":
            mutations = [("state", "OPEN")]
        else:
            mutations = [("_repository", other), ("_session", object()), ("_nonce", "changed"),
                         ("_thread_id", -1), ("_native_thread_id", -1), ("_connection", None)]
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
                    assert view._connection.execute("SELECT job_id FROM simulation_jobs WHERE job_id=?",
                                                    (job.job_id,)).fetchone() is not None
                    module._invalidate_view(view, "actual-owner-terminal-view-transition")
                    assert view.state == "INVALIDATED" and not session._unusable.is_set()
                    with pytest.raises(module.OperationalLeaseError):
                        session.evaluate_locked(view)
                    assert view._connection.in_transaction and view._proposal is None
                    assert view._connection.execute("SELECT job_id FROM simulation_jobs WHERE job_id=?",
                                                    (job.job_id,)).fetchone() is not None
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


@pytest.mark.parametrize("variant", ["exact_deadline", "after_deadline"],
                         ids=["exact_deadline", "after_deadline"])
def test_confirmation_consumption_keeps_previous_bound(monkeypatch, tmp_path, variant):
    def check(module, session, runtime, lease_raw, app_raw, worker, repo, job):
        lease_raw.now = 1_000_000_000
        with _tx(repo, session, job, "heartbeat") as view:
            proposal = session.propose_locked(view, ttl_ns=session.ttl_ns)
            ack = repo._commit_operational_proposal(view, proposal)
            previous, proposed = proposal._previous, proposal._segment
            assert previous is not None and previous.deadline.deadline_ns < proposed.deadline.deadline_ns
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
                    repo.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
                _evidence(tmp_path, "prior-bound-consumption", {"prior": previous.receipt(),
                          "proposed": proposed.receipt(), "current_ns": lease_raw.now,
                          "broker_thread": session.domain.owner_thread_id})
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
        draft["parameter_overrides"] = {**draft.get("parameter_overrides", {}), "runtime_delay_ms": 120}
        with repo.publication_guard(), closing(sqlite3.connect(repo.database_path)) as conn, conn:
            conn.execute("UPDATE simulation_jobs SET draft_json=? WHERE job_id=?", (json.dumps(draft), job.job_id))
        original = repo.heartbeat_lease
        def record_actual_call(*args, **kwargs):
            frame = inspect.currentframe()
            assert frame is not None and frame.f_back is not None
            caller = frame.f_back
            try:
                python_thread, native_thread = threading.get_ident(), threading.get_native_id()
                records.append({"python_thread": python_thread, "native_thread": native_thread,
                                "caller": caller.f_code.co_name})
                if caller.f_code is not worker._run.__func__.__code__:
                    # The true maintenance thread never borrows main D_app handles.
                    return original(*args, **kwargs)
                session = worker._operational_lease_session
                assert session is not None
                assert (python_thread, native_thread) == (session.main_thread, session.main_native_thread)
                owner = operational_windows._current_owner()
                assert owner is not None and owner._startup.worker is worker
                window, token, origin, clock = owner.task_window, owner.task_origin_token, owner.task_origin, owner.clock
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
                assert all(bound.deadline is saved for bound, saved in zip(after_owner._hard, hard, strict=True))
                assert all(deadline.origin is saved for deadline, saved in zip(hard, origins, strict=True))
                export_after = after_owner.export_record(window)
                assert export_after == export_before
                after_current = clock.read_current(after=token)
                assert before_current.domain == after_current.domain == clock.domain
                row_after = _rows(repo)[0]
                assert row_after["generation"] > row_before["generation"]
                assert row_after["original_acquisition_json"] == row_before["original_acquisition_json"]
                main_samples.append({"owner": owner, "clock": clock, "window": window, "token": token,
                    "origin": origin, "hard": hard, "deadline_origins": origins,
                    "export_before": export_before, "export_after": export_after,
                    "D_app_before": {"domain": asdict(before_current.domain), "lower_ns": before_current.lower_ns,
                                     "upper_ns": before_current.upper_ns},
                    "D_app_after": {"domain": asdict(after_current.domain), "lower_ns": after_current.lower_ns,
                                    "upper_ns": after_current.upper_ns},
                    "row_before": row_before, "row_after": row_after,
                    "python_thread": python_thread, "native_thread": native_thread})
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
        assert any(r["role"] == "heartbeat" and r["lifecycle"] == "ACQUIRED" for r in session.ingress_history)
        owner = runtime._operational_owner
        assert owner is not None and owner.task_window is not None
        late_export = owner.export_record(owner.task_window)
        for sample in main_samples:
            assert sample["owner"] is owner and sample["clock"] is owner.clock
            assert sample["window"] == owner.task_window and sample["token"] is owner.task_origin_token
            assert sample["origin"] is owner.task_origin
            assert sample["export_before"]["domain"] == late_export["domain"]
            assert sample["export_before"]["task_origin_event_id"] == late_export["task_origin_event_id"]
            # Inputs/source hashes/episode metadata may be enriched after the delay loop.
            # Every original deadline and budget remains exactly its original handle/receipt.
            assert all(any(bound.deadline is saved for bound in owner._hard) for saved in sample["hard"])
            assert all(deadline.origin is saved for deadline, saved in zip(sample["hard"], sample["deadline_origins"], strict=True))
            for deadline_receipt in sample["export_before"]["hard_deadlines"]:
                assert deadline_receipt in late_export["hard_deadlines"]
        errors = []
        def foreign():
            try:
                with module._heartbeat_lease_scope(session):
                    repo.heartbeat_lease(session.lease_id, lease_ttl_seconds=worker.lease_ttl_seconds)
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
        evidence = [{key: value for key, value in sample.items()
                     if key not in {"owner", "clock", "token", "origin", "hard", "deadline_origins"}}
                    for sample in main_samples]
        _evidence(tmp_path, "actual-heartbeat-producers", {"calls": records, "actual_main_before_after": evidence,
                  "later_app_export": late_export, "source_identity": session._binding_hash,
                  "ingress": session.ingress_history})
        return "actual-delay-loop-and-maintain-thread"
    _exercise(monkeypatch, tmp_path, check, configure=configure)
