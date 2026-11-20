"""Private startup identity and live worker/lease tests; no actual simulation."""

import copy
import json
import os
import pickle
import sqlite3
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from importlib import import_module, util
from time import monotonic
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import (
    CONFIG,
    ROOT,
    detached,
    load_json,
    prepare_native_calibration,
)
from cloud_edge_robot_arm.research.native_collection_application import (
    _REGISTRY,
    NativeCollectionApplication,
    _live,
)
from cloud_edge_robot_arm.research.native_collection_grounding import collection_unknown_row
from cloud_edge_robot_arm.research.native_full_horizon_recorder import (
    _ISSUER,
    NativeFullHorizonRecorder,
)
from cloud_edge_robot_arm.research.operational_time_v1 import open_operational_clock
from cloud_edge_robot_arm.simulation_runtime import sqlite_repository
from cloud_edge_robot_arm.simulation_runtime.models import RuntimeJobStatus
from cloud_edge_robot_arm.simulation_runtime.worker import CancelledByOperator, TimedOut
from cloud_edge_robot_arm.vision.worker_owner import read_visual_worker_lease
from tests.test_visual_raw_recorder_v3 import recorder_fixture, software_sensor_camera


def test_collection_factory_api_required():
    name = "cloud_edge_robot_arm.research.native_collection_application"
    module = import_module(name) if util.find_spec(name) else None
    assert getattr(module, "NativeCollectionApplication", None) is not None, (
        "collection factory missing"
    )


def application(tmp_path):
    protocol = tmp_path / "protocol"
    prepare_native_calibration(ROOT / CONFIG, output=protocol)
    return NativeCollectionApplication.from_startup(
        protocol, assignment_id="native-r439-0001", output=tmp_path / "run"
    )


def test_private_factory_copy_fabrication_and_foreign_worker(tmp_path):
    with pytest.raises(TypeError):
        NativeCollectionApplication()
    fake = object.__new__(NativeCollectionApplication)
    with pytest.raises(RuntimeError, match="exact live"):
        fake.check_active()
    app = application(tmp_path)
    for operation in (copy.copy, copy.deepcopy, pickle.dumps):
        with pytest.raises(RuntimeError, match="cannot"):
            operation(app)
    app.worker = object()
    with pytest.raises(RuntimeError, match="identity"):
        app.prepare_once()


def test_origin_before_enqueue_and_claim_is_one_shot(tmp_path):
    app = application(tmp_path)
    job = app.prepare_once()
    live = _REGISTRY[app]
    try:
        assert job.status.value == "QUEUED"
        assert live.origin.upper_ns < live.deadline.deadline_ns
        assert live.deadline.deadline_ns == live.origin.lower_ns + 1800 * 10**9
        assert live.worker._active_task_origin is None
        with pytest.raises(RuntimeError, match="once"):
            app.prepare_once()
        with pytest.raises(RuntimeError, match="already claimed"):
            NativeCollectionApplication.from_startup(
                tmp_path / "protocol", assignment_id="native-r439-0001", output=tmp_path / "retry"
            )
    finally:
        live.owner.close()


def test_unreleased_assignment_no_output(tmp_path):
    app = application(tmp_path)
    with pytest.raises(ValueError, match="first"):
        NativeCollectionApplication.from_startup(
            _REGISTRY[app].protocol_path,
            assignment_id="native-r439-0002",
            output=tmp_path / "other",
        )
    assert not (tmp_path / "other").exists()


def test_actual_worker_poll_claims_real_lease_without_physics(tmp_path, monkeypatch):
    app = application(tmp_path)
    seen = []

    def software_body(self, worker, job, *, start_monotonic):
        live = _live(self)
        live.worker_origin = worker._active_task_origin
        source = self.check_active()
        assert source["lease"]["attempt"] == 1
        assert source["original_deadline_ns"] == live.deadline.deadline_ns
        assert live.origin.upper_ns < source["current"]["upper_ns"]
        assert live.worker_origin[:2] == (job.job_id, start_monotonic)
        mode = worker._frozen_operational_time_mode
        before_events = detached(live.repository.list_events(job.run_id))
        try:
            worker._frozen_operational_time_mode = "LOCAL_TEMPORAL_PUBLICATION_V1"
            assert worker._operational_lease_session is None
            assert worker._owns_artifact_publication(job, job.lease_id) is False
            assert detached(live.repository.list_events(job.run_id)) == before_events
        finally:
            worker._frozen_operational_time_mode = mode
        seen.append(source)
        original = live.worker_origin
        worker._active_task_origin = (job.job_id, start_monotonic + 1, datetime.now(UTC))
        with pytest.raises(RuntimeError, match="origin"):
            self.check_active()
        worker._active_task_origin = original
        live.result = dict(status="SOFTWARE_ONLY", native_qualification="UNKNOWN")
        return dict(evaluation_scope="TEACHER_COLLECTION", task_success=False), [], []

    monkeypatch.setattr(NativeCollectionApplication, "run_from_worker", software_body)
    assert app.execute_once()["status"] == "SOFTWARE_ONLY"
    assert len(seen) == 1
    assert _REGISTRY[app].closed
    with pytest.raises(RuntimeError):
        app.execute_once()


