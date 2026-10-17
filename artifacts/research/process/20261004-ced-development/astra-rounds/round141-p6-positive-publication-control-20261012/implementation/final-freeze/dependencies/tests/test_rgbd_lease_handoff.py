"""A stale worker may close only its own attempt after a recovered lease handoff."""

from __future__ import annotations

import json

import pytest

from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.worker import CancelledByOperator, TimedOut
from tests.test_rgbd_runtime_control import _queued_closed_loop_worker


def _handoff(repo, job, worker, tmp_path):
    current = repo.get_job(job.job_id)
    if current.status == RuntimeJobStatus.RUNNING:
        repo.update_status_cas(
            current.job_id,
            expected=RuntimeJobStatus.RUNNING,
            next_status=RuntimeJobStatus.INTERRUPTED,
            reason_code="lease_lost",
            worker_id=worker.worker_id,
            lease_id=current.lease_id,
        )
    for previous, next_status in [
        (RuntimeJobStatus.INTERRUPTED, RuntimeJobStatus.RECOVERY_PENDING),
        (RuntimeJobStatus.RECOVERY_PENDING, RuntimeJobStatus.QUEUED),
    ]:
        repo.update_status_cas(
            job.job_id,
            expected=previous,
            next_status=next_status,
            reason_code="recovery",
            worker_id="",
            lease_id="",
        )
    lease = repo.acquire_lease(worker_id="new-worker", backend="MUJOCO", lease_ttl_seconds=60)
    assert lease is not None
    repo.start_attempt(job.job_id, worker_id="new-worker")
    for previous, next_status in [
        (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
        (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
    ]:
        repo.update_status_cas(
            job.job_id,
            expected=previous,
            next_status=next_status,
            reason_code="new_owner",
            worker_id="new-worker",
            lease_id=lease.lease_id,
        )
    directory = tmp_path / job.artifact_root
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "result.json").write_text(json.dumps({"owner": "new-worker", "status": "RUNNING"}))
    (directory / "metrics.json").write_text('[{"owner":"new-worker"}]')
    repo.save_metrics(job.job_id, [{"owner": "new-worker"}])
    repo.save_artifacts(
        job.job_id,
        {
            "result": f"{job.artifact_root}/result.json",
            "metrics": f"{job.artifact_root}/metrics.json",
        },
    )
    return lease


@pytest.mark.parametrize("failure", [ValueError, TimedOut, CancelledByOperator])
@pytest.mark.parametrize("handoff_when", ["during_run", "after_settlement", "before_cas"])
def test_old_worker_does_not_release_or_overwrite_new_owner(
    tmp_path,
    failure,
    handoff_when,
):
    repo, job, old_worker = _queued_closed_loop_worker(tmp_path)
    old_lease_id = []
    new_lease = []
    original_settle = old_worker._settle_failure_status
    original_cas = repo.update_status_cas
    injecting_handoff = False

    def run(current, **kwargs):
        old_lease_id.append(current.lease_id)
        if handoff_when == "during_run":
            new_lease.append(_handoff(repo, job, old_worker, tmp_path))
        elif handoff_when == "after_settlement":
            repo.update_status_cas(
                job.job_id,
                expected=RuntimeJobStatus.RUNNING,
                next_status=RuntimeJobStatus.INTERRUPTED,
                reason_code="lease_lost",
                worker_id=old_worker.worker_id,
                lease_id=current.lease_id,
            )
        raise failure("old execution finished late")

    def settle(*args, **kwargs):
        result = original_settle(*args, **kwargs)
        if handoff_when == "after_settlement":
            new_lease.append(_handoff(repo, job, old_worker, tmp_path))
        return result

    def cas(*args, **kwargs):
        nonlocal injecting_handoff
        if (
            handoff_when == "before_cas"
            and not injecting_handoff
            and kwargs.get("expected") == RuntimeJobStatus.RUNNING
            and kwargs.get("worker_id") == old_worker.worker_id
        ):
            injecting_handoff = True
            new_lease.append(_handoff(repo, job, old_worker, tmp_path))
        return original_cas(*args, **kwargs)

    old_worker._run = run
    old_worker._settle_failure_status = settle
    repo.update_status_cas = cas
    assert old_worker.poll_once()
    current = repo.get_job(job.job_id)
    lease = next(
        item for item in repo.list_leases(job.run_id) if item.lease_id == new_lease[0].lease_id
    )
    assert lease.released_at is None
    assert current.status == RuntimeJobStatus.RUNNING
    assert current.lease_id == lease.lease_id
    assert current.worker_id == "new-worker"
    assert repo.get_metrics(job.run_id) == [{"owner": "new-worker"}]
    assert repo.get_artifacts(job.run_id) == {
        "result": f"{job.artifact_root}/result.json",
        "metrics": f"{job.artifact_root}/metrics.json",
    }
    directory = tmp_path / job.artifact_root
    assert json.loads((directory / "result.json").read_text()) == {
        "owner": "new-worker",
        "status": "RUNNING",
    }
    assert json.loads((directory / "metrics.json").read_text()) == [{"owner": "new-worker"}]
    attempts = repo.list_attempts(job.run_id)
    assert attempts[0].result == "INTERRUPTED"
    assert attempts[0].ended_at is not None
    assert attempts[1].result == "RUNNING"
    assert attempts[1].ended_at is None
    assert any(
        event.event_type == "stale_worker_result_discarded"
        and event.payload["lease_id"] == old_lease_id[0]
        and event.payload["attempt"] == 1
        for event in repo.list_events(job.run_id)
    )


def _competing_guard_process(database, queue):
    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )

    repo = SQLiteSimulationJobRepository(database)
    queue.put("waiting")
    with repo.publication_guard():
        queue.put("acquired")


