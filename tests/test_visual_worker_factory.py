"""Software-only worker factory checks; no provider, rendered frame or action."""

from dataclasses import replace
from pathlib import Path

import pytest

from cloud_edge_robot_arm.repositories.event_autonomy import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.simulation_runtime.in_memory_repository import (
    InMemorySimulationJobRepository,
)
from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker


def make_worker(tmp_path: Path, **kwargs):
    return SimulationWorker(
        worker_id="factory-software-worker",
        backend="MUJOCO",
        repository=InMemorySimulationJobRepository(),
        artifact_root=tmp_path,
        **kwargs,
    )


def test_unconfigured_worker_preserves_legacy_default(tmp_path):
    worker = make_worker(tmp_path)
    assert worker.visual_role_binding is None
    assert worker.visual_event_repository is None
    assert worker.visual_robot_id is None


@pytest.mark.parametrize(
    "config",
    [
        {"visual_robot_id": "simulation-arm-1"},
        {"visual_event_repository": InMemoryEventAutonomyRepository()},
        {"visual_role_binding": object()},
    ],
)
def test_incomplete_opencv_configuration_rejects_before_execution(tmp_path, config):
    with pytest.raises(ValueError, match="together"):
        make_worker(tmp_path, **config)


@pytest.mark.parametrize("robot_id", ["", "unknown", "robot-unknown", "../arm", True])
def test_explicit_robot_id_rejects_placeholders(tmp_path, robot_id):
    from tests.test_ced_runtime_binding import role_binding

    source_root = tmp_path / "source"
    source_root.mkdir()
    _, binding = role_binding(source_root)
    with pytest.raises(ValueError):
        make_worker(
            tmp_path,
            visual_role_binding=binding,
            visual_event_repository=InMemoryEventAutonomyRepository(),
            visual_robot_id=robot_id,
        )


def software_factory(
    monkeypatch, tmp_path, *, during_initialize=None, during_settle=None, during_episode=None
):
    """Keep the real job lease/attempt/SQLite; replace physical APIs and episode only."""
    from contextlib import contextmanager, nullcontext
    from types import SimpleNamespace

    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.repositories.event_autonomy import SQLiteEventAutonomyRepository
    from cloud_edge_robot_arm.simulation_runtime.worker import VISUAL_WORKER_FACTORY_SOURCE_PATHS
    from cloud_edge_robot_arm.vision.evaluation import VisualEpisodeOutcome
    from cloud_edge_robot_arm.vision.raw_recorder_v3 import RECORDER_SOURCE_PATHS
    from cloud_edge_robot_arm.vision.role_models import cloud_request_settings, configuration_hash
    from cloud_edge_robot_arm.vision.worker_runtime import REQUIRED_WORKER_RUNTIME_SOURCES
    from tests.test_ced_runtime_binding import role_binding
    from tests.test_rgbd_lease_handoff import _cpu_visual_worker

    source_root = tmp_path / "source"
    source_root.mkdir()
    planner, binding = role_binding(source_root)
    planner.model_snapshot = replace(
        planner.model_snapshot,
        grasp_profile="mujoco_upright_box_v2",
    )
    cloud_snapshot = replace(
        binding.bundle.cloud_snapshot,
        request_config_hash=configuration_hash(cloud_request_settings(planner)),
    )
    planner.role_snapshot = cloud_snapshot
    binding = replace(
        binding,
        bundle=replace(binding.bundle, cloud_snapshot=cloud_snapshot),
        edge_policy=binding.evidence()["edge_policy"],
    )
    root = Path(__file__).resolve().parents[1]
    for name in (
        REQUIRED_WORKER_RUNTIME_SOURCES | VISUAL_WORKER_FACTORY_SOURCE_PATHS | RECORDER_SOURCE_PATHS
    ):
        target = source_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / name).read_bytes())
    calls = []
    received = []
    backend = SimpleNamespace(_episode_id=None)

    def initialize(config):
        calls.append("initialize")
        if during_initialize:
            during_initialize(worker, repo, job, source_root)

    def reset(scenario):
        calls.append("reset")
        backend._episode_id = "software-shared-backend-episode"

    def settle(**kwargs):
        calls.append("settle")
        if during_settle:
            during_settle(worker, repo, job, source_root)

    backend.initialize = initialize
    backend.reset = reset
    backend.step = settle
    backend.shutdown = lambda: calls.append("shutdown")
    robot = SimpleNamespace(_backend=backend, get_state=lambda: RobotState(connected=True))
    capture = SimpleNamespace(_backend=backend, _owns_backend=False)

    class SoftwareRecorder:
        """Factory protocol probe; produces no raw evidence or completeness claim."""

        def __init__(self, actual_backend, actual_capture, executor, **config):
            self.backend, self.capture_session, self.executor = (
                actual_backend,
                actual_capture,
                executor,
            )
            self.directory = config["directory"]
            self.source_hashes = config["source_hashes"]

        def __enter__(self):
            calls.append("raw_enter")
            return self

        def __exit__(self, *args):
            calls.append("raw_exit")

        @contextmanager
        def purpose(self, kind):
            calls.append(f"purpose_begin:{kind}")
            try:
                yield
            finally:
                calls.append(f"purpose_end:{kind}")

    def episode(actual_planner, actual_robot, actual_capture, policy):
        calls.append("episode")
        received.append((actual_planner, actual_robot, actual_capture, policy))
        if during_episode:
            during_episode(worker, repo, job, source_root)
        return VisualEpisodeOutcome(
            success=False,
            status="FAILED",
            safety_violation=False,
            failure_reason="SOFTWARE_FACTORY_ONLY",
            measured_lift_m=0.0,
            hold_s=0.0,
            placed_stable_s=0.0,
            elapsed_s=0.0,
            terminal_reason="SOFTWARE_FACTORY_ONLY",
            episode_id=backend._episode_id,
        )

    repo, job, _ = _cpu_visual_worker(monkeypatch, tmp_path, episode)
    event_repository = SQLiteEventAutonomyRepository(tmp_path / "events.db")
    worker = SimulationWorker(
        worker_id="worker",
        backend="MUJOCO",
        repository=repo,
        artifact_root=tmp_path,
        planner_factory=lambda: planner,
        visual_role_binding=binding,
        visual_event_repository=event_repository,
        visual_robot_id="software-simulation-arm",
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.simulation.mujoco.backend.MuJoCoPhysicsBackend", lambda: backend
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.simulation.mujoco.skill_robot.MuJoCoSkillRobot", lambda _: robot
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.vision.capture.MuJoCoCaptureSession",
        lambda *args, **kwargs: nullcontext(capture),
    )
    monkeypatch.setattr(
        "cloud_edge_robot_arm.vision.raw_recorder_v3.VisualRawRecorderV3", SoftwareRecorder
    )
    return repo, job, worker, calls, received, backend, event_repository