def test_actual_teacher_checkpoint_reads_one_sqlite_snapshot(tmp_path, monkeypatch):
    app = application(tmp_path)
    queries = Counter()
    actual_connect = sqlite3.connect
    connections = []

    def track_sql(sql):
        words = sql.split()
        queries[words[0].upper()] += 1
        if words[0] == "SELECT":
            queries[words[words.index("FROM") + 1]] += 1

    def trace_connect(*args, **kwargs):
        connection = actual_connect(*args, **kwargs)
        if kwargs.get("uri") and str(args[0]).endswith("?mode=ro"):
            connections.append(connection)
            connection.set_trace_callback(track_sql)
        return connection

    def software_body(self, worker, job, *, start_monotonic):
        live = _live(self)
        live.worker_origin = worker._active_task_origin
        with monkeypatch.context() as patch:
            patch.setattr(sqlite3, "connect", trace_connect)
            first = self.check_active()["lease"]
            assert not connections[-1].in_transaction
            source = self.check_active()["lease"]
            assert not connections[-1].in_transaction
        assert source["observed_at"] >= first["observed_at"]
        assert len(connections) == 1
        assert queries["CREATE"] == queries["INSERT"] == 0, dict(queries)
        assert queries["BEGIN"] == queries["ROLLBACK"] == 2, dict(queries)
        assert queries["simulation_jobs"] == 2, dict(queries)
        assert queries["simulation_job_leases"] == 2, dict(queries)
        assert queries["simulation_job_attempts"] == 2, dict(queries)
        baseline = read_visual_worker_lease(
            live.repository,
            job_id=job.job_id,
            run_id=job.run_id,
            worker_id=worker.worker_id,
            lease_id=job.lease_id,
            now=datetime.fromisoformat(source["observed_at"]),
        )
        assert source == baseline.to_payload()
        live.result = dict(status="SOFTWARE_ONLY", native_qualification="UNKNOWN")
        return dict(evaluation_scope="TEACHER_COLLECTION", task_success=False), [], []

    monkeypatch.setattr(NativeCollectionApplication, "run_from_worker", software_body)
    assert app.execute_once()["status"] == "SOFTWARE_ONLY"
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connections[0].execute("SELECT 1")


@pytest.fixture
def active_teacher_checkpoint(tmp_path):
    app = application(tmp_path)
    job = app.prepare_once()
    live = _live(app)
    owner = live.worker.worker_id
    lease = live.repository.acquire_lease(worker_id=owner, backend="MUJOCO", lease_ttl_seconds=60)
    assert lease is not None
    live.repository.start_attempt(job.job_id, worker_id=owner)
    for old, new in ((RuntimeJobStatus.LEASED, RuntimeJobStatus.STARTING),
                     (RuntimeJobStatus.STARTING, RuntimeJobStatus.RUNNING)):
        assert live.repository.update_status_cas(
            job.job_id, expected=old, next_status=new, reason_code="software checkpoint test",
            worker_id=owner, lease_id=lease.lease_id, expected_lease_id=lease.lease_id,
        ) is not None
    live.worker.active_job_id = job.job_id
    origin = (job.job_id, monotonic(), datetime.now(UTC))
    live.worker._active_task_origin = live.worker_origin = origin
    try:
        yield app, live.repository.get_job(job.job_id), lease
    finally:
        live.owner.close()


def test_teacher_checkpoint_job_records_are_independent(active_teacher_checkpoint):
    app, job, _ = active_teacher_checkpoint
    repo = app.repository
    with repo._teacher_checkpoint_read(_live(app).checkpoint_database):
        first = repo.get_job(job.job_id)
        first.draft["seeds"].clear()
        second = repo.get_job(job.job_id)
        assert first is not second
        assert second.draft["seeds"] == job.draft["seeds"]


