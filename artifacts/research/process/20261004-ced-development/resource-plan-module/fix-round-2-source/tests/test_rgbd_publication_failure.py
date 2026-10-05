"""An owned success cannot survive failed terminal artifact publication."""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.test_rgbd_lease_handoff import _handoff
from tests.test_rgbd_runtime_control import _queued_closed_loop_worker


def _successful_run(worker):
    worker._run = lambda *args, **kwargs: (
        {
            "evaluation_scope": "VISION_CLOSED_LOOP",
            "success": True,
            "task_success": True,
            "task_execution": "EXECUTED",
            "executed_actions": 8,
            "online_reported_complete": True,
            "physical_success": True,
            "verification_records": [{"layer": "SKILL_RETURN", "physics_steps": 15}],
        },
        [],
        [],
    )


@pytest.mark.parametrize("persistent", [False, True])
def test_publication_error_replaces_owned_success_with_recovery_pending(tmp_path, persistent):
    repo, job, worker = _queued_closed_loop_worker(tmp_path)
    _successful_run(worker)
    original_write = worker._write_artifacts
    calls = 0

    def failed_write(*args, **kwargs):
        nonlocal calls
        calls += 1
        if persistent or calls == 1:
            raise OSError("terminal artifact disk unavailable")
        return original_write(*args, **kwargs)

    worker._write_artifacts = failed_write
    assert worker.poll_once()
    current = repo.get_job(job.job_id)
    assert current.status == "RECOVERY_PENDING"
    assert "OSError" in current.error_message
    attempt = repo.list_attempts(job.run_id)[0]
    assert attempt.result == "RECOVERY_PENDING"
    assert attempt.ended_at is not None
    assert "OSError" in attempt.error
    assert all(lease.released_at is not None for lease in repo.list_leases(job.run_id))
    assert worker.active_job_id == ""
    assert repo.acquire_lease(worker_id="next", backend="MUJOCO", lease_ttl_seconds=60) is None
    failed_event = next(
        event
        for event in repo.list_events(job.run_id)
        if event.event_type == "artifact_publication_failed"
    )
    evidence = failed_event.payload["result_evidence"]
    assert evidence["executed_actions"] == 8
    assert evidence["task_execution"] == "EXECUTED"
    assert evidence["task_success"] is False
    assert evidence["success"] is False
    assert evidence["verification_records"][0]["physics_steps"] == 15
    if persistent:
        assert current.artifact_paths == {}
        assert attempt.artifact_paths == {}
        assert calls == 2
        assert any(
            event.event_type == "artifact_recovery_write_failed"
            for event in repo.list_events(job.run_id)
        )
    else:
        result = json.loads((tmp_path / current.artifact_paths["result"]).read_text())
        recovery = json.loads((tmp_path / current.artifact_paths["recovery"]).read_text())
        consistency = json.loads(
            (tmp_path / current.artifact_paths["evidence_consistency"]).read_text()
        )
        assert result["status"] == "RECOVERY_PENDING"
        assert result["success"] is False
        assert result["task_success"] is False
        assert result["task_execution"] == "EXECUTED"
        assert result["executed_actions"] == 8
        assert "OSError" in result["error"]
        assert recovery["recovery_required"] is True
        assert consistency["consistent"] is True


def test_normal_terminal_publication_preserves_succeeded(tmp_path):
    repo, job, worker = _queued_closed_loop_worker(tmp_path)
    _successful_run(worker)
    assert worker.poll_once()
    current = repo.get_job(job.job_id)
    result = json.loads((tmp_path / current.artifact_paths["result"]).read_text())
    assert current.status == "SUCCEEDED"
    assert result["task_success"] is True
    assert not any(
        event.event_type == "artifact_publication_failed" for event in repo.list_events(job.run_id)
    )


def test_lost_owner_publication_error_cannot_downgrade_new_lease(tmp_path):
    repo, job, worker = _queued_closed_loop_worker(tmp_path)
    _successful_run(worker)
    replacement = []

    def replaced_owner(*args, **kwargs):
        # Inject the already-established recovery boundary before late I/O fails.
        with sqlite3.connect(repo.database_path) as connection:
            connection.execute(
                "UPDATE simulation_jobs SET status='INTERRUPTED' WHERE job_id=?", (job.job_id,)
            )
        replacement.append(_handoff(repo, job, worker, tmp_path))
        raise OSError("late old-owner terminal write failed")

    worker._write_artifacts = replaced_owner
    assert worker.poll_once()
    current = repo.get_job(job.job_id)
    assert current.status == "RUNNING"
    assert current.lease_id == replacement[0].lease_id
    assert current.worker_id == "new-worker"
    assert json.loads((tmp_path / job.artifact_root / "result.json").read_text()) == {
        "owner": "new-worker",
        "status": "RUNNING",
    }
    assert repo.list_attempts(job.run_id)[-1].result == "RUNNING"
    assert (
        next(
            lease
            for lease in repo.list_leases(job.run_id)
            if lease.lease_id == replacement[0].lease_id
        ).released_at
        is None
    )