def test_publication_guard_is_cross_process_and_repository_reentrant(tmp_path):
    import multiprocessing
    from queue import Empty

    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )

    database = tmp_path / "guard.db"
    first = SQLiteSimulationJobRepository(database)
    second = SQLiteSimulationJobRepository(database)
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=_competing_guard_process, args=(database, queue))
    try:
        with first.publication_guard(), second.publication_guard():
            process.start()
            assert queue.get(timeout=5) == "waiting"
            with pytest.raises(Empty):
                queue.get(timeout=0.1)
        assert queue.get(timeout=5) == "acquired"
        process.join(timeout=5)
        assert process.exitcode == 0
    finally:
        if process.pid is not None and process.is_alive():
            process.terminate()
            process.join(timeout=5)
        queue.close()


def test_new_owner_waits_until_old_terminal_publication_finishes(tmp_path):
    import threading

    from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
        SQLiteSimulationJobRepository,
    )

    repo, job, old_worker = _queued_closed_loop_worker(tmp_path)
    competing = SQLiteSimulationJobRepository(repo.database_path)
    started = threading.Event()
    completed = threading.Event()
    thread_errors = []
    contender = None
    original_save = repo.save_metrics

    def run(current, **kwargs):
        repo.update_status_cas(
            job.job_id,
            expected=RuntimeJobStatus.RUNNING,
            next_status=RuntimeJobStatus.INTERRUPTED,
            reason_code="lease_lost",
            worker_id=old_worker.worker_id,
            lease_id=current.lease_id,
        )
        raise ValueError("old task interrupted")

    def take_over():
        started.set()
        try:
            _handoff(competing, job, old_worker, tmp_path)
        except BaseException as exc:
            thread_errors.append(exc)
        finally:
            completed.set()

    def save_metrics(*args, **kwargs):
        nonlocal contender
        contender = threading.Thread(target=take_over)
        contender.start()
        assert started.wait(5)
        # The contender has an explicit start barrier; it must remain unable to
        # change ownership while shared evidence is being published.
        assert not completed.wait(0.1)
        return original_save(*args, **kwargs)

    old_worker._run = run
    repo.save_metrics = save_metrics
    try:
        assert old_worker.poll_once()
    finally:
        if contender is not None:
            contender.join(timeout=5)
    assert completed.is_set()
    assert not thread_errors
    assert repo.get_job(job.job_id).worker_id == "new-worker"
    assert repo.get_metrics(job.run_id) == [{"owner": "new-worker"}]
    assert json.loads((tmp_path / job.artifact_root / "result.json").read_text()) == {
        "owner": "new-worker",
        "status": "RUNNING",
    }


