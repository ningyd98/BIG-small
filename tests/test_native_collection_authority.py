"""Private startup identity and live worker/lease tests; no actual simulation."""

import copy
import pickle
from dataclasses import replace
from datetime import UTC, datetime
from importlib import import_module, util
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
