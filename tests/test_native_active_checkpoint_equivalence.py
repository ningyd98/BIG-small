"""CPU-only equivalence controls for the teacher's live checkpoint."""

import multiprocessing
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.research import native_collection_application as collection
from cloud_edge_robot_arm.simulation_runtime import sqlite_repository
from cloud_edge_robot_arm.simulation_runtime.worker import CancelledByOperator
from cloud_edge_robot_arm.vision import worker_owner
from tests import test_native_collection_authority as authority

active_teacher_checkpoint = authority.active_teacher_checkpoint


def test_foreign_process_cancellation_between_same_step_checkpoints(tmp_path, monkeypatch):
    app = authority.application(tmp_path)
    seen = []

    def software_body(self, worker, job, *, start_monotonic):
        live = collection._live(self)
        live.worker_origin = worker._active_task_origin
        assert live.worker_origin[:2] == (job.job_id, start_monotonic)
        live.backend = SimpleNamespace(total_physics_steps=0)
        assert self.check_active()["lease"]["attempt"] == 1
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from pathlib import Path; "
                "from cloud_edge_robot_arm.simulation_runtime.sqlite_repository "
                "import SQLiteSimulationJobRepository; "
                "repo = SQLiteSimulationJobRepository(Path(sys.argv[1])); "
                "assert repo.request_cancel(sys.argv[2]).cancel_requested",
                os.fspath(live.repository.database_path),
                job.job_id,
            ],
            env={
                **os.environ,
                "PYTHONPATH": str(Path(sqlite_repository.__file__).resolve().parents[2]),
            },
            check=True,
            timeout=10,
        )
        try:
            self.check_active()
        except CancelledByOperator:
            assert live.backend.total_physics_steps == 0
            assert live.repository._teacher_checkpoint_connection() is None
            seen.append(job.job_id)
            raise
        pytest.fail("the next checkpoint accepted a committed cancellation")

    monkeypatch.setattr(collection.NativeCollectionApplication, "run_from_worker", software_body)
    with pytest.raises(RuntimeError, match='worker terminal outcome: .*"status": "CANCELLED"'):
        app.execute_once()
    assert len(seen) == 1


def test_unchanged_lease_rows_expire_on_next_clock_sample(active_teacher_checkpoint, monkeypatch):
    app, job, lease = active_teacher_checkpoint
    first = app.check_active()["lease"]
    expires = lease.expires_at
    assert datetime.fromisoformat(first["observed_at"]) < expires

    class AtExpiry(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is not None
            return expires.astimezone(tz)

    # Supply the lease reader with the exact boundary instant. No row changes
    # or sleep are needed, and the previous transaction has already ended.
    monkeypatch.setattr(worker_owner, "datetime", AtExpiry)
    with pytest.raises(ValueError, match="worker job identity"):
        app.check_active()
    assert app.repository.get_job(job.job_id).lease_expires_at == expires


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("config", "backend configuration changed"),
        ("physical", "registered physical budget exhausted"),
        ("rss", "registered process RSS budget exhausted"),
        ("deadline", "original operational deadline expired"),
        ("estop", "current robot hard safety stop"),
        ("collision", "current robot hard safety stop"),
        ("disconnected", "current robot hard safety stop"),
    ],
)
def test_mutable_guard_inputs_are_checked_again(active_teacher_checkpoint, monkeypatch,
                                                mutation, reason):
    app, _, _ = active_teacher_checkpoint
    live = collection._live(app)
    configuration = {"controller": "original"}
    live.config_json = collection.canonical(configuration)
    live.backend = SimpleNamespace(
        total_physics_steps=app.protocol["physical_budget"],
        _config=SimpleNamespace(model_dump=lambda **kwargs: configuration),
    )
    robot_state = SimpleNamespace(connected=True, estop_engaged=False, collision_detected=False)
    live.robot = SimpleNamespace(get_state=lambda: robot_state)
    checkpoint = {"name": "CPU equivalence control"}
    app._guard(checkpoint)
    assert len(live.checks) == 1

    if mutation == "config":
        configuration["controller"] = "changed in place"
    elif mutation == "physical":
        live.backend.total_physics_steps += 1
    elif mutation == "rss":
        monkeypatch.setattr(collection.resource, "getrusage", lambda _: SimpleNamespace(
            ru_maxrss=app.policy["rss_bytes"] // 1024 + 1,
        ))
    elif mutation == "deadline":
        monkeypatch.setattr(
            type(live.owner._source), "read_ns", lambda _: live.deadline.deadline_ns,
        )
    elif mutation == "estop":
        robot_state.estop_engaged = True
    elif mutation == "collision":
        robot_state.collision_detected = True
    else:
        robot_state.connected = False

    with pytest.raises(RuntimeError, match=reason):
        app._guard(checkpoint)
    assert len(live.checks) == 1