def test_factory_passes_real_running_lease_attempt_and_original_clock(monkeypatch, tmp_path):
    from dataclasses import asdict
    from datetime import UTC, datetime

    repo, job, worker, calls, received, backend, events = software_factory(monkeypatch, tmp_path)
    before = datetime.now(UTC)
    assert worker.poll_once()
    assert calls == [
        "initialize",
        "raw_enter",
        "reset",
        "purpose_begin:SETTLE",
        "settle",
        "purpose_end:SETTLE",
        "episode",
        "raw_exit",
        "shutdown",
    ], repo.get_job(job.job_id).error_message
    planner, robot, capture, policy = received[0]
    assert policy.device_pipeline == "OPENCV"
    assert policy.role_binding is worker.visual_role_binding
    runtime = policy.worker_runtime
    assert runtime is not None
    source = runtime.source
    assert source.job_repository is repo
    assert source.event_repository is events
    assert source.job_id == job.job_id
    assert source.run_id == job.run_id
    assert source.worker_id == worker.worker_id
    assert source.lease_id == repo.list_leases(job.run_id)[0].lease_id
    assert source.robot_id == "software-simulation-arm"
    assert before <= source.task_started_at <= datetime.now(UTC)
    assert source.task_timeout_s == job.timeout_seconds
    assert policy.timeout_s <= source.task_timeout_s
    assert (
        runtime.bootstrap.task_deadline_at - source.task_started_at
    ).total_seconds() == source.task_timeout_s
    assert runtime.bootstrap.verification_state.deadline_at <= runtime.bootstrap.task_deadline_at
    assert runtime.bootstrap.definition.episode_id == backend._episode_id
    assert runtime.bootstrap.definition.lease.attempt == 1
    assert repo.list_attempts(job.run_id)[0].attempt == 1
    assert robot._backend is capture._backend is backend
    assert policy.raw_recorder.backend is backend
    assert policy.raw_recorder.capture_session is capture
    assert policy.raw_recorder.executor._robot is robot
    assert policy.raw_recorder.directory.name == "raw_episode_v3"
    assert dict(policy.raw_recorder.source_hashes) == dict(runtime.source.source_hashes)
    assert asdict(policy.verification_budget) == dict(
        worker.visual_role_binding.edge_policy["verification_budget"]
    )
    assert not hasattr(source, "execution_admitted")
    assert not hasattr(runtime, "execution_admitted")


@pytest.mark.parametrize("boundary", ["initialize", "settle"])
def test_lease_cancel_during_setup_stops_before_episode(monkeypatch, tmp_path, boundary):
    def cancel(worker, repo, job, source_root):
        repo.request_cancel(job.job_id)

    params = {f"during_{boundary}": cancel}
    repo, job, worker, calls, received, _, _ = software_factory(monkeypatch, tmp_path, **params)
    assert worker.poll_once()
    assert "episode" not in calls
    assert calls[-1] == "shutdown"
    assert received == []
    assert repo.get_job(job.job_id).status == "CANCELLED"


def test_runtime_source_drift_after_initialize_stops_before_reset(monkeypatch, tmp_path):
    def rewrite(worker, repo, job, source_root):
        path = source_root / "src/cloud_edge_robot_arm/vision/worker_runtime.py"
        path.write_text("# changed during initializer\n")

    repo, job, worker, calls, received, _, _ = software_factory(
        monkeypatch, tmp_path, during_initialize=rewrite
    )
    assert worker.poll_once()
    assert calls == ["initialize", "shutdown"]
    assert received == []
    assert repo.get_job(job.job_id).status != "SUCCEEDED"


