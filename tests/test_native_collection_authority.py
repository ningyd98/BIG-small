"""Private startup identity and live worker/lease tests; no actual simulation."""

import copy
import json
import os
import pickle
import sqlite3
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager, nullcontext
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
            assert_guard_stop_clocks(recorder, backend, 4, "ABORTED")
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


def source_recorder(tmp_path, *, software_fixture=None):
    base, backend, capture, executor, _, original = software_fixture or recorder_fixture(tmp_path)
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
            assert_guard_stop_clocks(recorder, backend, 0, "COMPLETE")
    finally:
        owner.close()


def assert_guard_stop_clocks(recorder, backend, step, disposition, *, episode_id=None):
    episode_id = backend._episode_id if episode_id is None else episode_id
    intervals = {row["interval_id"]: row for row in recorder._intervals}
    purpose, = [row for row in intervals.values() if row["kind"] == "TERMINATION"]
    hold_command, stop_command = recorder._commands[-2:]
    assert [row["command_payload"]["type"] for row in (hold_command, stop_command)] == [
        "hold_current_joints", "emergency_stop",
    ]
    for command in (hold_command, stop_command):
        payload = command["command_payload"]
        assert payload["episode_id"] == episode_id
        assert payload["physics_step"] == step and payload["accepted"] is True
        assert command["effective_from_step"] == step + 1
        assert command["parent_interval_id"] == purpose["interval_id"]
        assert command["owner_action_span_id"] is None
    hold = intervals[hold_command["interval_id"]]
    stop = intervals[stop_command["interval_id"]]
    control = intervals[list(recorder.control_sources.values())[-1]["interval_id"]]
    assert purpose["start_step"] == purpose["end_step"] == step
    assert purpose["disposition"] == disposition
    # The recorder's MONOTONIC pairs and the owner's BOOTTIME brackets each
    # witness containment on their own clock.
    for first, second in (
        (purpose["start"], hold["start"]), (hold["end"], stop["start"]),
        (stop["start"], control["start"]), (control["end"], stop["end"]),
        (stop["end"], purpose["end"]),
    ):
        assert first[0] < second[0] and first[3] <= second[1]
    ids = [int(row["interval_id"].split("-")[1]) for row in (hold, stop, control)]
    ledger = backend.operation_ledger[-6:]
    assert [(row["operation_id"], row["kind"], row["phase"]) for row in ledger] == [
        (ids[0], "COMMAND", "BEGIN"), (ids[0], "COMMAND", "END"),
        (ids[1], "COMMAND", "BEGIN"), (ids[2], "CONTROL", "BEGIN"),
        (ids[2], "CONTROL", "END"), (ids[1], "COMMAND", "END"),
    ]
    assert all(row["episode_id"] == episode_id and row["physics_step"] == step
               for row in ledger)
    by_id = {row["operation_id"]: row for row in recorder.operational_events}
    hold_b, stop_b, control_b = [by_id[op]["bracket"] for op in ids]
    assert all(bracket["domain"] == detached(recorder.owner.domain)
               for bracket in (hold_b, stop_b, control_b))
    assert "CLOCK_BOOTTIME" in hold_b["domain"]["api"]
    assert hold_b["upper_ns"] <= stop_b["lower_ns"] <= control_b["lower_ns"]
    assert control_b["upper_ns"] <= stop_b["upper_ns"]


def test_nested_capture_failure_brackets_first_stop(tmp_path):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard
    from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration
    from cloud_edge_robot_arm.research.native_source_effect_graph import (
        validate_native_command_controls,
    )
    from cloud_edge_robot_arm.simulation.models import PhysicalScenarioConfig
    from tests.native_collection_source_graph import (
        install_original_shape_camera,
        install_software_reset_engine,
    )

    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    install_software_reset_engine(backend)
    install_original_shape_camera(backend, geometry_registration())
    backend._episode_id = None
    live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
    primary = RuntimeError("LIFT POST admission denied")
    try:
        with capture, recorder:
            backend.reset(PhysicalScenarioConfig.scenario("S01_NORMAL_STATIC", seed=0))
            recorder.require_clean_reset()
            with pytest.raises(RuntimeError) as caught:
                with _collection_guard(live, lambda event: None, 1024):
                    try:
                        with backend.capture_each_physics_step(max_captures=1):
                            with recorder.purpose("SETTLE"):
                                backend.step(1)
                            raise primary
                    finally:
                        # The sampler must brake before control returns to its caller.
                        assert backend.estop_engaged
            assert caught.value is primary
            commands = recorder._commands
            assert [row["command_payload"]["type"] for row in commands] == [
                "hold_current_joints", "emergency_stop",
            ]
            intervals = {row["interval_id"]: row for row in recorder._intervals}
            parents = {
                row["command_payload"]["type"]: row["parent_interval_id"] for row in commands
            }
            assert all(parent in intervals for parent in parents.values()), parents
            purpose, = [row for row in intervals.values() if row["kind"] == "TERMINATION"]
            assert set(parents.values()) == {purpose["interval_id"]}
            assert [row["owner_action_span_id"] for row in commands] == [None, None]
            assert [row["effective_from_step"] for row in commands] == [2, 2]
            assert purpose["start_step"] == purpose["end_step"] == backend.total_physics_steps == 1
            assert backend.execution_guard_events[-1]["kind"] == "FAILURE"
            assert backend.execution_guard_events[-1]["error"] == str(primary)
            assert_guard_stop_clocks(recorder, backend, 1, "ABORTED")
            recorder.freeze()
            raw = load_json(recorder.directory / "partial-originals.json")
            steps = {row["physics_step"]: row["post_state_payload"] for row in raw["physics"]}
            steps[0] = raw["reset"]["physics_state"]
            saved_intervals = {row["interval_id"]: row for row in raw["intervals"]}
            validate_native_command_controls(raw, saved_intervals, steps, expected_delay_steps=0)
    finally:
        owner.close()