def test_renamed_database_during_checkpoint_releases_snapshot_and_lock(
    active_teacher_checkpoint, monkeypatch,
):
    app, _, lease = active_teacher_checkpoint
    repo = app.repository
    path = repo.database_path
    displaced = path.with_suffix(".displaced")
    original_get = repo.get_job

    def displace_once(job_id):
        result = original_get(job_id)
        if not displaced.exists():
            path.rename(displaced)
            sqlite3.connect(path).close()
        return result

    with monkeypatch.context() as patch:
        patch.setattr(repo, "get_job", displace_once)
        with pytest.raises(RuntimeError, match="database identity changed"):
            app.check_active()
    assert repo._teacher_checkpoint_connection() is None
    path.unlink()
    displaced.rename(path)
    other = sqlite_repository.SQLiteSimulationJobRepository(path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(other.heartbeat_lease, lease.lease_id, lease_ttl_seconds=90).result(timeout=5)
    app.check_active()


def test_lifecycle_reader_thread_and_fault_isolation(active_teacher_checkpoint):
    app, job, lease = active_teacher_checkpoint
    repo = app.repository
    database = collection._live(app).checkpoint_database

    def read_in_other_thread():
        with repo._teacher_checkpoint_read(database):
            connection = repo._teacher_checkpoint_connection()
            assert repo.get_job(job.job_id).lease_id == lease.lease_id
            assert connection.in_transaction
        return connection

    with repo._teacher_checkpoint_lifecycle(database):
        with repo._teacher_checkpoint_read(database):
            owner_connection = repo._teacher_checkpoint_connection()
            assert owner_connection.in_transaction
        assert not owner_connection.in_transaction
        assert repo._teacher_checkpoint_connection() is None

        with ThreadPoolExecutor(max_workers=1) as pool:
            foreign = pool.submit(read_in_other_thread).result(timeout=5)
        assert foreign is not owner_connection

        with pytest.raises(ValueError, match="injected checkpoint error"):
            with repo._teacher_checkpoint_read(database):
                assert repo._teacher_checkpoint_connection() is owner_connection
                raise ValueError("injected checkpoint error")
        assert repo._teacher_checkpoint_connection() is None
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            owner_connection.execute("SELECT 1")

        with repo._teacher_checkpoint_read(database):
            replacement = repo._teacher_checkpoint_connection()
            assert replacement is not owner_connection
            assert repo.get_job(job.job_id).lease_id == lease.lease_id
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        replacement.execute("SELECT 1")


def test_substituted_live_lease_fails_original_fencing(active_teacher_checkpoint):
    app, job, lease = active_teacher_checkpoint
    assert app.check_active()["lease"]["lease_id"] == lease.lease_id
    replacement_id = "replacement-lease"
    path = app.repository.database_path
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("UPDATE simulation_job_leases SET lease_id=? WHERE lease_id=?",
                   (replacement_id, lease.lease_id))
        db.execute("UPDATE simulation_jobs SET lease_id=? WHERE job_id=?",
                   (replacement_id, job.job_id))
    joined = worker_owner.read_visual_worker_lease(
        app.repository, job_id=job.job_id, run_id=job.run_id, worker_id=lease.worker_id,
        lease_id=replacement_id,
    )
    assert joined.lease_id == replacement_id
    with pytest.raises(RuntimeError, match="original lease/attempt changed"):
        app.check_active()


def test_fork_cannot_use_parent_reader(active_teacher_checkpoint):
    app, job, _ = active_teacher_checkpoint
    repo = app.repository
    database = collection._live(app).checkpoint_database
    context = multiprocessing.get_context("fork")
    received, sender = context.Pipe(duplex=False)

    def child_check():
        try:
            with repo._teacher_checkpoint_read(database):
                sender.send(("accepted", repo.get_job(job.job_id).job_id))
        except RuntimeError as error:
            sender.send(("rejected", str(error)))
        finally:
            sender.close()

    with received, sender, repo._teacher_checkpoint_lifecycle(database):
        with repo._teacher_checkpoint_read(database):
            parent_connection = repo._teacher_checkpoint_connection()
        child = context.Process(target=child_check)
        child.start()
        try:
            assert received.poll(5)
            status, detail = received.recv()
            assert status == "rejected"
            assert "reader owner" in detail
            child.join(5)
            assert child.exitcode == 0
        finally:
            if child.is_alive():
                child.terminate()
                child.join(5)
        with repo._teacher_checkpoint_read(database):
            assert repo._teacher_checkpoint_connection() is parent_connection
            assert repo.get_job(job.job_id).job_id == job.job_id


@pytest.mark.parametrize("primary_body_error", [False, True])
def test_rollback_failure_discards_reader_and_preserves_primary_error(
    active_teacher_checkpoint, monkeypatch, primary_body_error,
):
    app, job, _ = active_teacher_checkpoint
    repo = app.repository
    database = collection._live(app).checkpoint_database
    actual_connect = sqlite3.connect

    class BrokenRollback(sqlite3.Connection):
        def rollback(self):
            assert self.in_transaction
            raise sqlite3.OperationalError("injected rollback failure")

    def fail_read_rollback(target, **kwargs):
        if isinstance(target, str) and target.endswith("?mode=ro"):
            kwargs["factory"] = BrokenRollback
        return actual_connect(target, **kwargs)

    expected = ValueError if primary_body_error else sqlite3.OperationalError
    reason = "primary body error" if primary_body_error else "injected rollback failure"
    with repo._teacher_checkpoint_lifecycle(database):
        with monkeypatch.context() as patch:
            patch.setattr(sqlite3, "connect", fail_read_rollback)
            with pytest.raises(expected, match=reason):
                with repo._teacher_checkpoint_read(database):
                    failed_connection = repo._teacher_checkpoint_connection()
                    repo.get_job(job.job_id)
                    if primary_body_error:
                        raise ValueError(reason)
        assert repo._teacher_checkpoint_connection() is None
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            failed_connection.execute("SELECT 1")
        with repo._teacher_checkpoint_read(database):
            assert repo.get_job(job.job_id).job_id == job.job_id