@pytest.mark.parametrize("mutation", ["renew", "cancel", "release", "finish_attempt"])
def test_teacher_checkpoint_serializes_current_writer_and_rereads(
    active_teacher_checkpoint, monkeypatch, mutation,
):
    app, job, lease = active_teacher_checkpoint
    repo = app.repository
    other = sqlite_repository.SQLiteSimulationJobRepository(repo.database_path)
    ready = threading.Event()
    checked = threading.Event()
    lock_key = (os.getpid(), str(repo.database_path.resolve()))
    baseline = app.check_active()["lease"]
    acquired = []

    def concurrent_write():
        assert ready.wait(5)
        lock = sqlite_repository._PUBLICATION_LOCKS[lock_key]
        entered = lock.acquire(blocking=False)
        acquired.append(entered)
        if entered:
            lock.release()
        checked.set()
        if mutation == "renew":
            other.heartbeat_lease(lease.lease_id, lease_ttl_seconds=90)
        elif mutation == "cancel":
            other.request_cancel(job.job_id)
        elif mutation == "release":
            other.release_lease(lease.lease_id)
        else:
            other.finish_attempt(
                job.job_id, attempt=1, result="FAILED", error="software checkpoint test",
                artifact_paths={},
            )

    original = repo.get_job

    def staged_job_read(job_id):
        result = original(job_id)
        ready.set()
        assert checked.wait(5)
        return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(concurrent_write)
        with monkeypatch.context() as patch:
            patch.setattr(repo, "get_job", staged_job_read)
            observed = app.check_active()["lease"]
            assert acquired == [False]
            assert all(observed[k] == baseline[k] for k in (
                "job_state_hash", "lease_state_hash", "attempt_state_hash",
            ))
        future.result(timeout=5)
    if mutation == "renew":
        fresh = app.check_active()["lease"]
        assert fresh["job_state_hash"] != baseline["job_state_hash"]
        assert fresh["lease_state_hash"] != baseline["lease_state_hash"]
        assert fresh["attempt_state_hash"] == baseline["attempt_state_hash"]
    elif mutation == "cancel":
        with pytest.raises(CancelledByOperator):
            app.check_active()
    else:
        expected = "unique live job lease" if mutation == "release" else "unique open job attempt"
        with pytest.raises(ValueError, match=expected):
            app.check_active()


@pytest.mark.parametrize("condition,exception,pattern", [
    ("legacy_timeout", TimedOut, "timeout"),
    ("heartbeat", RuntimeError, "heartbeat failed"),
    ("foreign_worker", ValueError, "worker job identity"),
    ("expired", ValueError, "worker job identity"),
    ("wrong_attempt", RuntimeError, "lease/attempt changed"),
    ("duplicate_lease", ValueError, "unique live job lease"),
    ("duplicate_attempt", ValueError, "unique open job attempt"),
    ("bad_date", ValueError, "Invalid isoformat"),
    ("local_mode", RuntimeError, "current local task/lease authority unavailable"),
])
def test_teacher_checkpoint_retains_original_rejection(
    active_teacher_checkpoint, condition, exception, pattern,
):
    app, job, lease = active_teacher_checkpoint
    live = _live(app)
    if condition == "legacy_timeout":
        origin = (job.job_id, monotonic() - job.timeout_seconds - 1, datetime.now(UTC))
        live.worker._active_task_origin = live.worker_origin = origin
    elif condition == "heartbeat":
        live.worker._heartbeat_failed.set()
    elif condition == "foreign_worker":
        live.worker.worker_id = "foreign-worker"
    elif condition == "local_mode":
        live.worker._frozen_operational_time_mode = "LOCAL_TEMPORAL_PUBLICATION_V1"
    else:
        with closing(sqlite3.connect(app.repository.database_path)) as db, db:
            if condition == "expired":
                db.execute("UPDATE simulation_jobs SET lease_expires_at=? WHERE job_id=?", (
                    (datetime.now(UTC) - timedelta(seconds=1)).isoformat(), job.job_id,
                ))
            elif condition == "wrong_attempt":
                db.execute("UPDATE simulation_jobs SET attempt=2")
                db.execute("UPDATE simulation_job_attempts SET attempt=2")
            elif condition == "duplicate_lease":
                db.execute(
                    "INSERT INTO simulation_job_leases SELECT 'duplicate',job_id,worker_id,"
                    "acquired_at,expires_at,heartbeat_at,released_at FROM simulation_job_leases "
                    "WHERE lease_id=?", (lease.lease_id,),
                )
            elif condition == "duplicate_attempt":
                db.execute("INSERT INTO simulation_job_attempts SELECT job_id,run_id,2,worker_id,"
                           "started_at,ended_at,result,error,artifact_paths_json "
                           "FROM simulation_job_attempts WHERE job_id=?", (job.job_id,))
            else:
                db.execute("UPDATE simulation_job_leases SET expires_at='invalid'")
    with pytest.raises(exception, match=pattern):
        app.check_active()
    assert app.repository._teacher_checkpoint_connection() is None


