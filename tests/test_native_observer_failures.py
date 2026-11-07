"""Source failure/effect accounting regressions; only SOFTWARE_ONLY engines."""

from dataclasses import replace

import pytest

from cloud_edge_robot_arm.research.native_calibration_collection import load_json
from cloud_edge_robot_arm.research.native_collection_grounding import geometry_registration
from cloud_edge_robot_arm.research.native_full_horizon_originals import _Audit
from cloud_edge_robot_arm.research.native_full_horizon_recorder import NativeFullHorizonRecorder
from tests.native_collection_source_graph import (
    install_original_shape_camera,
    install_software_reset_engine,
)
from tests.test_native_collection_authority import application, source_recorder
from tests.test_visual_raw_recorder_v3 import software_backend


def test_reset_conversion_failure_vetoes_first_step_and_keeps_original(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.simulation.mujoco import backend as backend_module
    from cloud_edge_robot_arm.vision import top_grasp

    backend = software_backend()
    install_software_reset_engine(backend)
    calls, checked = [], []
    original_error = "RGB size must equal width * height * 3"

    def initialize(config):
        backend._config = config
        install_original_shape_camera(backend, geometry_registration())
        capture = backend._camera._capture

        def malformed_rgb(*args, **kwargs):
            frame, ids, labels, hashes = capture(*args, **kwargs)
            return replace(frame, rgb=frame.rgb[:-1]), ids, labels, hashes

        backend._camera._capture = malformed_rgb

    reset = backend.reset

    def record_reset(scenario):
        calls.append("reset")
        reset(scenario)

    def guard(*args, **kwargs):
        calls.append("guard")
        raise RuntimeError("SOFTWARE_ONLY guard sentinel after malformed reset")

    def forbidden(*args, **kwargs):
        calls.append("forbidden_step_or_sampler")
        raise AssertionError("conversion failure reached physical entry")

    require_clean_reset = NativeFullHorizonRecorder.require_clean_reset

    def observe_original_conversion(self):
        assert not self.failures and not self._audit_failures
        assert not backend.operation_observer_failures
        capture = self.operational_events[1]
        assert capture["kind"] == "CAPTURE" and capture["error_type"] is None
        interval = self._operations[capture["operation_id"]]["row"]
        assert interval["disposition"] == "ABORTED" and original_error in interval["error"]
        source = load_json(self.directory / self.frame_sources[capture["acquisition_id"]])
        assert source["frame"]["observation_payload"] is None
        assert self.render_accounting["exact_passes"] == 2
        checked.append(True)
        return require_clean_reset(self)

    monkeypatch.setattr(backend, "initialize", initialize)
    monkeypatch.setattr(backend, "reset", record_reset)
    monkeypatch.setattr(backend, "enforce_execution_guard", guard)
    monkeypatch.setattr(backend, "capture_each_physics_step", forbidden)
    monkeypatch.setattr(backend, "step", forbidden)
    monkeypatch.setattr(backend_module, "MuJoCoPhysicsBackend", lambda: backend)
    monkeypatch.setattr(top_grasp, "matches_calibrated_gripper", lambda *_args: True)
    monkeypatch.setattr(
        NativeFullHorizonRecorder, "require_clean_reset", observe_original_conversion
    )
    app = application(tmp_path)
    with pytest.raises(RuntimeError):
        app.execute_once()
    result = load_json(app.output / "collection-result.json")
    raw = load_json(app.output / "originals/partial-originals.json")
    assert checked == [True]
    assert result["status"] == "COLLECTION_PARTIAL" and result["physics_steps"] == 0
    assert result["owner_closure"]["completed"]
    assert result["render_passes"] == result["render_passes_lower_bound"] == 2
    assert result["render_count_status"] == "EXACT"
    acquisition = [row for row in raw["intervals"] if row["kind"] == "ACQUISITION"]
    assert len(acquisition) == 1 and acquisition[0]["disposition"] == "ABORTED"
    assert original_error in acquisition[0]["error"]
    source = load_json(app.output / "originals" / next(iter(raw["frame_sources"].values())))
    assert source["frame"]["observation_payload"] is None
    assert calls == ["reset"]
    assert "reset source" in result["worker_snapshot"]["job"]["error_message"]


def test_reset_source_failure_vetoes_first_step_and_keeps_partial(tmp_path, monkeypatch):
    assert callable(getattr(NativeFullHorizonRecorder, "require_clean_reset", None)), (
        "R452 reset source veto missing"
    )
    from cloud_edge_robot_arm.simulation.mujoco import backend as backend_module
    from cloud_edge_robot_arm.vision import top_grasp

    for case in ("write", "observer", "audit", "camera", "clean"):
        with monkeypatch.context() as patch:
            backend = software_backend()
            install_software_reset_engine(backend)
            calls = []

            def initialize(config, backend=backend, case=case):
                backend._config = config
                install_original_shape_camera(backend, geometry_registration())
                if case == "camera":

                    def broken_camera(*_args, **_kwargs):
                        raise RuntimeError("SOFTWARE_ONLY reset camera failed")

                    backend._camera._capture = broken_camera

            reset = backend.reset

            def record_reset(scenario, calls=calls, reset=reset):
                calls.append("reset")
                reset(scenario)

            def guard(*args, calls=calls, **kwargs):
                calls.append("guard")
                raise RuntimeError("SOFTWARE_ONLY stop after clean reset")

            def forbidden(*args, calls=calls, **kwargs):
                calls.append("forbidden_step_or_sampler")
                raise AssertionError("source failure reached physical entry")

            patch.setattr(backend, "initialize", initialize)
            patch.setattr(backend, "reset", record_reset)
            patch.setattr(backend, "enforce_execution_guard", guard)
            patch.setattr(backend, "capture_each_physics_step", forbidden)
            patch.setattr(backend, "step", forbidden)
            patch.setattr(backend_module, "MuJoCoPhysicsBackend", lambda backend=backend: backend)
            patch.setattr(top_grasp, "matches_calibrated_gripper", lambda *_args: True)
            write = NativeFullHorizonRecorder._write_blob
            boundary = NativeFullHorizonRecorder._on_boundary
            injected = []

            def fail_once(self, name, raw, case=case, injected=injected, write=write):
                if case == "write" and name.startswith("frames/") and not injected:
                    injected.append(case)
                    raise OSError("SOFTWARE_ONLY reset original write failed")
                return write(self, name, raw)

            def observed(self, event, case=case, injected=injected, boundary=boundary):
                boundary(self, event)
                if event.kind == "CAPTURE" and event.phase == "END" and not injected:
                    if case == "observer":
                        injected.append(case)
                        raise OSError("SOFTWARE_ONLY reset observer failed")
                    if case == "audit":
                        injected.append(case)
                        self._audit_failures.append("SOFTWARE_ONLY reset audit failed")

            patch.setattr(NativeFullHorizonRecorder, "_write_blob", fail_once)
            patch.setattr(NativeFullHorizonRecorder, "_on_boundary", observed)
            app = application(tmp_path / case)
            with pytest.raises(RuntimeError):
                app.execute_once()
            result = load_json(app.output / "collection-result.json")
            raw = load_json(app.output / "originals/partial-originals.json")
            assert result["status"] == "COLLECTION_PARTIAL" and result["physics_steps"] == 0
            if case == "camera":
                assert result["render_passes"] is None
                assert result["render_passes_lower_bound"] == 0
                assert result["render_count_status"] == "UNAVAILABLE"
            else:
                assert result["render_passes"] == result["render_passes_lower_bound"] == 2
                assert result["render_count_status"] == "EXACT"
            assert result["owner_closure"]["completed"] and result["failures"]
            assert not result["progress"].get("guard_entered")
            assert calls == (["reset", "guard"] if case == "clean" else ["reset"])
            if case != "clean":
                assert raw["failures"] or raw["audit_failures"] or raw["observer_failures"]
                error = result["worker_snapshot"]["job"]["error_message"]
                assert ("reset camera failed" if case == "camera" else "reset source") in error
                assert any(
                    "SOFTWARE_ONLY reset" in str(raw[key])
                    for key in ("failures", "audit_failures", "observer_failures")
                )


def test_returned_render_passes_survive_original_write_failure(tmp_path, monkeypatch):
    assert hasattr(NativeFullHorizonRecorder, "render_accounting"), (
        "R452 returned pass accounting missing"
    )
    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    install_original_shape_camera(backend, geometry_registration())
    events = []
    boundary = recorder._on_boundary

    def observed(event):
        events.append(event)
        boundary(event)

    monkeypatch.setattr(recorder, "_on_boundary", observed)
    try:
        with capture, recorder:
            backend._capture_cached_observed()
            recorder.capture()
            assert recorder.render_accounting["exact_passes"] == 5
            write = recorder._write_blob

            def fail_blob(name, raw):
                if name.endswith("rgb.png"):
                    raise OSError("SOFTWARE_ONLY returned-frame spool failed")
                return write(name, raw)

            monkeypatch.setattr(recorder, "_write_blob", fail_blob)
            recorder.capture()  # Backend retains observer failure; render already returned.
            assert recorder.failures and backend.operation_observer_failures
            accounting = recorder.render_accounting
            assert accounting["known_completed_passes"] == accounting["exact_passes"] == 8
            assert accounting["status"] == "EXACT" and accounting["attempt_count"] == 3
            with pytest.raises(RuntimeError, match="duplicate capture END"):
                recorder._on_boundary(events[-1])
            assert recorder.render_accounting == accounting
            monkeypatch.setattr(recorder, "_write_blob", write)
            recorder.freeze()
            raw = load_json(recorder.directory / "partial-originals.json")
            assert raw["render_accounting"] == accounting and raw["failures"]
    finally:
        owner.close()


def test_midcapture_failure_retains_lower_bound_not_exact_zero(tmp_path, monkeypatch):
    assert hasattr(NativeFullHorizonRecorder, "render_accounting"), (
        "R452 unknown pass accounting missing"
    )
    recorder, backend, capture, owner, _ = source_recorder(tmp_path)
    geometry = geometry_registration()
    install_original_shape_camera(backend, geometry)

    def partial_camera(*_args, **_kwargs):
        raise RuntimeError("SOFTWARE_ONLY camera failed before complete return")

    try:
        with capture, recorder:
            backend._capture_cached_observed()
            recorder.capture()
            monkeypatch.setattr(backend._camera, "capture_with_instances", partial_camera)
            with pytest.raises(RuntimeError, match="camera failed"):
                recorder.capture()
            accounting = recorder.render_accounting
            assert accounting["exact_passes"] is None
            assert accounting["known_completed_passes"] == 5
            assert accounting["status"] == "LOWER_BOUND"
            assert len(accounting["unknown_operation_ids"]) == 1
            assert accounting["attempts"][-1]["returned_pass_count"] is None
            recorder.freeze()
            audit = _Audit(dict(geometry=geometry), {}, tmp_path)
            audit.raw = load_json(recorder.directory / "partial-originals.json")
            assert audit.raw["render_accounting"] == accounting
            with pytest.raises(ValueError, match="only a lower bound"):
                audit.render_accounting()
            assert not audit.source_ok and not audit.horizon_ok
    finally:
        owner.close()