def test_guard_failure_inside_action_separates_stop_from_controller_commands(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard
    from cloud_edge_robot_arm.simulation.models import JointCommand

    source = recorder_fixture(tmp_path)
    recorder, backend, capture, owner, original = source_recorder(tmp_path, software_fixture=source)
    live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
    primary = RuntimeError("controller checkpoint rejected")
    entered = []

    def check(event):
        if entered and event.kind == "RETURN" and event.phase == "BEFORE":
            raise primary

    def drive(**_):
        entered.append(True)
        backend.apply_joint_targets(JointCommand([0.2] * 7))
        try:
            backend.step(2)
        finally:
            assert backend.estop_engaged  # already stopped inside the executor

    monkeypatch.setattr(recorder.executor, "execute_attempt", drive)
    try:
        with capture, recorder:
            recorder.bind_source(source[-2], original)
            with pytest.raises(RuntimeError) as caught:
                with _collection_guard(live, check, 1024):
                    with backend.capture_each_physics_step(max_captures=2):
                        with recorder.purpose("SETTLE"):
                            backend.step(1)
                        recorder.execute_attempt(
                            contract=original.contract, step=original.contract.steps[0], attempt=1
                        )
            assert caught.value is primary
            assert caught.traceback[-1].name == "check"
            assert entered == [True]
            assert backend.total_physics_steps == 1
            action, = recorder._actions
            joint, hold, stop = recorder._commands
            assert joint["owner_action_span_id"] == action["span_id"]
            assert joint["parent_interval_id"] == action["interval_id"]
            assert (hold["owner_action_span_id"], stop["owner_action_span_id"]) == (None, None)
            assert (action["command_seq_start"], action["command_seq_end"]) == (1, 2)
            assert action["disposition"] == "PARTIAL"
            purpose, = [row for row in recorder._intervals if row["kind"] == "TERMINATION"]
            assert hold["parent_interval_id"] == purpose["interval_id"]
            assert stop["parent_interval_id"] == purpose["interval_id"]
            assert [cmd["effective_from_step"] for cmd in (joint, hold, stop)] == [2, 2, 2]
            assert_guard_stop_clocks(recorder, backend, 1, "ABORTED")
    finally:
        owner.close()


def test_guard_exception_exit_preserves_primary_and_secondary(tmp_path, monkeypatch):
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
            def bad_purpose(name, **kwargs):
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
                    assert live.failures[0]["error_type"] == "OSError"
        finally:
            owner.close()


@pytest.mark.parametrize("phase", ["entry", "exit"])
@pytest.mark.parametrize("body_failed", [False, True])
def test_guard_scope_failure_keeps_first_error_and_always_brakes(
    tmp_path, monkeypatch, phase, body_failed,
):
    from cloud_edge_robot_arm.research.native_collection_application import (
        _collection_guard,
        _remember,
    )

    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
    body_error = ValueError("admission failed")
    scope_error = LookupError("termination source failed")
    stop_error = OSError("stop feedback failed after braking")
    real_purpose, real_stop = recorder.purpose, backend.emergency_stop

    @contextmanager
    def faulted_purpose(name, **kwargs):
        if phase == "entry":
            raise scope_error
        with real_purpose(name, **kwargs) as purpose:
            try:
                yield purpose
            finally:
                raise scope_error

    def brake():
        real_stop()
        if body_failed:
            raise stop_error

    monkeypatch.setattr(recorder, "purpose", faulted_purpose)
    monkeypatch.setattr(backend, "emergency_stop", brake)
    try:
        with capture, recorder:
            with pytest.raises((ValueError, LookupError)) as caught:
                try:
                    with _collection_guard(live, lambda event: None, 1024):
                        with backend.capture_each_physics_step(max_captures=1):
                            if body_failed:
                                raise body_error
                except BaseException as error:
                    _remember(live, "collection_body", error)
                    raise
            assert caught.value is (body_error if body_failed else scope_error)
            assert caught.traceback[-1].name == (
                "test_guard_scope_failure_keeps_first_error_and_always_brakes"
                if body_failed else "faulted_purpose"
            )
            assert backend.estop_engaged and backend.total_physics_steps == 0
            assert [row["type"] for row in backend.command_records] == [
                "hold_current_joints", "emergency_stop",
            ]
            (source_error,) = [r for r in live.failures if r["phase"] == "termination_" + phase]
            assert source_error["role"] == ("SECONDARY" if body_failed else "PRIMARY")
            closure = backend.execution_guard_events[-1]
            assert closure["termination_" + phase + "_error_type"] == "LookupError"
            if body_failed:
                assert closure["kind"] == "FAILURE" and closure["error"] == str(body_error)
                assert closure["stop_error_type"] == "OSError"
                assert closure["stop_error"] == str(stop_error)
            first, = [r for r in live.failures if r["role"] == "PRIMARY"]
            assert first["error_type"] == type(caught.value).__name__
    finally:
        owner.close()


def test_guard_normal_exit_inside_handled_exception_and_repeated_stop(tmp_path):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    for explicit in (False, True):
        recorder, backend, capture, owner, _ = source_recorder(tmp_path / str(explicit))
        live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
        try:
            with capture, recorder:
                try:
                    raise ValueError("unrelated previously handled exception")
                except ValueError:
                    with _collection_guard(live, lambda event: None, 1024):
                        if explicit:
                            backend.emergency_stop()
                            backend.emergency_stop()
                            with pytest.raises(RuntimeError, match="closed"):
                                backend.step()
                backend._close_execution_guard(None)
                backend.emergency_stop()
                assert [row["type"] for row in backend.command_records] == [
                    "hold_current_joints", "emergency_stop",
                ]
                assert backend.execution_guard_events[-1] == {"kind": "CLOSED", "physics_step": 0}
                assert_guard_stop_clocks(recorder, backend, 0, "COMPLETE")
                assert backend.total_physics_steps == 0 and not live.failures
        finally:
            owner.close()


@pytest.mark.parametrize("phase", ["entry", "exit"])
def test_guard_reports_real_termination_interval_write_failure(tmp_path, monkeypatch, phase):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
    fault = OSError("termination interval clock unavailable")
    real_new, real_close = recorder._new_interval, recorder._close_interval

    def allocate(interval_id, kind, step, sim_time):
        if phase == "entry" and kind == "TERMINATION":
            raise fault
        return real_new(interval_id, kind, step, sim_time)

    def finish(row, error=None):
        if phase == "exit" and row["kind"] == "TERMINATION":
            raise fault
        return real_close(row, error)

    monkeypatch.setattr(recorder, "_new_interval", allocate)
    monkeypatch.setattr(recorder, "_close_interval", finish)
    try:
        with capture, recorder:
            with pytest.raises(OSError) as caught:
                with _collection_guard(live, lambda event: None, 1024):
                    pass
            assert caught.value is fault
            assert backend.estop_engaged and backend.total_physics_steps == 0
            assert [row["type"] for row in backend.command_records] == [
                "hold_current_joints", "emergency_stop",
            ]
            assert recorder._audit_failures == ["OSError: termination interval clock unavailable"]
            assert live.failures[0]["phase"] == "termination_" + phase
            terminal = backend.execution_guard_events[-1]
            assert terminal["kind"] == "FAILURE" and terminal["error"] == str(fault)
            assert terminal["phase"] == "termination_" + phase
            backend.emergency_stop()
            assert len(backend.command_records) == 2
    finally:
        owner.close()


@pytest.mark.parametrize("fault,step", [("engine", 0), ("capture_observer", 1)])
def test_guard_brackets_stop_on_inner_engine_or_observer_error(tmp_path, monkeypatch, fault, step):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
    primary = ValueError(f"{fault} source fault")

    def reject(*args):
        raise primary

    if fault == "engine":
        monkeypatch.setattr(backend._mujoco, "mj_step", reject)
    else:
        monkeypatch.setattr(recorder.application, "check_active", reject)
    try:
        with capture, recorder:
            with pytest.raises(ValueError) as caught:
                with _collection_guard(live, lambda event: None, 1024):
                    with backend.capture_each_physics_step(max_captures=2):
                        with recorder.purpose("SETTLE"):
                            try:
                                backend.step(2)
                            finally:
                                assert backend.estop_engaged
            assert caught.value is primary and caught.traceback[-1].name == "reject"
            assert backend.total_physics_steps == step
            closure = backend.execution_guard_events[-1]
            assert closure["kind"] == "FAILURE" and closure["error"] == str(primary)
            if fault == "capture_observer":
                assert backend.operation_observer_failures
                assert recorder.failures[0]["phase"] == "source_observer"
            assert_guard_stop_clocks(recorder, backend, step, "ABORTED")
    finally:
        owner.close()


def test_foreign_guard_fault_brakes_when_owner_recorder_rejects_thread(tmp_path):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
    try:
        with capture, recorder:
            with _collection_guard(live, lambda event: None, 1024):
                with ThreadPoolExecutor(max_workers=1) as pool:
                    foreign = pool.submit(backend.step)
                    with pytest.raises(RuntimeError, match="another thread"):
                        foreign.result(timeout=5)
                assert backend.estop_engaged
                with pytest.raises(RuntimeError, match="closed"):
                    backend.step()
            assert backend.total_physics_steps == 0
            assert [row["type"] for row in backend.command_records] == [
                "hold_current_joints", "emergency_stop",
            ]
            closure = backend.execution_guard_events[-1]
            assert closure["kind"] == "FAILURE" and "another thread" in closure["error"]
            assert "owner thread" in closure["termination_entry_error"]
            assert live.failures[0]["phase"] == "termination_entry"
            assert backend.operation_observer_failures
    finally:
        owner.close()


@pytest.mark.parametrize("phase", ["entry", "exit"])
def test_guard_termination_recorder_cannot_reenter_backend(tmp_path, monkeypatch, phase):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
    real_purpose = recorder.purpose

    @contextmanager
    def reenter(kind, **kwargs):
        with real_purpose(kind, **kwargs) as purpose:
            if phase == "entry":
                backend.emergency_stop()
            yield purpose
            if phase == "exit":
                backend.hold_current_joints()

    monkeypatch.setattr(recorder, "purpose", reenter)
    try:
        with capture, recorder:
            with pytest.raises(RuntimeError, match="guard callback"):
                with _collection_guard(live, lambda event: None, 1024):
                    pass
            assert backend.estop_engaged and backend.total_physics_steps == 0
            assert [row["type"] for row in backend.command_records] == [
                "hold_current_joints", "emergency_stop",
            ]
            assert live.failures[0]["phase"] == "termination_" + phase
    finally:
        owner.close()


@pytest.fixture
def recorded_stop(tmp_path):
    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    with closing(owner), capture, recorder:
        yield SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})