def test_teacher_checkpoint_preserves_typed_timezone_offset(active_teacher_checkpoint):
    app, job, lease = active_teacher_checkpoint
    offset = datetime.now(timezone(timedelta(hours=-5))) + timedelta(seconds=35)
    with closing(sqlite3.connect(app.repository.database_path)) as db, db:
        db.execute("UPDATE simulation_jobs SET lease_expires_at=?", (offset.isoformat(),))
        db.execute("UPDATE simulation_job_leases SET expires_at=?", (offset.isoformat(),))
    observed = app.check_active()["lease"]
    baseline = read_visual_worker_lease(
        app.repository, job_id=job.job_id, run_id=job.run_id, worker_id=lease.worker_id,
        lease_id=lease.lease_id, now=datetime.fromisoformat(observed["observed_at"]),
    )
    assert observed == baseline.to_payload()


def test_teacher_checkpoint_rejects_replaced_database(active_teacher_checkpoint):
    app, _, _ = active_teacher_checkpoint
    path = app.repository.database_path
    path.rename(path.with_suffix(".historical"))
    sqlite_repository.SQLiteSimulationJobRepository(path)
    with pytest.raises(RuntimeError, match="database identity changed"):
        app.check_active()


def test_teacher_checkpoint_fault_releases_guard_without_rebuilding_schema(
    active_teacher_checkpoint,
):
    app, _, lease = active_teacher_checkpoint
    path = app.repository.database_path
    other = sqlite_repository.SQLiteSimulationJobRepository(path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("DROP TABLE simulation_job_attempts")
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        app.check_active()
    assert app.repository._teacher_checkpoint_connection() is None
    with closing(sqlite3.connect(path)) as db:
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE name='simulation_job_attempts'"
        ).fetchone() is None
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(other.heartbeat_lease, lease.lease_id, lease_ttl_seconds=90).result(timeout=5)


def test_teacher_checkpoint_does_not_replace_nested_writer(active_teacher_checkpoint, monkeypatch):
    app, job, lease = active_teacher_checkpoint
    repo = app.repository
    recorded = []
    actual_now = sqlite_repository._now

    def check_during_write():
        if getattr(repo._transactions, "connection", None) is not None and not recorded:
            owner = repo._writer_binding()
            with repo._teacher_checkpoint_read(_live(app).checkpoint_database):
                assert repo._teacher_checkpoint_connection() is None
                assert repo.get_job(job.job_id).lease_id == lease.lease_id
                assert repo._writer_binding() is owner
            recorded.append(True)
        return actual_now()

    monkeypatch.setattr(sqlite_repository, "_now", check_during_write)
    repo.heartbeat_lease(lease.lease_id, lease_ttl_seconds=90)
    assert recorded == [True]