def test_stale_worker_start_cannot_create_attempt_or_replace_new_owner(tmp_path):
    repo, job, old_worker = _queued_closed_loop_worker(tmp_path)
    old_lease = repo.acquire_lease(
        worker_id=old_worker.worker_id,
        backend="MUJOCO",
        lease_ttl_seconds=60,
    )
    assert old_lease is not None
    repo.start_attempt(job.job_id, worker_id=old_worker.worker_id)
    for previous, following in [
        (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
        (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
    ]:
        repo.update_status_cas(
            job.job_id,
            expected=previous,
            next_status=following,
            reason_code="test",
            worker_id=old_worker.worker_id,
            lease_id=old_lease.lease_id,
        )
    new_lease = _handoff(repo, job, old_worker, tmp_path)
    old_worker._execute(job.job_id, old_lease.lease_id)
    current = repo.get_job(job.job_id)
    assert current.worker_id == "new-worker"
    assert current.lease_id == new_lease.lease_id
    assert current.status == RuntimeJobStatus.RUNNING
    assert len(repo.list_attempts(job.run_id)) == 2


def _cpu_visual_worker(monkeypatch, tmp_path, episode, *, instruction=None):
    """Keep the worker/SQLite/files real; replace only GPU and episode work."""
    from contextlib import nullcontext
    from types import SimpleNamespace

    from cloud_edge_robot_arm.vision.planner import RGBDPlannerAdapter
    from tests.test_phase11_1_simulation_runtime import _draft

    draft = _draft(backend="MUJOCO", input_mode="RGBD", execution_scope="VISION_CLOSED_LOOP")
    if instruction is not None:
        draft["user_instruction"] = instruction
    repo, job, worker = _queued_closed_loop_worker(tmp_path, draft)
    backend = SimpleNamespace(
        initialize=lambda config: None,
        reset=lambda scenario: None,
        step=lambda **kwargs: None,
        shutdown=lambda: None,
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.simulation.mujoco.backend.MuJoCoPhysicsBackend", lambda: backend
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.simulation.mujoco.skill_robot.MuJoCoSkillRobot",
        lambda backend: object(),
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.vision.capture.MuJoCoCaptureSession",
        lambda *args, **kwargs: nullcontext(object()),
    )
    monkeypatch.setattr("cloud_edge_robot_arm.vision.execution.run_visual_episode", episode)
    planner = RGBDPlannerAdapter()
    planner.model_snapshot = SimpleNamespace(
        weight_digest="a" * 64,
        grasp_profile="mujoco_upright_box_v1",
        digest=lambda: "b" * 64,
    )
    worker.planner_factory = lambda: planner
    return repo, job, worker


def _successful_visual_episode():
    from cloud_edge_robot_arm.vision.evaluation import VisualEpisodeOutcome

    return VisualEpisodeOutcome(
        success=True,
        status="SUCCESS",
        safety_violation=False,
        failure_reason=None,
        measured_lift_m=0.1,
        hold_s=0.6,
        placed_stable_s=1.0,
        elapsed_s=5.0,
        online_reported_complete=True,
        physical_success=True,
        executed_actions=8,
    )


def test_late_episode_frame_write_cannot_overwrite_new_lease_frames(monkeypatch, tmp_path):
    import time

    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker
    from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft

    outputs = []
    new_lease = []

    def episode(planner, robot, capture, policy):
        directory = policy.output_dir
        outputs.append(directory)
        frame = directory / "frames" / "0001" / "rgb.png"
        frame.parent.mkdir(parents=True, exist_ok=True)
        if len(outputs) == 1:
            frame.write_bytes(b"old-first-frame")
            new_lease.append(_handoff(repo, job, old_worker, tmp_path))
            new_worker = SimulationWorker(
                worker_id="new-worker",
                backend="MUJOCO",
                repository=repo,
                artifact_root=tmp_path,
                planner_factory=old_worker.planner_factory,
            )
            current = repo.get_job(job.job_id)
            new_worker._run_visual_closed_loop(
                current,
                ExperimentDraft.model_validate(current.draft),
                start_monotonic=time.monotonic(),
            )
            # A finally block may still flush its own frame after ownership has moved.
            frame.write_bytes(b"late-old-frame")
            (directory / "episode.json").write_text('{"owner":"old"}')
            raise CancelledByOperator("lease lost during physics")
        frame.write_bytes(b"new-frame")
        (directory / "episode.json").write_text('{"owner":"new"}')
        return _successful_visual_episode()

    repo, job, old_worker = _cpu_visual_worker(monkeypatch, tmp_path, episode)
    assert old_worker.poll_once()
    assert len(outputs) == 2
    assert (outputs[1] / "frames/0001/rgb.png").read_bytes() == b"new-frame"
    assert json.loads((outputs[1] / "episode.json").read_text()) == {"owner": "new"}
    assert outputs[0] != outputs[1]
    assert repo.get_job(job.job_id).lease_id == new_lease[0].lease_id
    current = repo.get_job(job.job_id)
    published = old_worker._artifact_paths(current)
    assert published["visual_episode"] == str((outputs[1] / "episode.json").relative_to(tmp_path))
    assert not (tmp_path / job.artifact_root / "visual_episode").exists()


@pytest.mark.parametrize("scope", ["CAPTURE_ONLY", "VISUAL_PLANNING"])
def test_capture_and_plan_publish_only_current_lease_artifacts(monkeypatch, tmp_path, scope):
    from types import SimpleNamespace

    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from tests.test_phase11_1_simulation_runtime import _draft
    from tests.test_rgbd_observations import observation_payload

    repo, job, worker = _queued_closed_loop_worker(
        tmp_path, _draft(backend="MUJOCO", input_mode="RGBD", execution_scope=scope)
    )
    run_dir = tmp_path / job.artifact_root
    run_dir.mkdir(parents=True)
    (run_dir / "rgb.png").write_bytes(b"historical-frame")
    (run_dir / "visual_episode").mkdir()
    (run_dir / "visual_episode/episode.json").write_text('{"owner":"historical"}')
    monkeypatch.setattr(
        "cloud_edge_robot_arm.vision.capture.capture_simulated_observation",
        lambda **kwargs: RGBDObservation.model_validate(observation_payload()),
    )
    worker.planner_factory = lambda: object()
    monkeypatch.setattr(
        "cloud_edge_robot_arm.cloud.planning.pipeline.PlanningPipeline.process",
        lambda *args: SimpleNamespace(
            outcome="REJECTED",
            reason="fixture rejection",
            model_dump=lambda **kwargs: {"outcome": "REJECTED"},
        ),
    )
    assert worker.poll_once()
    current = repo.get_job(job.job_id)
    assert (run_dir / "rgb.png").read_bytes() == b"historical-frame"
    prefix = f"{job.artifact_root}/rgbd-attempts/{current.lease_id}/"
    assert current.artifact_paths["rgb"] == prefix + "rgb.png"
    assert current.artifact_paths["observation"] == prefix + "observation.json"
    assert "visual_episode" not in current.artifact_paths
    if scope == "VISUAL_PLANNING":
        assert current.artifact_paths["visual_plan"] == prefix + "visual_plan.json"


def test_unleased_historical_job_retains_original_artifact_paths(tmp_path):
    repo, job, worker = _queued_closed_loop_worker(tmp_path)
    directory = tmp_path / job.artifact_root / "visual_episode"
    directory.mkdir(parents=True)
    (directory / "episode.json").write_text("{}")
    assert not job.lease_id
    assert worker._artifact_paths(job)["visual_episode"] == (
        f"{job.artifact_root}/visual_episode/episode.json"
    )


@pytest.mark.parametrize("color,want_success", [("red", True), ("purple", False)])
def test_worker_conjoins_terminal_semantics_without_overwriting_task_result(
    monkeypatch, tmp_path, color, want_success
):
    instruction = f"Move the {color} block to the green region."
    repo, job, worker = _cpu_visual_worker(
        monkeypatch, tmp_path, lambda *args: _successful_visual_episode(), instruction=instruction
    )
    assert worker.poll_once()
    current = repo.get_job(job.job_id)
    result = json.loads((tmp_path / current.artifact_paths["result"]).read_text())
    assert result["task_success"] is want_success
    assert result["success"] is want_success
    assert result["visual_episode_success"] is True
    assert result["online_reported_complete"] is True
    assert result["physical_success"] is True
    assert result["semantic_success"] is want_success
    assert result["semantic_used_for_online_routing"] is False
    assert current.status == ("SUCCEEDED" if want_success else "FAILED")


def test_expiry_scan_cannot_interrupt_a_replacement_lease(tmp_path):
    from tests.test_rgbd_lease_control import invalidate, running_job

    repo, job, worker = running_job(tmp_path)
    invalidate(repo, job, "expired")
    original_cas = repo.update_status_cas
    replacement = []

    def race(*args, **kwargs):
        if kwargs.get("reason_code") == "lease_expired" and not replacement:
            replacement.append(_handoff(repo, job, worker, tmp_path))
        return original_cas(*args, **kwargs)

    repo.update_status_cas = race
    assert repo.expire_leases() == []
    current = repo.get_job(job.job_id)
    assert current.status == "RUNNING"
    assert current.lease_id == replacement[0].lease_id
    assert current.worker_id == "new-worker"


def test_expiry_scan_rechecks_current_expiration_in_atomic_update(tmp_path):
    import sqlite3
    from datetime import UTC, datetime, timedelta

    from tests.test_rgbd_lease_control import invalidate, running_job

    repo, job, _ = running_job(tmp_path)
    invalidate(repo, job, "expired")
    original_cas = repo.update_status_cas

    def refresh_before_cas(*args, **kwargs):
        if kwargs.get("reason_code") == "lease_expired":
            # Model a heartbeat committed after the scan snapshot, before expiry CAS.
            future = (datetime.now(UTC) + timedelta(seconds=60)).isoformat()
            with sqlite3.connect(repo.database_path) as connection:
                connection.execute(
                    "UPDATE simulation_jobs SET lease_expires_at=? WHERE job_id=?",
                    (future, job.job_id),
                )
                connection.execute(
                    "UPDATE simulation_job_leases SET expires_at=? WHERE lease_id=?",
                    (future, job.lease_id),
                )
        return original_cas(*args, **kwargs)

    repo.update_status_cas = refresh_before_cas
    assert repo.expire_leases() == []
    assert repo.get_job(job.job_id).status == "RUNNING"


def test_cancel_racing_handoff_cancels_current_job_without_restoring_old_owner(tmp_path):
    from tests.test_rgbd_lease_control import running_job

    repo, job, worker = running_job(tmp_path)
    original_cas = repo.update_status_cas
    replacement = []

    def race(*args, **kwargs):
        if kwargs.get("reason_code") == "operator_cancel" and not replacement:
            replacement.append(_handoff(repo, job, worker, tmp_path))
        return original_cas(*args, **kwargs)

    repo.update_status_cas = race
    returned = repo.request_cancel(job.job_id)
    current = repo.get_job(job.job_id)
    assert returned == current
    assert current.status == "CANCEL_REQUESTED"
    assert current.cancel_requested
    assert current.lease_id == replacement[0].lease_id
    assert current.worker_id == "new-worker"


def test_recovery_scan_cannot_finish_new_owner_attempt(tmp_path):
    from cloud_edge_robot_arm.simulation_runtime.recovery import ArtifactRecoveryService
    from tests.test_rgbd_lease_control import invalidate, running_job

    repo, job, worker = running_job(tmp_path)
    invalidate(repo, job, "interrupted")
    original_find = repo.find_recoverable_jobs

    def race():
        snapshot = original_find()
        _handoff(repo, job, worker, tmp_path)
        return snapshot

    repo.find_recoverable_jobs = race
    ArtifactRecoveryService(repository=repo, artifact_root=tmp_path).recover_interrupted_jobs()
    current = repo.get_job(job.job_id)
    assert current.status == "RUNNING"
    assert current.worker_id == "new-worker"
    attempts = repo.list_attempts(job.run_id)
    assert attempts[-1].ended_at is None
    assert attempts[-1].result == "RUNNING"


def test_stale_retry_snapshot_cannot_requeue_new_owner(tmp_path):
    from tests.test_rgbd_lease_control import invalidate, running_job

    repo, job, worker = running_job(tmp_path)
    invalidate(repo, job, "interrupted")
    original_get = repo.get_job
    injected = False

    def race(job_id):
        nonlocal injected
        snapshot = original_get(job_id)
        if not injected:
            injected = True
            _handoff(repo, job, worker, tmp_path)
        return snapshot

    repo.get_job = race
    with pytest.raises(ValueError, match="job_not_retryable"):
        repo.retry_job(job.job_id)
    current = original_get(job.job_id)
    assert current.status == "RUNNING"
    assert current.worker_id == "new-worker"


def test_expired_starting_lease_can_be_interrupted(tmp_path):
    import sqlite3

    from tests.test_rgbd_lease_control import invalidate, running_job

    repo, job, _ = running_job(tmp_path)
    with sqlite3.connect(repo.database_path) as connection:
        connection.execute(
            "UPDATE simulation_jobs SET status='STARTING' WHERE job_id=?", (job.job_id,)
        )
    invalidate(repo, job, "expired")
    assert repo.expire_leases() == [job.job_id]
    assert repo.get_job(job.job_id).status == "INTERRUPTED"


def test_cancel_before_episode_flush_publishes_current_lease_budget_checkpoint(tmp_path):
    repo, job, worker = _queued_closed_loop_worker(tmp_path)

    def run(current, **kwargs):
        path = (
            tmp_path
            / current.artifact_root
            / "rgbd-attempts"
            / current.lease_id
            / "visual_episode"
            / "verification-state.json"
        )
        path.parent.mkdir(parents=True)
        path.write_text('{"reobservations_used":2}')
        repo.request_cancel(current.job_id)
        raise CancelledByOperator("cancel before final episode write")

    worker._run = run
    assert worker.poll_once()
    current = repo.get_job(job.job_id)
    checkpoint = tmp_path / current.artifact_paths["verification_state"]
    assert json.loads(checkpoint.read_text()) == {"reobservations_used": 2}
    assert "visual_episode" not in current.artifact_paths
    assert current.status == "CANCELLED"