def recorder_boundary_state(recorder):
    fields = (
        "operational_events", "_pending", "capture_receipts", "_operations", "_intervals",
        "_record_seq", "_clock_seq", "_purpose_seq", "_purpose_stack", "_purpose_allocations",
        "_action_stack", "_interrupted_action_ends", "_physics", "_commands", "_actions",
        "_frames", "_frame_aux", "_joins", "_allocated_actions", "_allocated_frames", "_controls",
        "control_sources", "_reset_count", "_reset_metadata", "_reset_result", "_previous_state",
        "_render_attempts", "_render_overflow_count", "_first_unrecorded_capture", "render_passes",
        "_sample_slot", "_capture_roles", "inventory", "frame_sources", "bytes_written",
        "failures", "_audit_failures",
    )
    return {name: detached(getattr(recorder, name)) for name in fields}


@pytest.mark.parametrize("kind", ["RESET", "CONTROL", "PHYSICS", "COMMAND", "CAPTURE"])
@pytest.mark.parametrize("phase", ["BEGIN", "END"])
@pytest.mark.parametrize("active", [True, False], ids=["foreign", "inactive_owner"])
def test_recorder_owner_rejects_every_boundary_before_mutation(tmp_path, kind, phase, active):
    from cloud_edge_robot_arm.simulation.mujoco.backend import BackendOperationBoundary

    recorder, backend, capture, clock, _ = source_recorder(tmp_path)
    checks = []
    recorder.application.check_active = lambda: checks.append(threading.get_ident())
    event = BackendOperationBoundary(
        27, kind, phase, backend._episode_id, 0, 0.0, {}, {
            "control_state": {"physics_step": 0}, "pass_state_hashes": ["a" * 64],
        } if phase == "END" else None, None, None,
    )
    with closing(clock), capture, recorder if active else nullcontext():
        clock._check()
        initial = recorder_boundary_state(recorder)
        with pytest.raises(RuntimeError, match="recorder requires its active actual owner thread"):
            if active:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(recorder._on_boundary, event).result(timeout=3)
            else:
                recorder._on_boundary(event)
        assert recorder_boundary_state(recorder) == initial
        assert checks == [] and not clock._events and not clock._receipts
        clock._check()


def test_recorder_owner_preserves_pending_token_from_foreign_end(recorded_stop, monkeypatch):
    live = recorded_stop
    recorder, backend = live.recorder, live.backend
    clock = recorder.owner
    source = backend._operation_observer
    attempted, rejected = [], []

    def observe(event):
        if event.kind == "CONTROL" and event.phase == "END":
            row, token = recorder._pending[event.operation_id]
            before = recorder_boundary_state(recorder)
            with ThreadPoolExecutor(max_workers=1) as pool:
                try:
                    pool.submit(recorder._on_boundary, event).result(timeout=3)
                except BaseException as error:
                    rejected.append(str(error))
            attempted.append((
                recorder_boundary_state(recorder) == before,
                recorder._pending.get(event.operation_id) == (row, token), token,
            ))
        source(event)

    monkeypatch.setattr(backend, "_operation_observer", observe)
    backend._apply_control()
    assert rejected == ["recorder requires its active actual owner thread"]
    (unchanged, same_token, token), = attempted
    assert unchanged and same_token and not recorder._pending
    completed, = recorder.operational_events
    assert completed["token"] == completed["bracket"]["event_identity"] == token.event_identity
    assert completed["bracket"] == detached(clock._event_record(token).receipt)
    assert not recorder.failures and not recorder._audit_failures
    assert not backend.operation_observer_failures
    clock._check()