def test_teacher_checkpoint_dense_cpu_capture_stops_on_fresh_cancel(active_teacher_checkpoint):
    from cloud_edge_robot_arm.edge.runtime.skill_executor import SkillExecutor
    from cloud_edge_robot_arm.edge.runtime.skill_registry import SkillRegistry
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard
    from cloud_edge_robot_arm.simulation.config import SimulatorConfig
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MuJoCoSkillRobot
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession

    app, job, _ = active_teacher_checkpoint
    live = _live(app)
    backend = live.backend = MuJoCoPhysicsBackend()
    backend.initialize(SimulatorConfig(domain_randomization=False))
    software_sensor_camera(backend)
    camera = backend._camera

    def cached_capture(*args, **kwargs):
        frame, _, _, passes = camera.capture_with_instances(*args, **kwargs)
        return frame, (), {}, passes[:2]

    camera._capture, camera.close = cached_capture, lambda: None
    live.robot = MuJoCoSkillRobot(backend)
    live.executor = SkillExecutor(robot=live.robot, registry=SkillRegistry.default())
    live.capture = MuJoCoCaptureSession(backend._config, backend=backend)
    recorder = live.recorder = NativeFullHorizonRecorder(
        backend, live.capture, live.executor, directory=app.output / "cpu-originals",
        source_root=ROOT, source_hashes=app.protocol["source_hashes"], application=app,
        owner=live.owner, _token=_ISSUER,
    )
    canceller = sqlite_repository.SQLiteSimulationJobRepository(app.repository.database_path)
    try:
        with live.capture, recorder:
            backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=job.seed))
            recorder.require_clean_reset()
            with pytest.raises(CancelledByOperator):
                with _collection_guard(live, app._guard, app.policy["guard_event_limit"]):
                    with backend.capture_each_physics_step(max_captures=16):
                        start = monotonic()
                        for _ in range(4):
                            backend.step(1)
                        elapsed = monotonic() - start
                        active_checks = len(live.checks)
                        canceller.request_cancel(job.job_id)
                        backend.step(1)
            assert backend.total_physics_steps == 4
            assert backend.estop_engaged
            assert recorder.render_passes == 22  # 4 x (3 registered + 2 cache), plus reset pair.
            assert active_checks >= 12 * 4
            assert live.repository._teacher_checkpoint_connection() is None
            print(json.dumps({
                "scope": "CPU_MUJOCO_WITH_SOFTWARE_SENSOR",
                "physical_steps": backend.total_physics_steps,
                "render_fixture_passes": recorder.render_passes,
                "completed_guard_checks": active_checks,
                "before_cancel_wall_s": elapsed,
                "stop_engaged": backend.estop_engaged,
                "original_members": len(recorder.inventory),
                "model_calls": 0,
            }))
    finally:
        backend.shutdown()


def unknown_row(**changes):
    values = dict(
        phase="PRE",
        skill="MOVE_ABOVE",
        condition="target_reachable",
        verdict=dict(status="UNKNOWN", reasons=["visual_fact_not_boolean"]),
        facts={
            "target_reachable": dict(
                value=None,
                reasons=["calibrated_depth_error_bound_missing"],
                measured_values={"stationary_support": True},
            )
        },
        holding=False,
        tcp_reached=False,
        full_horizon=False,
        nominal_release=False,
        released=False,
        tracker_has_no_held=True,
        depth_bound_missing=True,
    )
    values.update(changes)
    return collection_unknown_row(**values)


def test_only_precise_reachable_depth_unknown_is_experiment_permission():
    assert unknown_row() == "PRE_INITIAL_REACHABLE_DEPTH"
    for changes in (
        dict(phase="POST"),
        dict(skill="RELEASE"),
        dict(condition="target_visible"),
        dict(verdict={"status": "FAIL", "reasons": ["visual_fact_not_boolean"]}),
        dict(depth_bound_missing=False),
        dict(facts={}),
        dict(verdict={"status": "UNKNOWN", "reasons": ["observation_future_or_stale"]}),
    ):
        assert unknown_row(**changes) is None
    assert (
        unknown_row(
            facts={
                "target_reachable": dict(
                    value=None,
                    reasons=["calibrated_depth_error_bound_missing"],
                    measured_values={"stationary_support": False},
                )
            }
        )
        is None
    )


def test_lift_missing_fact_is_only_exact_original_interface_exception():
    kwargs = dict(
        phase="POST",
        skill="LIFT",
        condition="object_held",
        facts={},
        holding=True,
        tcp_reached=True,
        full_horizon=True,
        verdict=dict(
            status="UNKNOWN",
            reasons=["visual_fact_missing_or_untrusted_source", "robot_state_condition_satisfied"],
        ),
    )
    assert unknown_row(**kwargs) == "POST_LIFT_HELD_INTERFACE"
    for change in (
        dict(holding=False),
        dict(full_horizon=False),
        dict(tracker_has_no_held=False),
        dict(facts={"object_held": {}}),
        dict(condition="object_lifted"),
    ):
        assert unknown_row(**(kwargs | change)) is None