def test_direct_opencv_entry_cannot_invent_a_worker_task_clock(monkeypatch, tmp_path):
    import time

    from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
    from cloud_edge_robot_arm.simulation_workbench.models import ExperimentDraft

    repo, job, worker, calls, received, _, _ = software_factory(monkeypatch, tmp_path)
    lease = repo.acquire_lease(worker_id=worker.worker_id, backend="MUJOCO", lease_ttl_seconds=60)
    assert lease is not None
    repo.start_attempt(job.job_id, worker_id=worker.worker_id)
    for old, new in (
        (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
        (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
    ):
        repo.update_status_cas(
            job.job_id,
            expected=old,
            next_status=new,
            reason_code="software-factory-only",
            worker_id=worker.worker_id,
            lease_id=lease.lease_id,
        )
    current = repo.get_job(job.job_id)
    with pytest.raises(ValueError, match="worker task clock"):
        worker._run_visual_closed_loop(
            current, ExperimentDraft.model_validate(job.draft), start_monotonic=time.monotonic()
        )
    assert calls == []
    assert received == []


def test_source_drift_during_episode_rejects_returned_result(monkeypatch, tmp_path):
    def rewrite(worker, repo, job, source_root):
        path = source_root / "src/cloud_edge_robot_arm/vision/worker_runtime.py"
        path.write_text("# changed before episode returned\n")

    repo, job, worker, calls, received, _, _ = software_factory(
        monkeypatch, tmp_path, during_episode=rewrite
    )
    assert worker.poll_once()
    current = repo.get_job(job.job_id)
    assert "episode" in calls
    assert len(received) == 1
    assert current.status == "FAILED"
    assert "registered source" in current.error_message


def persist_original_runtime_parameters(repo, job, parameters):
    """Set the actual queued SQLite source before any lease/runtime is acquired."""
    import json

    draft = {**job.draft, "parameter_overrides": parameters}
    with repo._connect() as connection:
        connection.execute(
            "UPDATE simulation_jobs SET draft_json = ? WHERE job_id = ? AND status = 'QUEUED'",
            (json.dumps(draft), job.job_id),
        )


@pytest.mark.parametrize(
    "parameters,expected_period,expected_waits",
    [
        ({"supervision_period_ms": 500, "advance_physics_during_wait": True}, 0.5, True),
        ({"supervision_period_ms": 2000, "advance_physics_during_wait": False}, 2.0, False),
        ({"supervision_period_ms": 1250.5, "advance_physics_during_wait": True}, 1.2505, True),
        ({"advance_physics_during_wait": True}, None, True),
        ({}, None, False),
    ],
)
def test_factory_preserves_explicit_original_supervision_and_wait_parameters(
    monkeypatch, tmp_path, parameters, expected_period, expected_waits
):
    repo, job, worker, calls, received, backend, _ = software_factory(monkeypatch, tmp_path)
    persist_original_runtime_parameters(repo, job, parameters)
    assert worker.poll_once()
    assert len(received) == 1, repo.get_job(job.job_id).error_message
    _, robot, capture, policy = received[0]
    assert policy.supervision_period_s == expected_period
    assert policy.advance_physics_during_wait is expected_waits
    runtime = policy.worker_runtime
    original = repo.get_job(job.job_id).draft["parameter_overrides"]
    assert original == parameters
    assert policy.timeout_s <= runtime.source.task_timeout_s == job.timeout_seconds
    assert robot._backend is capture._backend is backend
    assert policy.raw_recorder.executor._robot is robot
    assert calls.count("episode") == 1
    assert repo.list_attempts(job.run_id)[0].attempt == runtime.bootstrap.definition.lease.attempt


@pytest.mark.parametrize(
    "parameters",
    [
        {"supervision_period_ms": True},
        {"supervision_period_ms": "500"},
        {"supervision_period_ms": 0},
        {"supervision_period_ms": -500},
        {"supervision_period_ms": float("inf")},
        {"supervision_period_ms": float("nan")},
        {"advance_physics_during_wait": "true"},
        {"advance_physics_during_wait": 1},
        {"advance_physics_during_wait": None},
    ],
)
def test_invalid_original_optional_parameters_stop_before_camera_provider_or_action(
    monkeypatch, tmp_path, parameters
):
    repo, job, worker, calls, received, _, _ = software_factory(monkeypatch, tmp_path)
    persist_original_runtime_parameters(repo, job, parameters)
    assert worker.poll_once()
    assert received == [] and "episode" not in calls
    assert calls == []
    current = repo.get_job(job.job_id)
    assert current.status in {"FAILED", "BLOCKED_BY_ENV"}
    import json

    assert json.dumps(current.draft["parameter_overrides"], sort_keys=True) == json.dumps(
        parameters, sort_keys=True
    )
    assert repo.list_attempts(job.run_id)[0].ended_at is not None
    assert repo.list_leases(job.run_id)[0].released_at is not None