def test_recorder_owner_valid_thread_audits_closed_clock(recorded_stop):
    recorder, backend = recorded_stop.recorder, recorded_stop.backend
    recorder.owner.close()
    backend._apply_control()
    row, = recorder.operational_events
    assert row["token"] is row["bracket"] is None
    assert row["error_type"] == "OperationalTimeError"
    assert row["error"] == "OperationalTimeError: operational owner is not live"
    assert recorder.failures[0] == {
        "phase": "source_observer", "error_type": "OperationalTimeError", "error": row["error"],
    }
    assert backend.operation_observer_failures[0]["observer_error_type"] == "OperationalTimeError"
    assert row["operation_id"] in recorder.control_sources
    assert not recorder._pending and not recorder.owner._events


@pytest.mark.parametrize("first_fails", [False, True])
def test_recorder_owner_foreign_control_write_retains_only_owned_sources(
    recorded_stop, monkeypatch, first_fails,
):
    import numpy as np

    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    live = recorded_stop
    backend, recorder = live.backend, live.recorder
    clock = recorder.owner
    clock._check()
    domain = clock.domain
    owner = threading.get_ident()
    reached, sampled, release = (threading.Event() for _ in range(3))
    writes = []
    fault = OSError("foreign physical CONTROL write failed")

    class InstrumentedControl(np.ndarray):
        def __setitem__(self, key, value):
            if self is control and key == slice(None, 7):
                writes.append((threading.get_ident(), float(self[0])))
                if threading.get_ident() != owner:
                    reached.set()
                    assert release.wait(3)
                    if first_fails:
                        raise fault
            super().__setitem__(key, value)

    def release_writer():
        try:
            assert sampled.wait(3)
        finally:
            release.set()

    backend._data.ctrl[0] = 0.75
    control = backend._data.ctrl.view(InstrumentedControl)
    monkeypatch.setattr(backend._data, "ctrl", control)
    before = recorder_boundary_state(recorder)
    with _collection_guard(live, lambda event: None, 1024):
        with ThreadPoolExecutor(max_workers=2) as pool:
            freeing = pool.submit(release_writer)
            writer = pool.submit(backend.step)
            try:
                assert reached.wait(3)
                assert backend.estop_engaged and control[0] == 0.75
                mid_state = recorder_boundary_state(recorder)
                clock_was_open = not clock._closed
            finally:
                sampled.set()
            freeing.result(timeout=3)
            with pytest.raises(RuntimeError, match="another thread"):
                writer.result(timeout=3)
        after_foreign = recorder_boundary_state(recorder)
        assert clock_was_open and not clock._closed
        assert mid_state == after_foreign == before
        assert not clock._events and not clock._receipts
        clock._check()
        if first_fails:
            assert control[0] == 0.75
            backend.emergency_stop()
    assert clock.domain is domain and not clock._closed
    clock._check()
    assert backend.total_physics_steps == 0 and backend.estop_engaged and control[0] == 0
    assert len(writes) == (2 if first_fails else 1) and writes[0][0] != owner
    assert writes[0][1] == 0.75
    assert [row["type"] for row in backend.command_records] == [
        "hold_current_joints", "emergency_stop",
    ] * len(writes)
    first, = backend.execution_guard_events
    rejection = "recorder requires its active actual owner thread"
    assert first["phase"] == "backend"
    assert first["error"] == "execution guard belongs to another thread"
    assert first["termination_entry_error"] == rejection
    refused = [
        (row["operation_id"], row["kind"], row["phase"])
        for row in backend.operation_observer_failures if row["observer_error"] == rejection
    ]
    original = [
        (row["operation_id"], row["kind"], row["phase"]) for row in backend.operation_ledger
    ]
    assert len(backend.operation_observer_failures) == len(refused) == 6
    assert refused == original[:6]
    control_end = next(row for row in backend.operation_ledger[:6]
                       if (row["kind"], row["phase"]) == ("CONTROL", "END"))
    assert control_end["error_type"] == ("OSError" if first_fails else None)
    assert control_end["error"] == (str(fault) if first_fails else None)
    assert not recorder.failures and not recorder._audit_failures and not recorder._pending
    if not first_fails:
        assert "stop_error" not in first
        assert recorder_boundary_state(recorder) == before
        return
    assert first["stop_error_type"] == "OSError" and first["stop_error"] == str(fault)
    assert writes[1] == (owner, 0.75)
    assert_guard_stop_clocks(recorder, backend, 0, "COMPLETE")
    assert [cmd["command_seq"] for cmd in backend.command_records] == [1, 2, 3, 4]
    assert [cmd["command_seq"] for cmd in recorder._commands] == [3, 4]
    assert [cmd["command_payload"] for cmd in recorder._commands] == backend.command_records[2:]
    events = recorder.operational_events
    assert [(r["operation_id"], r["kind"]) for r in events] == [
        (operation_id, kind) for operation_id, kind, phase in original[6:] if phase == "BEGIN"
    ]
    assert [r["sequence"] for r in events] == [1, 2, 3]
    assert [r["operation_id"] for r in events] == [4, 5, 6]
    control_source, = recorder.control_sources.values()
    assert control_source["operation_id"] == events[-1]["operation_id"]
    assert control_source["physics_step"] == backend.total_physics_steps == 0
    assert control_source["control_state"] == detached(backend._build_actuator_observation())
    assert control_source["control_state"]["physics_step"] == 1
    assert control_source["control_state"]["control_rad"] == list(control[:7])
    assert recorder._controls[1] == (control_source["interval_id"], control_source["control_state"])
    assert len({r["token"] for r in events}) == len(clock._events) == len(clock._receipts) == 3
    for row in events:
        issued, = [
            event for event in clock._events.values() if event.token.event_identity == row["token"]
        ]
        assert issued.token.domain is domain and issued.token.kind == row["kind"]
        assert issued.receipt is not None
        assert clock._receipt_record(issued.receipt).token is issued.token
        assert row["bracket"] == detached(issued.receipt)
        assert row["token"] == row["bracket"]["event_identity"]
        assert row["begin_step"] == row["end_step"] == 0
        assert row["episode_id"] == backend._episode_id
        assert row["error_type"] is row["error"] is None