def test_release_requires_place_nominal_and_holding():
    kwargs = dict(
        skill="RELEASE",
        condition="object_inside_target_region",
        holding=True,
        nominal_release=True,
        facts={
            "object_inside_target_region": dict(
                value=None, reasons=["calibrated_depth_error_bound_missing"]
            )
        },
    )
    assert unknown_row(**kwargs) == "PRE_RELEASE_NOMINAL_DEPTH"
    assert unknown_row(**(kwargs | dict(nominal_release=False))) is None
    assert unknown_row(**(kwargs | dict(holding=False))) is None


def test_streamed_frame_roundtrips_original_and_full_hold_uses_legacy_hold(tmp_path):
    base, backend, capture, executor, identity, original = recorder_fixture(tmp_path)
    software_sensor_camera(backend)
    owner = open_operational_clock()
    app = SimpleNamespace(policy={"raw_bytes": 2**30}, check_active=lambda: None)
    recorder = NativeFullHorizonRecorder(
        backend,
        capture,
        executor,
        directory=tmp_path / "full",
        source_root=base.source_root,
        source_hashes=base.source_hashes,
        application=app,
        owner=owner,
        _token=_ISSUER,
    )
    try:
        with capture, recorder:
            # CPU fixture binds the same concrete old types; no fake source certificate.
            recorder.bind_source(
                replace(identity, source_kind="GROUND_TRUTH_TEACHER", model_snapshot_hash=None),
                original,
            )
            observation = recorder.capture()
            aid = recorder.allocated_acquisition_ids[-1]
            metadata = load_json(recorder.directory / recorder.frame_sources[aid])
            import base64

            payload = metadata["frame"]["observation_payload"]
            for field, name in metadata["encoded_fields"].items():
                payload[field] = base64.b64encode((recorder.directory / name).read_bytes()).decode()
            assert payload == observation.model_dump(mode="json")
            assert metadata["instance_count"] == observation.width * observation.height
            assert metadata["pass_count"] == 3
            assert metadata["capture_source"]["role"] == "REGISTERED_ACTION_BOUNDARY"
            assert set(recorder._frames[-1]["observation_payload"]) == {
                "observation_id",
                "checksum_sha256",
            }
            with recorder.purpose("FULL_HORIZON_HOLD") as interval:
                pass
            assert recorder.hold_mappings[-1]["interval_id"] == interval
            assert recorder._intervals[-1]["kind"] == "HOLD"
            with pytest.raises(ValueError):
                with recorder.purpose("RANDOM_SCOPE"):
                    pass
            manifest = recorder.freeze()
            assert manifest["native_qualification"] == "UNKNOWN"
            assert detached(original) == original.to_payload()
            with pytest.raises(RuntimeError):
                recorder.freeze()
    finally:
        owner.close()


def source_recorder(tmp_path):
    base, backend, capture, executor, identity, original = recorder_fixture(tmp_path)
    software_sensor_camera(backend)
    owner = open_operational_clock()
    recorder = NativeFullHorizonRecorder(
        backend,
        capture,
        executor,
        directory=tmp_path / "originals",
        source_root=base.source_root,
        source_hashes=base.source_hashes,
        application=SimpleNamespace(policy={"raw_bytes": 2**30}, check_active=lambda: None),
        owner=owner,
        _token=_ISSUER,
    )
    return recorder, backend, capture, owner, original


