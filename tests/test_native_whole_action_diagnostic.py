"""Software controls for the single registered whole-action development release."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cloud_edge_robot_arm.research import native_checkpoint_diagnostic as diagnostic
from cloud_edge_robot_arm.research.native_calibration_collection import (
    ROOT,
    load_json,
    read_protocol,
)
from cloud_edge_robot_arm.research.native_collection_application import NativeCollectionApplication
from cloud_edge_robot_arm.simulation.mujoco.backend import ExecutionGuardBoundaryV1


@pytest.fixture
def whole_slot(tmp_path, monkeypatch):
    source = tmp_path / diagnostic.WHOLE_ACTION_SOURCE_SUFFIX
    config = diagnostic._REGISTERED_TEACHER_CONFIG
    (source / config).parent.mkdir(parents=True)
    (source / config).write_bytes((ROOT / config).read_bytes())
    monkeypatch.setattr(diagnostic, "ROOT", source)
    monkeypatch.chdir(source)
    monkeypatch.setenv("MUJOCO_GL", "egl")
    return source.parent / "release"


def test_whole_action_profile_is_one_canonical_distinct_release(whole_slot, tmp_path):
    with pytest.raises(ValueError, match="canonical"):
        diagnostic.register_whole_action_diagnostic(tmp_path / "elsewhere")
    diagnostic.register_whole_action_diagnostic(whole_slot)
    release = load_json(whole_slot / "protocol.json")
    assert release["scope"] == "WHOLE_ACTION_DEVELOPMENT"
    assert release["schema_version"] == "native.whole-action-egl.development.v1"
    assert release["seed"] == 11920067
    assert release["step_wall_budget_ns"] == 8_000_000_000
    assert release["qualification_credit"] == 0
    assert release["png_compress_level"] == 1
    assert release["recipe"]["actions"][0]["horizon"]["total_steps"] == 1920
    with pytest.raises(ValueError):
        read_protocol(whole_slot)
    with pytest.raises(ValueError):
        NativeCollectionApplication.from_checkpoint_diagnostic(whole_slot)
    assert not (whole_slot / "run").exists()

    prefix = tmp_path / "prefix"
    diagnostic.register_checkpoint_diagnostic(prefix)
    with pytest.raises(ValueError):
        NativeCollectionApplication.from_whole_action_diagnostic(prefix)
    assert load_json(prefix / "protocol.json")["schema_version"] == diagnostic.DIAGNOSTIC_SCHEMA
    copy = tmp_path / "copied"
    copy.mkdir()
    (copy / "protocol.json").write_bytes((whole_slot / "protocol.json").read_bytes())
    with pytest.raises(ValueError):
        NativeCollectionApplication.from_whole_action_diagnostic(copy)


@pytest.mark.parametrize("field,value", [("png_compress_level", 6), ("seed", 11919001)])
def test_whole_action_rejects_preregistered_tampering_before_output(whole_slot, field, value):
    diagnostic.register_whole_action_diagnostic(whole_slot)
    file = whole_slot / "protocol.json"
    candidate = load_json(file)
    candidate[field] = value
    file.write_text(json.dumps(candidate))
    with pytest.raises(ValueError, match="diagnostic registration"):
        NativeCollectionApplication.from_whole_action_diagnostic(whole_slot)
    assert not (whole_slot / "run").exists()


def test_whole_action_dispatch_preserves_real_early_veto_and_exclusive_claim(
    whole_slot, monkeypatch
):
    from cloud_edge_robot_arm.research import native_collection_application
    from cloud_edge_robot_arm.simulation_runtime.worker import SimulationWorker

    diagnostic.register_whole_action_diagnostic(whole_slot)
    app = NativeCollectionApplication.from_whole_action_diagnostic(whole_slot)
    assert type(app.worker) is SimulationWorker
    job = app.prepare_once()
    assert job.seed == 11920067
    assert job.max_attempts == 1
    assert job.manifest_id == "native.whole-action-egl.development.v1"
    claim = whole_slot / "diagnostic-claim.json"
    assert load_json(claim)["scope"] == "WHOLE_ACTION_DEVELOPMENT"
    assert (whole_slot.parent / "worker-begin.json").is_file()
    with pytest.raises(RuntimeError, match="already"):
        NativeCollectionApplication.from_whole_action_diagnostic(whole_slot)

    disk_usage = native_collection_application.shutil.disk_usage

    def low_disk(path):
        return SimpleNamespace(free=0) if Path(path) == whole_slot / "run" else disk_usage(path)

    monkeypatch.setattr(native_collection_application.shutil, "disk_usage", low_disk)
    with pytest.raises(RuntimeError, match="worker terminal outcome"):
        app.execute_once()
    result = load_json(whole_slot / "run/collection-result.json")
    measurement = result["whole_action_diagnostic"]
    assert result["qualification_credit"] == 0
    assert result["worker_snapshot"]["job"]["status"] == "BLOCKED_BY_ENV"
    assert measurement["sqlite"]["readonly_snapshots"] == 1
    assert measurement["status"] == "EARLY_STOP"
    assert measurement["measurement_complete"] is False
    assert measurement["post_shield"] is None
    assert measurement["elapsed_ns"] is None
    assert measurement["action_pass"] is False
    assert result["owner_closure"]["completed"]


def test_only_old_prefix_cuts_guard_and_original_post_uses_strict_timeout():
    from cloud_edge_robot_arm.edge.safety.models import SafetyContext
    from cloud_edge_robot_arm.edge.safety.rules import StepTimeoutRule

    start = 10_000_000_000
    boundary = ExecutionGuardBoundaryV1("PHYSICS", "BEFORE", "episode", 120, 9)
    old = diagnostic._CheckpointDiagnostic(registration_sha256="a" * 64)
    whole = diagnostic._CheckpointDiagnostic(registration_sha256="b" * 64, whole_action=True)
    for state in (old, whole):
        state.start_action(start, 120)
    with pytest.raises(diagnostic._CheckpointDiagnosticDeadline):
        old.authorize(boundary, start + 8_000_000_000)
    whole.authorize(boundary, start + 8_001_000_000)
    assert whole.cutoff_monotonic_ns is None
    assert whole.last_authorized_checkpoint["physics_step"] == 120

    rule = StepTimeoutRule()
    context = SafetyContext.model_construct(
        contract=SimpleNamespace(steps=[SimpleNamespace(step_id="step-1", timeout_ms=8_000)]),
        step_id="step-1",
        step_started_at=start / 10**9,
        monotonic_now=18.0,
    )
    at_gate = rule.evaluate(context)
    over_gate = rule.evaluate(context.model_copy(update={"monotonic_now": 18.001}))
    assert at_gate.decision.value == "ALLOW"
    assert over_gate.decision.value == "REJECT"
    assert over_gate.limit_value == 8_000
    assert over_gate.reason_code == "STEP_TIMEOUT"


@pytest.mark.parametrize("level", [6, 1])
def test_same_profile_native_recorder_and_capture_encode_same_frame(tmp_path, level):
    from cloud_edge_robot_arm.vision.capture import MuJoCoCaptureSession
    from cloud_edge_robot_arm.vision.raw_recorder_v3 import VisualRawRecorderV3
    from tests.test_visual_raw_recorder_v3 import recorder_fixture, software_sensor_camera

    stub, backend, _, executor, _, _ = recorder_fixture(tmp_path)
    software_sensor_camera(backend)
    session = MuJoCoCaptureSession(backend._config, backend=backend, png_compress_level=level)
    recorder = VisualRawRecorderV3(
        backend,
        session,
        executor,
        directory=tmp_path / "same",
        source_root=stub.source_root,
        source_hashes=stub.source_hashes,
        png_compress_level=level,
    )
    with session, recorder:
        returned = recorder.capture()
        original = recorder._frames[-1]["observation_payload"]
        assert original == returned.model_dump(mode="json")
    with pytest.raises(ValueError, match="compression"):
        VisualRawRecorderV3(
            backend,
            session,
            executor,
            directory=tmp_path / "mixed",
            source_root=stub.source_root,
            source_hashes=stub.source_hashes,
            png_compress_level=6 if level == 1 else 1,
        )