@pytest.mark.parametrize("after_exit", [False, True])
@pytest.mark.parametrize("point", ["hold", "control"])
def test_incomplete_guard_brake_retries_under_a_fresh_parent(
    recorded_stop, monkeypatch, after_exit, point,
):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    live = recorded_stop
    backend, recorder = live.backend, live.recorder
    name = "hold_current_joints" if point == "hold" else "_apply_stop_control"
    original = getattr(backend, name)
    error = OSError("physical brake failed at " + point)
    backend._data.ctrl[0] = 1

    def fail_once():
        monkeypatch.setattr(backend, name, original)
        raise error

    def retry():
        backend.emergency_stop()
        assert backend.estop_engaged and backend._data.ctrl[0] == 0
        with pytest.raises(RuntimeError, match="closed"):
            backend.step()

    monkeypatch.setattr(backend, name, fail_once)
    with _collection_guard(live, lambda event: None, 1024):
        with pytest.raises(OSError) as caught:
            backend.emergency_stop()
        assert caught.value is error
        assert backend.estop_engaged is (point == "control")
        assert backend._data.ctrl[0] == 1
        if not after_exit:
            retry()
    if after_exit:
        retry()
    backend.emergency_stop()
    assert backend.total_physics_steps == 0
    assert [row["type"] for row in backend.command_records] == (
        [] if point == "hold" else ["hold_current_joints", "emergency_stop"]
    ) + ["hold_current_joints", "emergency_stop"]
    purposes = [r for r in recorder._intervals if r["kind"] == "TERMINATION"]
    assert [r["disposition"] for r in purposes] == ["ABORTED", "COMPLETE"]
    assert purposes[0]["end"][3] <= purposes[1]["start"][1]
    assert all(
        c["parent_interval_id"] == purposes[1]["interval_id"] for c in recorder._commands[-2:]
    )
    assert all(r["kind"] != "CLOSED" for r in backend.execution_guard_events)
    first = backend.execution_guard_events[0]
    assert first["kind"] == "FAILURE" and first["error"] == str(error)


def test_manual_brake_and_later_body_exception_have_separate_originals(recorded_stop):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    live = recorded_stop
    primary = ValueError("controller rethrew only after requesting a public stop")
    with pytest.raises(ValueError) as caught:
        with _collection_guard(live, lambda event: None, 1024):
            try:
                raise primary
            except ValueError:
                live.backend.emergency_stop()
                assert live.backend.execution_guard_events[-1]["kind"] == "CLOSED"
                raise
    assert caught.value is primary
    assert [r["kind"] for r in live.backend.execution_guard_events] == ["CLOSED", "FAILURE"]
    assert live.backend.execution_guard_events[-1]["error"] == str(primary)
    assert_guard_stop_clocks(live.recorder, live.backend, 0, "COMPLETE")


def test_late_cause_is_retained_once_at_the_guard_event_limit(recorded_stop):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    live = recorded_stop
    backend = live.backend
    first = ValueError("initial controller fault")
    second = LookupError("subsequent controller fault")
    with pytest.raises(LookupError) as caught:
        with _collection_guard(live, lambda event: None, 1024):
            for _ in range(1023):
                backend._check_execution_guard("RETURN", "BEFORE")
            backend.stop_after_failure(first)
            backend.stop_after_failure(second)
            raise second
    assert caught.value is second and len(backend.execution_guard_events) == 1024
    terminal = backend.execution_guard_events[-1]
    assert terminal["kind"] == "FAILURE" and terminal["error"] == str(first)
    assert terminal["closure"]["error"] == str(second)
    assert "subsequent_failure" not in terminal["closure"]
    assert_guard_stop_clocks(live.recorder, backend, 0, "ABORTED")


@pytest.mark.parametrize("point", ["hold", "control"])
@pytest.mark.parametrize("failures", [0, 1, 2])
def test_concurrent_public_stop_reports_in_progress_until_real_write(
    recorded_stop, monkeypatch, point, failures,
):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    backend = recorded_stop.backend
    name = "hold_current_joints" if point == "hold" else "_apply_stop_control"
    actual = getattr(backend, name)
    barrier = threading.Barrier(3)
    done = [threading.Event(), threading.Event()]
    attempts = writers = peak = 0
    fault = OSError("incomplete physical write")
    backend._data.ctrl[0] = 0.75

    def write():
        nonlocal attempts, writers, peak
        attempts += 1
        writers += 1
        peak = max(peak, writers)
        try:
            if attempts == 1:
                barrier.wait(timeout=3)
                assert all(event.wait(3) for event in done)
            if attempts <= failures:
                raise fault
            actual()
        finally:
            writers -= 1

    def compete(index):
        try:
            barrier.wait(timeout=3)
            try:
                backend.emergency_stop()
            except RuntimeError as error:
                return str(error), backend.estop_engaged, backend._data.ctrl[0]
            return None, backend.estop_engaged, backend._data.ctrl[0]
        finally:
            done[index].set()

    monkeypatch.setattr(backend, name, write)
    with _collection_guard(recorded_stop, lambda event: None, 1024):
        with ThreadPoolExecutor(max_workers=2) as pool:
            calls = [pool.submit(compete, index) for index in range(2)]
            try:
                for _ in range(failures):
                    with pytest.raises(OSError) as caught:
                        backend.emergency_stop()
                    assert caught.value is fault and backend._data.ctrl[0] == 0.75
                backend.emergency_stop()
            finally:
                for event in done:
                    event.set()
            outcomes = [call.result(timeout=3) for call in calls]
        assert all(message and "in progress" in message for message, _, _ in outcomes), outcomes
        assert all(latched == (point == "control") and control == 0.75
                   for _, latched, control in outcomes)
        assert backend.estop_engaged and backend._data.ctrl[0] == 0
        backend.emergency_stop()
    backend.emergency_stop()
    assert peak == 1 and attempts == failures + 1 and backend.total_physics_steps == 0
    scopes = [r for r in recorded_stop.recorder._intervals if r["kind"] == "TERMINATION"]
    assert [r["disposition"] for r in scopes] == ["ABORTED"] * failures + ["COMPLETE"]
    assert [r["type"] for r in backend.command_records] == (
        ["hold_current_joints", "emergency_stop"] * (failures + 1 if point == "control" else 1)
    )


@pytest.mark.parametrize("public", [True, False])
def test_recursive_public_stop_cannot_reuse_the_internal_brake(recorded_stop, monkeypatch, public):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    backend = recorded_stop.backend
    actual = backend.hold_current_joints
    calls, outcome = [], []

    def hold():
        calls.append("hold")
        if len(calls) == 1:
            try:
                backend.emergency_stop()
            except RuntimeError as error:
                outcome.append(str(error))
            else:
                outcome.append("returned before hold")
        actual()

    monkeypatch.setattr(backend, "hold_current_joints", hold)
    with _collection_guard(recorded_stop, lambda event: None, 1024):
        if public:
            backend.emergency_stop()
    assert len(outcome) == len(calls) == 1 and "in progress" in outcome[0], (calls, outcome)
    assert_guard_stop_clocks(recorded_stop.recorder, backend, 0, "COMPLETE")