def test_shield_original_context_replays_and_failed_write_stops(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.edge.safety.models import SafetyContext
    from cloud_edge_robot_arm.research.native_calibration_collection import digest
    from cloud_edge_robot_arm.vision.execution import research_safety_shield
    from tests.test_visual_owner_registration import values

    recorder, backend, capture, owner, original = source_recorder(tmp_path)
    shield = research_safety_shield(1800)
    try:
        with capture, recorder:
            recorder.capture()
            recorder.record_shield_config(shield)
            config = load_json(recorder.directory / "shield/config.json")
            assert config["source_generation"] == digest(dict(recorder.source_hashes))
            assert config["merged"]["low_height_exception_skills"] == sorted(
                shield.config.merged.low_height_exception_skills
            )
            context = shield.context_builder.build(
                contract=original.contract,
                step=original.contract.steps[0],
                robot_state=values()["online"].robot_state,
                scene_version=original.contract.scene_version,
                wall_clock_now=datetime.now(UTC),
            )
            for index, changes in enumerate(
                ({}, {"robot_estop_engaged": True}, {"parameters": {"bypass_safety": True}})
            ):
                recorder.grounding_sources[index] = {
                    "path": "software-only-grounding",
                    "sha256": "a" * 64,
                }
                current = context.model_copy(update=changes)
                if index == 2:
                    with pytest.raises(ValueError, match="bypass"):
                        recorder.check_shield(shield, current, index=index, phase="PRE")
                    assert (
                        load_json(recorder.directory / "shield/step-3-pre-result.json")[
                            "error_type"
                        ]
                        == "ValueError"
                    )
                    continue
                result, refs = recorder.check_shield(shield, current, index=index, phase="PRE")
                source = load_json(recorder.directory / refs["input"]["path"])
                assert source["source_generation"] == digest(dict(recorder.source_hashes))
                replay = shield.pre_check(SafetyContext.model_validate(source["context"]))
                assert detached(replay) == detached(result)
                assert load_json(recorder.directory / refs["result"]["path"])["result"] == detached(
                    result
                )
                if index == 1:
                    assert not result.allowed
            invoked = []
            monkeypatch.setattr(shield, "pre_check", lambda value: invoked.append(value))
            recorder.grounding_sources[3] = recorder.grounding_sources[0]

            def full_disk(*args):
                raise OSError("input write failed")

            monkeypatch.setattr(recorder, "_write_original", full_disk)
            with pytest.raises(OSError, match="input write"):
                recorder.check_shield(shield, context, index=3, phase="PRE")
            assert not invoked
    finally:
        owner.close()


def test_guard_normal_exit_has_termination_parent(tmp_path):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
    try:
        with capture, recorder:
            baseline = len(recorder._commands)
            with _collection_guard(live, lambda event: None, 1024):
                pass
            assert backend.total_physics_steps == 0
            commands = recorder._commands[baseline:]
            assert [row["command_payload"]["type"] for row in commands] == [
                "hold_current_joints",
                "emergency_stop",
            ]
            assert [row["command_seq"] for row in commands] == [baseline + 1, baseline + 2]
            assert len({row["parent_interval_id"] for row in commands}) == 1
            for command in commands:
                parent = next(
                    r
                    for r in recorder._intervals
                    if r["interval_id"] == command["parent_interval_id"]
                )
                assert parent["kind"] == "TERMINATION"
                assert parent["start_step"] == parent["end_step"] == 0
                assert command["command_payload"]["accepted"] is True
            assert live.progress == {"guard_entered": True, "guard_exited": True}
    finally:
        owner.close()


def test_guard_exception_exit_preserves_primary_and_secondary(tmp_path, monkeypatch):
    from contextlib import contextmanager

    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    for case in ("body", "stop", "purpose"):
        recorder, backend, capture, owner, _ = source_recorder(tmp_path / case)
        live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
        original = ValueError("original body failure")
        stops = []
        actual_stop = backend.emergency_stop

        def stop(stops=stops, actual_stop=actual_stop, case=case):
            stops.append(1)
            actual_stop()
            if case == "stop":
                raise OSError("secondary stop failure")

        monkeypatch.setattr(backend, "emergency_stop", stop)
        if case == "purpose":

            @contextmanager
            def bad_purpose(name):
                raise OSError("purpose entry failure")
                yield

            monkeypatch.setattr(recorder, "purpose", bad_purpose)
        try:
            with capture, recorder:
                with pytest.raises(ValueError) as caught:
                    with _collection_guard(live, lambda event: None, 1024):
                        raise original
                assert caught.value is original
                assert stops == [1] and backend.estop_engaged
                assert backend.total_physics_steps == 0
                if case == "stop":
                    assert backend.execution_guard_events[-1]["stop_error_type"] == "OSError"
                if case == "purpose":
                    assert live.failures[0]["phase"] == "termination_entry"
        finally:
            owner.close()


def software_complete_body(self, worker, job, *, start_monotonic):
    live = _live(self)
    live.worker_origin = worker._active_task_origin
    self.check_active()
    live.result = dict(
        status="SOFTWARE_ONLY", native_qualification="UNKNOWN", teacher_collection_admitted=False
    )
    return dict(evaluation_scope="TEACHER_COLLECTION", task_success=False), [], []


def test_collection_preflight_failure_retains_worker_original(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research import native_collection_application as module

    app = application(tmp_path)

    def fail_preflight(*args):
        raise OSError("registered source preflight failure")

    monkeypatch.setattr(module, "check_sources", fail_preflight)
    with pytest.raises(RuntimeError, match="registered source preflight failure"):
        app.execute_once()
    result = load_json(app.output / "collection-result.json")
    assert result["status"] == "COLLECTION_PARTIAL" and result["physics_steps"] == 0
    assert result["count_provenance"] == "NOT_STARTED"
    assert (
        "registered source preflight failure" in result["worker_snapshot"]["job"]["error_message"]
    )
    assert (
        "registered source preflight failure" in result["worker_snapshot"]["attempts"][0]["error"]
    )
    assert result["owner_closure"]["completed"] and _REGISTRY[app].closed
    assert not (app.output / "originals").exists()


def test_collection_worker_failure_after_body_downgrades_final(tmp_path, monkeypatch):
    app = application(tmp_path)

    def bad_publication(self, worker, job, *, start_monotonic):
        software_complete_body(self, worker, job, start_monotonic=start_monotonic)
        _REGISTRY[self].result.update(
            status="COLLECTION_COMPLETE_WITH_UNRESOLVED_EFFECTS", teacher_collection_admitted=True
        )
        raise RuntimeError("publication failed after body")

    monkeypatch.setattr(NativeCollectionApplication, "run_from_worker", bad_publication)
    with pytest.raises(RuntimeError, match="publication failed after body"):
        app.execute_once()
    result = load_json(app.output / "collection-result.json")
    assert result["status"] == "COLLECTION_PARTIAL" and not result["teacher_collection_admitted"]
    # The existing RGBD route classifies this injected body RuntimeError before
    # the worker reaches publication. Retain that exact job and attempt outcome.
    assert result["worker_snapshot"]["job"]["status"] == "BLOCKED_BY_ENV"
    assert result["worker_snapshot"]["job"]["error_message"] == "publication failed after body"
    assert len(result["worker_snapshot"]["attempts"]) == 1
    attempt = result["worker_snapshot"]["attempts"][0]
    assert attempt["result"] == "BLOCKED_BY_ENV"
    assert attempt["error"] == "RuntimeError: publication failed after body"
    assert result["qualified_group_score"] is None and not result["execution_admitted"]


def test_collection_owner_close_failure_preserves_final_failure(tmp_path, monkeypatch):
    app = application(tmp_path)
    app.prepare_once()
    live = _REGISTRY[app]
    owner = live.owner

    class BadClose:
        def __getattr__(self, name):
            return getattr(owner, name)

        def close(self):
            owner.close()
            raise OSError("owner close failed")

    live.owner = BadClose()
    monkeypatch.setattr(NativeCollectionApplication, "run_from_worker", software_complete_body)
    with pytest.raises(OSError, match="owner close failed"):
        app.execute_once()
    result = load_json(app.output / "collection-result.json")
    assert live.closed and result["status"] == "COLLECTION_PARTIAL"
    assert result["owner_closure"] == {"attempted": True, "completed": False}
    assert any(row["phase"] == "owner_close" for row in result["failures"])


def test_collection_cleanup_failures_preserve_all_and_close_once(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research import native_collection_application as module

    order = []

    def failure(phase):
        def invoke(*args):
            order.append(phase)
            raise OSError(phase)

        return invoke

    live = SimpleNamespace(
        recorder=SimpleNamespace(
            _write_original=lambda *a: None, freeze=failure("freeze"), __exit__=failure("detach")
        ),
        capture=SimpleNamespace(__exit__=failure("capture")),
        backend=SimpleNamespace(shutdown=failure("backend")),
        checks=[],
        consumptions=[],
        failures=[],
        progress={
            "recorder_entered": True,
            "capture_entered": True,
            "backend_initialization_attempted": True,
        },
    )
    primary = ValueError("original")
    assert module._close_body_resources(live, primary) is primary
    assert order == ["freeze", "detach", "capture", "backend"]
    assert len(live.failures) == 4 and all(row["role"] == "SECONDARY" for row in live.failures)
    app = application(tmp_path)
    monkeypatch.setattr(NativeCollectionApplication, "run_from_worker", software_complete_body)
    actual_save = module.save_exclusive

    def reject_final(path, value):
        if path.name == "collection-result.json":
            raise OSError("final receipt full disk")
        return actual_save(path, value)

    monkeypatch.setattr(module, "save_exclusive", reject_final)
    with pytest.raises(OSError, match="final receipt full disk"):
        app.execute_once()
    assert _REGISTRY[app].closed
    assert _REGISTRY[app].result["final_receipt_persisted"] is False
    assert not (app.output / "collection-result.json").exists()
