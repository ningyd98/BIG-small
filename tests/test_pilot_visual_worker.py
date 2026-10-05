"""Persisted pilot source qualification; physics/provider APIs are CPU fixtures only."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cloud_edge_robot_arm.datasets.rgbd.models import SceneSpec, content_digest
from cloud_edge_robot_arm.research.protocol import build_scene_pools
from cloud_edge_robot_arm.simulation.config import SimulatorConfig
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import SQLiteSimulationJobRepository
from cloud_edge_robot_arm.vision.worker_owner import read_visual_worker_lease
from tests.test_ced_runtime_binding import role_binding


def api():
    name = "cloud_edge_robot_arm.research.pilot_worker"
    assert importlib.util.find_spec(name) is not None, "genuine persisted pilot worker is missing"
    return importlib.import_module(name)


@pytest.fixture(scope="module")
def assignments():
    from cloud_edge_robot_arm.research.pilot import build_pilot_assignments

    pools = build_scene_pools(981301, set(), protocol_version="ced.research.v2")
    return build_pilot_assignments(pools, "selection", role_bundle_hash="a" * 64)


def sources(tmp_path):
    module = api()
    root = tmp_path / "source"
    root.mkdir()
    planner, binding = role_binding(root)
    repo_root = Path(__file__).resolve().parents[1]
    for name in module.PILOT_WORKER_SOURCE_PATHS:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repo_root / name).read_bytes())
    return planner, binding


def attempt(tmp_path, assignments):
    planner, binding = sources(tmp_path)
    assignment = {**assignments[0], "role_bundle_hash": binding.bundle.digest()}
    directory = tmp_path / "stage" / "cases" / assignment["assignment_id"]
    directory.mkdir(parents=True)
    return (
        api().PilotWorkerAttempt(
            planner=planner,
            binding=binding,
            assignment=assignment,
            directory=directory,
            runtime_directory=tmp_path / "stage" / "worker-runtime",
            timeout_s=120.0,
        ),
        assignment,
        binding,
    )


def test_scene_compilation_preserves_all_scene_parameters_before_genuine_reset(assignments):
    module = api()
    scene = SceneSpec.model_validate(assignments[0]["base_assignment"]["scene"])
    xml, scenario = module.compile_pilot_scene(scene, SimulatorConfig(seed=scene.seed))
    tree = ET.fromstring(xml)
    params = scene.scene_parameters
    assert scenario.scenario_id == scene.group_id
    assert scenario.seed == scene.seed
    assert scenario.object_pose.model_dump() == dict(
        zip("xyz", params["target"]["position"], strict=True)
    )
    assert scenario.object_mass_kg == params["target"]["mass_kg"]
    for name, value in (("object", params["target"]), ("target_region", params["destination"])):
        body = tree.find(f".//body[@name='{name}']")
        assert body is not None
        geom = body.find("geom")
        assert geom is not None
        assert list(map(float, body.attrib["pos"].split())) == value["position"]
        assert list(map(float, geom.attrib["size"].split())) == value["half_size"]
        assert list(map(float, geom.attrib["rgba"].split())) == value["rgba"]
    for index, obj in enumerate(params["distractors"]):
        body = tree.find(f".//body[@name='dataset_distractor_{index}']")
        assert body is not None and body.find("freejoint") is not None
        assert list(map(float, body.attrib["pos"].split())) == obj["position"]
        assert float(body.find("geom").attrib["mass"]) == obj["mass_kg"]
    camera = tree.find(".//camera[@name='rgbd']")
    assert list(map(float, camera.attrib["pos"].split())) == params["camera"]["position"]
    assert list(map(float, camera.attrib["quat"].split())) == params["camera"]["quaternion"]
    assert float(camera.attrib["fovy"]) == params["camera"]["fovy"]


def test_attempt_uses_real_queue_lease_open_attempt_and_original_assignment(tmp_path, assignments):
    owner, assignment, binding = attempt(tmp_path, assignments)
    before = datetime.now(UTC)
    with owner:
        source = owner.source
        assert source.job_repository is owner.jobs
        assert type(source.job_repository) is SQLiteSimulationJobRepository
        lease = read_visual_worker_lease(
            owner.jobs,
            job_id=source.job_id,
            run_id=source.run_id,
            worker_id=source.worker_id,
            lease_id=source.lease_id,
        )
        job = owner.jobs.get_job(source.job_id)
        current = owner.jobs.list_attempts(source.run_id)[0]
        assert lease.attempt == current.attempt == job.attempt == 1
        assert current.result == "RUNNING" and current.ended_at is None
        assert job.status == RuntimeJobStatus.RUNNING
        assert job.manifest["pilot_assignment"] == assignment
        assert job.draft["parameter_overrides"] == {
            "supervision_period_ms": int(assignment["period_s"] * 1000),
            "advance_physics_during_wait": True,
        }
        assert job.reproducibility_hash == content_digest(assignment)
        assert job.scenario_id == assignment["group_id"]
        assert source.task_started_at == current.started_at
        assert before <= source.task_started_at <= datetime.now(UTC)
        assert source.task_timeout_s == 120.0
        assert source.source_root == binding.root
        owner.check_active()
    completed = owner.jobs.get_job(source.job_id)
    assert completed.status == RuntimeJobStatus.FAILED
    assert owner.jobs.list_attempts(source.run_id)[0].ended_at is not None
    assert owner.jobs.list_leases(source.run_id)[0].released_at is not None
    persisted = SQLiteSimulationJobRepository(owner.jobs.database_path).get_job(source.job_id)
    assert persisted.manifest["pilot_assignment"] == assignment


def test_current_cancel_invalidates_source_and_heartbeat_without_restoring_running(
    tmp_path, assignments
):
    owner, _, _ = attempt(tmp_path, assignments)
    with owner:
        owner.jobs.request_cancel(owner.source.job_id)
        assert owner.cancelled()
        with pytest.raises(RuntimeError):
            owner.check_active()
        with pytest.raises(RuntimeError):
            owner.heartbeat()
    assert owner.jobs.get_job(owner.source.job_id).status == RuntimeJobStatus.CANCELLED
    assert owner.jobs.list_attempts(owner.source.run_id)[0].result == "CANCELLED"


def test_source_drift_is_reread_before_setup_effect(tmp_path, assignments):
    owner, _, binding = attempt(tmp_path, assignments)
    with owner:
        (binding.root / "src/cloud_edge_robot_arm/research/pilot_worker.py").write_text("# drift\n")
        with pytest.raises(ValueError, match="source"):
            owner.check_active()


def test_initialization_time_does_not_restart_original_deadline(tmp_path, assignments):
    owner, _, _ = attempt(tmp_path, assignments)
    with owner:
        original = owner.source
        owner.source = replace(original, task_started_at=datetime.now(UTC) - timedelta(seconds=121))
        with pytest.raises(TimeoutError):
            owner.check_active()
        assert owner.source.task_timeout_s == 120.0
    assert owner.jobs.get_job(original.job_id).status == RuntimeJobStatus.TIMED_OUT


def test_heartbeat_updates_persistent_lease_join_only_for_current_attempt(tmp_path, assignments):
    owner, _, _ = attempt(tmp_path, assignments)
    with owner:
        before = owner.jobs.list_leases(owner.source.run_id)[0]
        owner.heartbeat()
        after = owner.jobs.list_leases(owner.source.run_id)[0]
        assert after.heartbeat_at >= before.heartbeat_at
        assert after.expires_at >= before.expires_at
        assert owner.jobs.get_job(owner.source.job_id).lease_expires_at == after.expires_at
        assert owner.jobs.list_attempts(owner.source.run_id)[0].ended_at is None


def test_start_source_failure_closes_actual_attempt_and_releases_lease(
    monkeypatch, tmp_path, assignments
):
    owner, _, binding = attempt(tmp_path, assignments)
    start = owner.jobs.start_attempt

    def drift(job_id, *, worker_id):
        actual = start(job_id, worker_id=worker_id)
        source = binding.root / "src/cloud_edge_robot_arm/research/pilot_worker.py"
        source.write_text("# source changed during durable startup\n")
        return actual

    monkeypatch.setattr(owner.jobs, "start_attempt", drift)
    with pytest.raises(ValueError, match="source"):
        with owner:
            pytest.fail("changed source reached backend setup")
    job = owner.jobs.list_jobs()[0]
    assert job.status == RuntimeJobStatus.FAILED
    assert owner.jobs.list_attempts(job.run_id)[0].ended_at is not None
    assert owner.jobs.list_leases(job.run_id)[0].released_at is not None


@pytest.mark.parametrize("committed", [False, True])
def test_start_attempt_storage_failure_releases_owned_lease_and_closes_only_actual_attempt(
    monkeypatch, tmp_path, assignments, committed
):
    owner, _, _ = attempt(tmp_path, assignments)
    start = owner.jobs.start_attempt

    def storage_failure(job_id, *, worker_id):
        if committed:
            start(job_id, worker_id=worker_id)
        raise RuntimeError("SOFTWARE_ONLY start storage failure")

    monkeypatch.setattr(owner.jobs, "start_attempt", storage_failure)
    with pytest.raises(RuntimeError, match="start storage failure"):
        with owner:
            pytest.fail("failed actual startup reached backend setup")
    job = owner.jobs.list_jobs()[0]
    assert job.status == RuntimeJobStatus.FAILED
    rows = owner.jobs.list_attempts(job.run_id)
    assert len(rows) == int(committed)
    assert job.attempt == int(committed)
    if committed:
        assert rows[0].ended_at is not None and rows[0].result == "FAILED"
    assert owner.jobs.list_leases(job.run_id)[0].released_at is not None


def test_aborted_start_preserves_replaced_lease_and_new_actual_attempt(
    monkeypatch, tmp_path, assignments
):
    owner, _, _ = attempt(tmp_path, assignments)
    start = owner.jobs.start_attempt
    replacement = {}

    def takeover_then_fail(job_id, *, worker_id):
        old = start(job_id, worker_id=worker_id)
        old_job = owner.jobs.get_job(job_id)
        owner.jobs.finish_attempt(
            job_id,
            attempt=old.attempt,
            result="INTERRUPTED",
            error="SOFTWARE_ONLY owner replacement",
            artifact_paths={"old": "retained.json"},
        )
        owner.jobs.release_lease(old_job.lease_id)
        for before, after in (
            (RuntimeJobStatus.LEASED, RuntimeJobStatus.INTERRUPTED),
            (RuntimeJobStatus.INTERRUPTED, RuntimeJobStatus.RECOVERY_PENDING),
            (RuntimeJobStatus.RECOVERY_PENDING, RuntimeJobStatus.QUEUED),
        ):
            assert (
                owner.jobs.update_status_cas(
                    job_id,
                    expected=before,
                    next_status=after,
                    reason_code="SOFTWARE_ONLY takeover",
                    worker_id=worker_id,
                    lease_id=old_job.lease_id,
                    expected_worker_id=worker_id,
                    expected_lease_id=old_job.lease_id,
                )
                is not None
            )
        lease = owner.jobs.acquire_lease(
            worker_id=worker_id, backend="MUJOCO", lease_ttl_seconds=30
        )
        assert lease is not None and lease.lease_id != old_job.lease_id
        actual = start(job_id, worker_id=worker_id)
        for before, after in (
            (RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
            (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING),
        ):
            assert (
                owner.jobs.update_status_cas(
                    job_id,
                    expected=before,
                    next_status=after,
                    reason_code="SOFTWARE_ONLY takeover",
                    worker_id=worker_id,
                    lease_id=lease.lease_id,
                    expected_worker_id=worker_id,
                    expected_lease_id=lease.lease_id,
                )
                is not None
            )
        replacement.update(lease=lease, attempt=actual, job=owner.jobs.get_job(job_id))
        raise RuntimeError("SOFTWARE_ONLY startup response lost after takeover")

    monkeypatch.setattr(owner.jobs, "start_attempt", takeover_then_fail)
    with pytest.raises(RuntimeError, match="response lost"):
        with owner:
            pytest.fail("replaced source reached backend setup")
    assert owner.jobs.get_job(replacement["job"].job_id) == replacement["job"]
    assert owner.jobs.list_attempts(owner.run_id)[-1] == replacement["attempt"]
    assert owner.jobs.list_leases(owner.run_id)[-1] == replacement["lease"]


def test_exit_preserves_already_ended_actual_attempt_evidence(tmp_path, assignments):
    owner, _, _ = attempt(tmp_path, assignments)
    with pytest.raises(RuntimeError, match="attempt source"):
        with owner:
            owner.jobs.finish_attempt(
                owner.source.job_id,
                attempt=owner.jobs.get_job(owner.source.job_id).attempt,
                result="EXTERNAL_TERMINAL",
                error="SOFTWARE_ONLY retained evidence",
                artifact_paths={"previous": "retained.json"},
            )
            before = owner.jobs.list_attempts(owner.source.run_id)[0]
    assert owner.jobs.list_attempts(owner.source.run_id)[0] == before
    assert owner.jobs.get_job(owner.source.job_id).status == RuntimeJobStatus.RUNNING
    assert owner.jobs.list_leases(owner.source.run_id)[0].released_at is not None


def test_terminal_source_cannot_publish_success_after_current_lease_is_released(
    tmp_path, assignments
):
    from cloud_edge_robot_arm.vision.evaluation import VisualEpisodeOutcome

    owner, _, _ = attempt(tmp_path, assignments)
    with pytest.raises(RuntimeError, match="lease source"):
        with owner:
            owner.record_outcome(
                VisualEpisodeOutcome(
                    success=True,
                    status="SUCCESS",
                    safety_violation=False,
                    failure_reason=None,
                    measured_lift_m=0.0,
                    hold_s=0.0,
                    placed_stable_s=0.0,
                    elapsed_s=0.0,
                    terminal_reason="SOFTWARE_ONLY_TERMINAL_SOURCE_PROBE",
                )
            )
            owner.jobs.release_lease(owner.source.lease_id)
    job = owner.jobs.get_job(owner.source.job_id)
    assert job.status == RuntimeJobStatus.FAILED
    assert owner.jobs.list_attempts(job.run_id)[0].result == "FAILED"


def test_pilot_script_delegates_complete_assignment_to_persisted_worker(
    monkeypatch, tmp_path, assignments
):
    from types import SimpleNamespace

    from scripts import run_rgbd_pilot as script

    planner, binding = sources(tmp_path)
    directory = tmp_path / "stage" / "cases" / assignments[0]["assignment_id"]
    directory.mkdir(parents=True)
    executor = script._RoleBoundPilotExecutor(
        {"timeout_s": 120}, planner, binding, tmp_path / "stage"
    )
    executor.archived = True
    received = []

    def run(**kwargs):
        received.append(kwargs)
        return SimpleNamespace(
            outcome=SimpleNamespace(),
            worker_source={"scope": "SOFTWARE_ONLY", "job_id": "from-real-worker"},
        )

    # Exercise the script adapter while avoiding any renderer/provider operation.
    monkeypatch.setattr(api(), "run_pilot_visual_worker", run)
    monkeypatch.setattr(script, "asdict", lambda outcome: {"success": False, "status": "FAILED"})
    row = executor(assignments[0], directory)
    assert len(received) == 1
    assert received[0]["assignment"] == assignments[0]
    assert received[0]["binding"] is binding
    assert received[0]["timeout_s"] == 120
    assert received[0]["runtime_directory"] == tmp_path / "stage" / "worker-runtime"
    assert row["accepted_success"] is False
    assert row["worker_source"]["scope"] == "SOFTWARE_ONLY"


def test_explicit_scene_xml_reports_its_actual_compiled_source_hash(monkeypatch):
    from types import SimpleNamespace

    from cloud_edge_robot_arm.simulation.mujoco import backend as module

    model = SimpleNamespace(opt=SimpleNamespace(), geom=lambda name: SimpleNamespace(id=hash(name)))
    mujoco = SimpleNamespace(
        MjModel=SimpleNamespace(from_xml_string=lambda xml: model),
        MjData=lambda model: SimpleNamespace(),
    )
    monkeypatch.setattr(module, "find_spec", lambda name: object())
    monkeypatch.setitem(__import__("sys").modules, "mujoco", mujoco)
    backend = module.MuJoCoPhysicsBackend()
    xml = "<mujoco>SOFTWARE_ONLY_SCENE</mujoco>"
    backend.initialize(SimulatorConfig(), model_xml=xml)
    assert (
        backend.model_parameter_evidence["spec_xml_sha256"]
        == hashlib.sha256(xml.encode()).hexdigest()
    )
    assert backend.model_parameter_evidence["compiler"] == "MjModel.from_xml_string"


def pipeline(monkeypatch, tmp_path, assignments, *, initialize_hook=None, settle_hook=None):
    """Actual SQLite/runtime source; replace only unavailable physics/provider effects."""
    from contextlib import contextmanager
    from types import SimpleNamespace

    from cloud_edge_robot_arm.contracts import RobotState
    from cloud_edge_robot_arm.vision.evaluation import VisualEpisodeOutcome

    module = api()
    planner, binding = sources(tmp_path)
    assignment = {**assignments[0], "role_bundle_hash": binding.bundle.digest()}
    directory = tmp_path / "stage" / "cases" / assignment["assignment_id"]
    directory.mkdir(parents=True)
    calls, received = [], []
    backend = SimpleNamespace(_episode_id=None, command_records=[], fault_records=[])

    def current_job():
        paths = list((tmp_path / "stage" / "worker-runtime").glob("*/jobs.sqlite"))
        assert len(paths) == 1
        jobs = SQLiteSimulationJobRepository(paths[0])
        jobs_list = jobs.list_jobs()
        assert len(jobs_list) == 1
        return jobs, jobs_list[0]

    def initialize(config, **kwargs):
        calls.append("initialize")
        backend._config = config
        jobs, job = current_job()
        assert job.status == RuntimeJobStatus.RUNNING
        assert jobs.list_attempts(job.run_id)[0].started_at <= datetime.now(UTC)
        assert job.manifest["pilot_assignment"] == assignment
        assert (
            job.manifest["compiled_scene_sha256"]
            == hashlib.sha256(kwargs["model_xml"].encode()).hexdigest()
        )
        if initialize_hook:
            initialize_hook(jobs, job)

    def reset(scenario):
        calls.append("reset")
        backend._scenario = scenario
        backend._episode_id = "SOFTWARE_ONLY_ACTUAL_RESET_SOURCE"

    def step(**kwargs):
        calls.append("settle")
        if settle_hook:
            settle_hook(*current_job())

    backend.initialize, backend.reset, backend.step = initialize, reset, step
    backend.shutdown = lambda: calls.append("shutdown")
    backend.current_physics_observation = lambda: pytest.fail("online pilot read physics labels")
    robot = SimpleNamespace(_backend=backend, get_state=lambda: RobotState(connected=True))

    class Capture:
        def __init__(self, config, *, backend):
            self._backend, self._owns_backend = backend, False

        def __enter__(self):
            calls.append("capture_enter")
            return self

        def __exit__(self, *args):
            calls.append("capture_exit")

    class Recorder:
        """CPU order probe only; generates no raw records or completeness assertion."""

        def __init__(self, backend, capture, executor, **kwargs):
            self.backend, self.capture_session, self.executor = backend, capture, executor

        def __enter__(self):
            calls.append("raw_enter")
            assert backend._episode_id is None
            return self

        def __exit__(self, *args):
            calls.append("raw_exit")

        @contextmanager
        def purpose(self, name):
            calls.append("purpose:" + name)
            yield

    def episode(planner, actual_robot, capture, policy):
        calls.append("episode")
        source = policy.worker_runtime.source
        assert type(source.job_repository) is SQLiteSimulationJobRepository
        assert (
            source.task_started_at
            == source.job_repository.list_attempts(source.run_id)[0].started_at
        )
        assert policy.worker_runtime.episode_id == backend._episode_id
        assert policy.raw_recorder.capture_session is capture
        assert policy.raw_recorder.executor._robot is actual_robot
        assert policy.supervision_period_s == assignment["period_s"]
        assert policy.advance_physics_during_wait is True
        assert policy.timeout_s <= source.task_timeout_s
        received.append(policy)
        return VisualEpisodeOutcome(
            success=False,
            status="FAILED",
            safety_violation=False,
            failure_reason="SOFTWARE_ONLY_ZERO_ACTIONS",
            measured_lift_m=0.0,
            hold_s=0.0,
            placed_stable_s=0.0,
            elapsed_s=0.0,
            terminal_reason="SOFTWARE_ONLY_ZERO_ACTIONS",
            episode_id=backend._episode_id,
        )

    monkeypatch.setattr(module, "MuJoCoPhysicsBackend", lambda: backend)
    monkeypatch.setattr(module, "MuJoCoSkillRobot", lambda backend: robot)
    monkeypatch.setattr(module, "VisualRawRecorderV3", Recorder)
    # This configuration probe cannot bypass any production admission gate.
    # Actual ExecutionPolicy keeps its persistent-supervision qualification guard.
    monkeypatch.setattr(module, "ExecutionPolicy", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(module, "run_visual_episode", episode)
    kwargs = dict(
        planner=planner,
        binding=binding,
        assignment=assignment,
        directory=directory,
        runtime_directory=tmp_path / "stage" / "worker-runtime",
        timeout_s=120.0,
        capture_factory=Capture,
    )
    return module, kwargs, calls, received, current_job


def test_pilot_pipeline_enters_shared_capture_and_sole_executor_recorder_before_reset(
    monkeypatch, tmp_path, assignments
):
    module, kwargs, calls, received, current_job = pipeline(monkeypatch, tmp_path, assignments)
    result = module.run_pilot_visual_worker(**kwargs)
    assert calls == [
        "initialize",
        "capture_enter",
        "raw_enter",
        "reset",
        "purpose:SETTLE",
        "settle",
        "episode",
        "raw_exit",
        "capture_exit",
        "shutdown",
    ]
    assert result.outcome.executed_actions == 0 and result.outcome.success is False
    assert result.worker_source["attempt_result"] == "FAILED"
    jobs, job = current_job()
    assert job.status == RuntimeJobStatus.FAILED
    assert jobs.list_leases(job.run_id)[0].released_at is not None
    assert len(received) == 1


def test_pilot_pipeline_cancel_during_initialization_stops_before_reset(
    monkeypatch, tmp_path, assignments
):
    module, kwargs, calls, received, current_job = pipeline(
        monkeypatch,
        tmp_path,
        assignments,
        initialize_hook=lambda jobs, job: jobs.request_cancel(job.job_id),
    )
    with pytest.raises(RuntimeError, match="lease source"):
        module.run_pilot_visual_worker(**kwargs)
    assert calls == ["initialize", "shutdown"] and received == []
    jobs, job = current_job()
    assert job.status == RuntimeJobStatus.CANCELLED
    assert jobs.list_attempts(job.run_id)[0].result == "CANCELLED"


def test_pilot_pipeline_cancel_during_settle_stops_before_cloud_or_controller(
    monkeypatch, tmp_path, assignments
):
    module, kwargs, calls, received, current_job = pipeline(
        monkeypatch,
        tmp_path,
        assignments,
        settle_hook=lambda jobs, job: jobs.request_cancel(job.job_id),
    )
    with pytest.raises(RuntimeError, match="lease source"):
        module.run_pilot_visual_worker(**kwargs)
    assert calls == [
        "initialize",
        "capture_enter",
        "raw_enter",
        "reset",
        "purpose:SETTLE",
        "settle",
        "raw_exit",
        "capture_exit",
        "shutdown",
    ]
    assert received == []
    jobs, job = current_job()
    assert job.status == RuntimeJobStatus.CANCELLED
    assert jobs.list_attempts(job.run_id)[0].ended_at is not None