def test_guard_failure_snapshot_allows_another_stop_to_report_in_progress(
    recorded_stop, monkeypatch,
):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    backend = recorded_stop.backend
    started, finished = threading.Event(), threading.Event()
    observed, outcome = [], []
    actual = backend.current_physics_observation
    primary = ValueError("controller state could not be used")

    def snapshot():
        if not started.is_set():
            started.set()
            observed.append(finished.wait(2))
        return actual()

    def compete():
        try:
            assert started.wait(3)
            try:
                backend.emergency_stop()
            except RuntimeError as error:
                outcome.append(str(error))
        finally:
            finished.set()

    monkeypatch.setattr(backend, "current_physics_observation", snapshot)
    with ThreadPoolExecutor(max_workers=1) as pool:
        contender = pool.submit(compete)
        with pytest.raises(ValueError) as caught:
            with _collection_guard(recorded_stop, lambda event: None, 1024):
                raise primary
        contender.result(timeout=3)
    assert caught.value is primary and observed == [True]
    assert len(outcome) == 1 and "in progress" in outcome[0]
    assert_guard_stop_clocks(recorded_stop.recorder, backend, 0, "ABORTED")


def test_owner_retries_after_foreign_writer_reports_incomplete_brake(recorded_stop, monkeypatch):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    backend = recorded_stop.backend
    first_hold, owner_observed = threading.Event(), threading.Event()
    actual = backend.hold_current_joints

    def fail_hold():
        monkeypatch.setattr(backend, "hold_current_joints", actual)
        first_hold.set()
        assert owner_observed.wait(3)
        raise OSError("foreign hold failed")

    monkeypatch.setattr(backend, "hold_current_joints", fail_hold)
    with _collection_guard(recorded_stop, lambda event: None, 1024):
        with ThreadPoolExecutor(max_workers=1) as pool:
            foreign = pool.submit(backend.step)
            try:
                assert first_hold.wait(3)
                with pytest.raises(RuntimeError, match="in progress"):
                    backend.emergency_stop()
                assert not backend.estop_engaged
            finally:
                owner_observed.set()
            with pytest.raises(RuntimeError, match="another thread"):
                foreign.result(timeout=3)
        backend.emergency_stop()
    first, = backend.execution_guard_events
    assert first["kind"] == "FAILURE" and first["stop_error"] == "foreign hold failed"
    assert "owner thread" in first["termination_entry_error"]
    assert backend.estop_engaged and backend.total_physics_steps == 0
    assert_guard_stop_clocks(recorded_stop.recorder, backend, 0, "COMPLETE")


@pytest.mark.parametrize("boundary", ["guard", "shutdown"])
@pytest.mark.parametrize("point", ["hold", "control_end"])
@pytest.mark.parametrize("first_fails", [False, True])
def test_teardown_keeps_foreign_brake_and_audit_alive(
    recorded_stop, monkeypatch, boundary, point, first_fails,
):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    live = recorded_stop
    backend = live.backend
    clock = live.recorder.owner
    clock._check()
    initial_recorder = recorder_boundary_state(live.recorder)
    blocked, closing, release = (threading.Event() for _ in range(3))
    finished = threading.Event()
    observed, captured = [], []
    original_camera, original_data = backend._camera, backend._data
    episode_id = backend._episode_id
    camera_closed = []
    monkeypatch.setattr(original_camera, "close", lambda: camera_closed.append(1), raising=False)
    source, hold = backend._operation_observer, backend.hold_current_joints
    backend._data.ctrl[0] = 0.75

    def pause():
        blocked.set()
        assert release.wait(3)
        if first_fails:
            raise OSError("first physical hold or END failed")

    def paused_hold():
        if not blocked.is_set() and point == "hold":
            pause()
        hold()

    def observed_source(event):
        try:
            source(event)
        finally:
            if not blocked.is_set() and point == "control_end" and (
                event.kind, event.phase
            ) == ("CONTROL", "END"):
                pause()

    def foreign_step():
        with pytest.raises(RuntimeError, match="another thread"):
            backend.step()
        captured.extend(backend.execution_guard_events)

    def release_independently():
        try:
            assert closing.wait(3)
            early = finished.wait(0.05)
            observed.append((
                early, backend._camera is original_camera, backend._data is original_data,
                live.progress.get("guard_exited", False), backend._operation_observer
                is observed_source, backend.estop_engaged, original_data.ctrl[0],
            ))
        finally:
            release.set()

    monkeypatch.setattr(backend, "hold_current_joints", paused_hold)
    monkeypatch.setattr(backend, "_operation_observer", observed_source)
    with ThreadPoolExecutor(max_workers=2) as pool:
        releasing = pool.submit(release_independently)
        with _collection_guard(live, lambda event: None, 1024):
            writer = pool.submit(foreign_step)
            assert blocked.wait(3)
            live_at_barrier = not clock._closed
            recorder_at_barrier = recorder_boundary_state(live.recorder)
            closing.set()
            if boundary == "shutdown":
                backend.shutdown()
                finished.set()
        finished.set()
        releasing.result(timeout=3)
        writer.result(timeout=3)
    assert observed == [(False, True, True, False, True,
                         point == "control_end", 0.0 if point == "control_end" else 0.75)]
    assert live_at_barrier and not clock._closed
    clock._check()
    assert recorder_at_barrier == initial_recorder
    assert live.progress["guard_exited"]
    assert captured[0]["error"] == "execution guard belongs to another thread"
    assert "owner thread" in captured[0]["termination_entry_error"]
    assert backend.estop_engaged and original_data.ctrl[0] == 0
    assert [command["type"] for command in backend.command_records] == [
        "hold_current_joints", "emergency_stop",
    ]
    if point == "hold" and first_fails:
        assert captured[0]["stop_error"] == "first physical hold or END failed"
        assert_guard_stop_clocks(live.recorder, backend, 0, "COMPLETE", episode_id=episode_id)
    else:
        assert recorder_boundary_state(live.recorder) == initial_recorder
    if point == "control_end" and first_fails:
        assert any(r["observer_error"] == "first physical hold or END failed"
                   for r in backend.operation_observer_failures)
    backend.shutdown()
    backend.shutdown()
    assert camera_closed == [1] and backend._data is backend._model is None


def test_teardown_recursive_shutdown_keeps_its_own_writer_alive(recorded_stop, monkeypatch):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    backend = recorded_stop.backend
    hold = backend.hold_current_joints
    outcome = []
    monkeypatch.setattr(backend._camera, "close", lambda: None, raising=False)

    def guarded_hold():
        try:
            backend.shutdown()
        except RuntimeError as error:
            outcome.append(str(error))
        hold()

    monkeypatch.setattr(backend, "hold_current_joints", guarded_hold)
    with _collection_guard(recorded_stop, lambda event: None, 1024):
        pass
    assert len(outcome) == 1 and "in progress" in outcome[0]
    assert_guard_stop_clocks(recorded_stop.recorder, backend, 0, "COMPLETE")
    backend.shutdown()
    assert backend._data is backend._model is None


