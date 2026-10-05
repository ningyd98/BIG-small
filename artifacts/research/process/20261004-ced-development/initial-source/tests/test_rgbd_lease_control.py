"""An expired, released or replaced lease cannot authorize a late model result."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker
from cloud_edge_robot_arm.vision.request_control import ModelCallCancelled, bounded_model_call


def running_job(tmp_path: Path):
    repo = SQLiteSimulationJobRepository(tmp_path / "lease.db")
    job = repo.create_job(
        run_id="run",
        batch_id="",
        backend="MUJOCO",
        scenario_id="S01_NORMAL_STATIC",
        control_mode="PCSC",
        seed=0,
        manifest_id="manifest",
        reproducibility_hash="hash",
        draft={},
        timeout_seconds=60,
        max_attempts=1,
        artifact_root="run",
        source_commit="test",
        source_tree_hash="test",
    )
    repo.update_status_cas(
        job.job_id,
        expected=RuntimeJobStatus.CREATED,
        next_status=RuntimeJobStatus.QUEUED,
        reason_code="test",
        worker_id="",
        lease_id="",
    )
    lease = repo.acquire_lease(worker_id="worker", backend="MUJOCO", lease_ttl_seconds=60)
    assert lease is not None
    for previous, current in [
        (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
        (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
    ]:
        repo.update_status_cas(
            job.job_id,
            expected=previous,
            next_status=current,
            reason_code="test",
            worker_id="worker",
            lease_id=lease.lease_id,
        )
    worker = SimulationWorker(
        worker_id="worker", backend="MUJOCO", repository=repo, artifact_root=tmp_path
    )
    return repo, repo.get_job(job.job_id), worker


def invalidate(repo, job, reason):
    if reason == "released":
        repo.release_lease(job.lease_id)
    elif reason == "interrupted":
        repo.update_status_cas(
            job.job_id,
            expected=RuntimeJobStatus.RUNNING,
            next_status=RuntimeJobStatus.INTERRUPTED,
            reason_code="test",
            worker_id="worker",
            lease_id=job.lease_id,
        )
    elif reason == "cancelled":
        repo.request_cancel(job.job_id)
    else:
        with sqlite3.connect(repo.database_path) as connection:
            if reason == "replaced":
                connection.execute(
                    "UPDATE simulation_jobs SET lease_id='another' WHERE job_id=?", (job.job_id,)
                )
            else:
                expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
                connection.execute(
                    "UPDATE simulation_jobs SET lease_expires_at=? WHERE job_id=?",
                    (expired, job.job_id),
                )
                connection.execute(
                    "UPDATE simulation_job_leases SET expires_at=? WHERE lease_id=?",
                    (expired, job.lease_id),
                )


@pytest.mark.parametrize("reason", ["released", "interrupted", "expired", "replaced", "cancelled"])
def test_revoked_lease_discards_late_model_response(tmp_path: Path, reason: str) -> None:
    repo, job, worker = running_job(tmp_path)
    assert not worker._active_job_cancelled(job)
    dispatched = []

    def model_response():
        invalidate(repo, job, reason)
        return "late action"

    with pytest.raises(ModelCallCancelled):
        dispatched.append(
            bounded_model_call(
                model_response,
                timeout_s=1,
                resource_key=f"lease-{reason}",
                cancelled=lambda: worker._active_job_cancelled(job),
            )
        )
    assert dispatched == []


@pytest.mark.parametrize("reason", ["released", "interrupted", "expired", "replaced", "cancelled"])
def test_heartbeat_cannot_revive_inactive_lease(tmp_path: Path, reason: str) -> None:
    repo, job, _ = running_job(tmp_path)
    invalidate(repo, job, reason)
    before = repo.list_leases(job.run_id)[0]
    with pytest.raises(RuntimeError, match="lease"):
        repo.heartbeat_lease(job.lease_id, lease_ttl_seconds=120)
    after = repo.list_leases(job.run_id)[0]
    assert after.expires_at == before.expires_at
    assert after.heartbeat_at == before.heartbeat_at


def test_heartbeat_extends_only_current_live_lease(tmp_path: Path) -> None:
    repo, job, worker = running_job(tmp_path)
    before = repo.list_leases(job.run_id)[0]
    repo.heartbeat_lease(job.lease_id, lease_ttl_seconds=120)
    after = repo.list_leases(job.run_id)[0]
    assert after.expires_at > before.expires_at
    assert repo.get_job(job.job_id).lease_expires_at == after.expires_at
    assert not worker._active_job_cancelled(job)
    worker._heartbeat_failed.set()
    assert worker._active_job_cancelled(job)