@pytest.mark.parametrize("guarded", [False, True])
def test_teardown_without_recorder_preserves_repeat_shutdown(guarded):
    from tests.test_visual_raw_recorder_v3 import software_backend

    backend = software_backend()
    closed = []
    backend._camera = SimpleNamespace(close=lambda: closed.append(backend.total_physics_steps))
    if guarded:
        with backend.enforce_execution_guard(lambda event: None):
            pass
    backend.shutdown()
    backend.shutdown()
    assert closed == [0] and backend._data is backend._model is backend._camera is None
    assert [row["type"] for row in backend.command_records] == (
        ["hold_current_joints", "emergency_stop"] if guarded else []
    )


def test_teardown_timeout_and_foreign_shutdown_preserve_live_writer(recorded_stop, monkeypatch):
    from cloud_edge_robot_arm.research.native_collection_application import (
        _collection_guard,
        _settle_body_guard,
    )
    from cloud_edge_robot_arm.simulation.mujoco import backend as backend_module

    live = recorded_stop
    backend = live.backend
    at_hold, checked, release = (threading.Event() for _ in range(3))
    hold = backend.hold_current_joints
    camera = backend._camera
    closes = []
    monkeypatch.setattr(camera, "close", lambda: closes.append(1), raising=False)
    monkeypatch.setattr(backend_module, "_GUARD_FINISH_TIMEOUT_S", 0.03)

    def pause():
        at_hold.set()
        assert release.wait(3)
        hold()

    def check_foreign_shutdown_then_release():
        try:
            assert at_hold.wait(3)
            with pytest.raises(RuntimeError, match="owner thread"):
                backend.shutdown()
            assert checked.wait(3)
        finally:
            release.set()

    monkeypatch.setattr(backend, "hold_current_joints", pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        releasing = pool.submit(check_foreign_shutdown_then_release)
        try:
            with pytest.raises(RuntimeError, match="in progress"):
                with _collection_guard(live, lambda event: None, 1024):
                    writer = pool.submit(backend.step)
                    assert at_hold.wait(3)
            with pytest.raises(RuntimeError, match="in progress"):
                backend.shutdown()
            assert live.progress["guard_stop_pending"] and not live.progress.get("guard_exited")
            assert backend._data is not None and backend._camera is camera
            assert backend._operation_observer is not None
            assert not closes and not backend.estop_engaged
        finally:
            checked.set()
        releasing.result(timeout=3)
        with pytest.raises(RuntimeError, match="another thread"):
            writer.result(timeout=3)
    assert _settle_body_guard(live, None) is None
    assert live.progress["guard_exited"] and "guard_stop_pending" not in live.progress
    assert backend.estop_engaged and len(backend.command_records) == 2
    backend.shutdown()
    assert closes == [1] and backend._data is None


def test_teardown_foreign_fault_during_dedicated_hold_brakes_on_owner(recorded_stop, monkeypatch):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    live = recorded_stop
    backend = live.backend
    at_hold, foreign_done = threading.Event(), threading.Event()
    hold = backend.hold_current_joints
    hold_threads = []

    def pause():
        hold_threads.append(threading.get_ident())
        hold()
        if len(hold_threads) == 1:
            at_hold.set()
            assert foreign_done.wait(3)

    def fail_guard():
        try:
            assert at_hold.wait(3)
            with pytest.raises(RuntimeError, match="another thread"):
                backend.step()
        finally:
            foreign_done.set()

    monkeypatch.setattr(backend, "hold_current_joints", pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with _collection_guard(live, lambda event: None, 1024):
            foreign = pool.submit(fail_guard)
            cleanup = backend.protect_motion_guard_failure(ValueError("controller loss"))
            assert cleanup == (None, None)
            foreign.result(timeout=3)
            assert backend.estop_engaged and backend._data.ctrl[0] == 0
    assert hold_threads == [threading.get_ident()] * 2
    assert [c["type"] for c in backend.command_records] == [
        "hold_current_joints", "hold_current_joints", "emergency_stop",
    ]
    event, = backend.execution_guard_events
    assert event["phase"] == "backend"
    assert event["error"] == "execution guard belongs to another thread"
    assert_guard_stop_clocks(live.recorder, backend, 0, "ABORTED")


def test_teardown_failed_brake_defers_freeze_and_owner_until_explicit_recovery(
    tmp_path, monkeypatch,
):
    from cloud_edge_robot_arm.research.native_calibration_collection import (
        collect_native_calibration_once,
    )
    from cloud_edge_robot_arm.research.native_collection_application import (
        _close_body_resources,
        _collection_guard,
    )

    app = application(tmp_path)
    app.prepare_once()
    live = _REGISTRY[app]
    recorder, backend, capture, extra_owner, _ = source_recorder(tmp_path / "partial")
    extra_owner.close()
    recorder.owner = live.owner
    live.backend, live.recorder, live.capture = backend, recorder, capture
    fault = OSError("physical control still unavailable")
    control = backend._apply_control
    original_camera = backend._camera
    closed = []
    monkeypatch.setattr(original_camera, "close", lambda: closed.append(1), raising=False)
    monkeypatch.setattr(backend, "_apply_control", lambda: (_ for _ in ()).throw(fault))

    def blocked_body(self, worker, job, *, start_monotonic):
        live.worker_origin = worker._active_task_origin
        capture.__enter__()
        recorder.__enter__()
        live.progress.update(backend_initialized=True, backend_initialization_attempted=True,
                             capture_entered=True, recorder_entered=True)
        try:
            with _collection_guard(live, lambda event: None, 1024):
                pass
        except OSError as error:
            assert error is fault
            assert _close_body_resources(live, error) is error
            live.result = {"status": "COLLECTION_PARTIAL", "teacher_collection_admitted": False}
            raise

    monkeypatch.setattr(NativeCollectionApplication, "run_from_worker", blocked_body)
    monkeypatch.setattr(NativeCollectionApplication, "from_startup", lambda *args, **kwargs: app)
    with pytest.raises(RuntimeError, match="physical control still unavailable") as caught:
        collect_native_calibration_once(
            tmp_path / "protocol", assignment_id=live.assignment_id, output=app.output
        )
    initial = load_json(app.output / "collection-result.json")
    assert initial["cleanup_status"] == "PENDING_OWNER_GUARD_STOP"
    continuation = caught.value.finish_pending_cleanup
    assert initial["owner_closure"] == {"attempted": False, "completed": False}
    assert live.progress["guard_stop_pending"] and not live.progress.get("guard_exited")
    assert not live.progress.get("freeze_attempted") and not live.owner._closed and not live.closed
    assert backend._data is not None and backend._operation_observer is not None and not closed
    with pytest.raises(OSError, match="physical control still unavailable"):
        continuation()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(RuntimeError, match="thread"):
            pool.submit(continuation).result(timeout=3)
    monkeypatch.setattr(backend, "_apply_control", control)
    result = continuation()
    assert result["owner_closure"] == {"attempted": True, "completed": True}
    assert result["progress"]["guard_exited"] and result["progress"]["backend_shutdown_completed"]
    assert result["progress"]["freeze_completed"] and result["progress"]["recorder_close_completed"]
    assert closed == [1] and backend._data is None and live.owner._closed and live.closed
    assert load_json(app.output / "collection-result.json") == initial
    assert load_json(app.output / "collection-cleanup-result.json") == result


@pytest.mark.parametrize("missing", ["hold_current_joints", "_apply_control"])
def test_return_without_a_real_guard_brake_effect_remains_retryable(
    recorded_stop, monkeypatch, missing,
):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    backend = recorded_stop.backend
    original = getattr(backend, missing)

    def return_without_effect():
        monkeypatch.setattr(backend, missing, original)

    monkeypatch.setattr(backend, missing, return_without_effect)
    with _collection_guard(recorded_stop, lambda event: None, 1024):
        with pytest.raises(RuntimeError, match="did not complete"):
            backend.emergency_stop()
        backend.emergency_stop()
    scopes = [r for r in recorded_stop.recorder._intervals if r["kind"] == "TERMINATION"]
    assert [r["disposition"] for r in scopes] == ["ABORTED", "COMPLETE"]
    assert all(r["parent_interval_id"] == scopes[-1]["interval_id"]
               for r in recorded_stop.recorder._commands[-2:])
    assert backend.execution_guard_events[-1]["kind"] == "FAILURE"
    assert backend.estop_engaged and backend.total_physics_steps == 0


def test_retry_after_recorder_detach_still_brakes_and_keeps_source_failure(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard

    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    live = SimpleNamespace(backend=backend, recorder=recorder, failures=[], progress={})
    hold = backend.hold_current_joints

    def fail_once():
        monkeypatch.setattr(backend, "hold_current_joints", hold)
        raise OSError("first brake failed")

    monkeypatch.setattr(backend, "hold_current_joints", fail_once)
    with closing(owner), capture:
        with recorder, pytest.raises(OSError, match="first brake failed"):
            with _collection_guard(live, lambda event: None, 1024):
                pass
        with pytest.raises(RuntimeError, match="active actual owner thread"):
            backend.emergency_stop()
        backend.emergency_stop()
        assert backend.estop_engaged and backend.total_physics_steps == 0
        assert [row["type"] for row in backend.command_records] == [
            "hold_current_joints", "emergency_stop",
        ]
        assert [row["phase"] for row in backend.execution_guard_events] == [
            "stop", "termination_entry",
        ]


def test_ordinary_public_stop_keeps_existing_repetition_and_exception_semantics(monkeypatch):
    from tests.test_visual_raw_recorder_v3 import software_backend

    backend = software_backend()
    with backend.enforce_execution_guard(lambda event: None):
        pass
    backend.emergency_stop()
    assert [row["type"] for row in backend.command_records] == [
        "hold_current_joints", "emergency_stop", "hold_current_joints", "emergency_stop",
    ]
    failure = OSError("ordinary stop control failed")

    def reject():
        raise failure

    monkeypatch.setattr(backend, "_apply_stop_control", reject)
    with pytest.raises(OSError) as caught:
        backend.emergency_stop()
    assert caught.value is failure and backend.total_physics_steps == 0


@pytest.mark.parametrize("scenario", ["receipt", "base", "secondary_brake", "motion_guard"])
def test_lift_hold_reports_guard_cause_without_changing_controller_outcome(
    recorded_stop, monkeypatch, scenario,
):
    from cloud_edge_robot_arm.contracts import Pose
    from cloud_edge_robot_arm.research.native_collection_application import _collection_guard
    from cloud_edge_robot_arm.simulation.mujoco.skill_robot import MotionGuardViolation
    from tests.native_collection_source_graph import install_software_reset_engine

    live = recorded_stop
    robot = live.recorder.executor._robot
    backend = live.backend
    install_software_reset_engine(backend)
    robot._holding_object_id = "software-object"
    monkeypatch.setattr(backend, "get_tcp_pose", lambda: Pose(x=0.45, y=0.0, z=0.05))
    monkeypatch.setattr(robot, "_grasp_contacts", lambda: {"left": 1, "right": 1})
    before = robot._snapshot()
    moved = robot._result("LIFT", True, before, datetime.now(UTC), 0)
    monkeypatch.setattr(robot, "_move", lambda *args, **kwargs: moved)
    primary = (
        MotionGuardViolation("GRASP_LOST", "measured grasp lost") if scenario == "motion_guard"
        else BaseException("caller cancelled lift") if scenario == "base"
        else ValueError("hold input failed")
    )

    def reject():
        raise primary

    def brake_failure():
        raise OSError("stop CONTROL failed")

    monkeypatch.setattr(robot, "_motion_guard", lambda *args: reject)
    if scenario == "secondary_brake":
        monkeypatch.setattr(backend, "_apply_stop_control", brake_failure)
    # A persistent physical failure also rejects the owner’s independent teardown retry.
    closing_outcome = (
        pytest.raises(OSError, match="stop CONTROL failed")
        if scenario == "secondary_brake" else nullcontext()
    )
    with closing_outcome, _collection_guard(live, lambda event: None, 1024):
        if scenario == "base":
            with pytest.raises(BaseException) as caught:
                robot.lift(height_m=0.1)
            assert caught.value is primary and caught.traceback[-1].name == "reject"
        else:
            receipt = robot.lift(height_m=0.1)
            assert receipt.success is False and receipt.details["reason"] == str(primary)
            if scenario == "motion_guard":
                assert receipt.error_code == "GRASP_LOST"
                assert not backend.estop_engaged
                assert [r["type"] for r in backend.command_records] == ["hold_current_joints"]
                return
            assert receipt.error_code == "LIFT_HOLD_FAILED"
        assert backend.estop_engaged
    closure = next(row for row in backend.execution_guard_events if row["kind"] == "FAILURE")
    assert closure["kind"] == "FAILURE" and closure["error"] == str(primary)
    assert closure["phase"] == "controller"
    if scenario == "secondary_brake":
        assert closure["stop_error"] == "stop CONTROL failed"
        assert backend.execution_guard_events[-1]["phase"] == "stop"
        assert not live.progress.get("guard_exited")
    else:
        assert_guard_stop_clocks(live.recorder, backend, 0, "ABORTED")


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
