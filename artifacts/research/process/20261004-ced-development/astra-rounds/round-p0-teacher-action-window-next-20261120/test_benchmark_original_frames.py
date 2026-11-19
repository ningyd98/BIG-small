"""Synthetic controls for the local benchmark input and output gates."""

from hashlib import sha256
from pathlib import Path

import pytest
from benchmark_original_frames import (
    fresh_output,
    phase_residual,
    require_identity,
    verified_file,
    verify_baseline_bytes,
)


def test_damaged_original_is_rejected(tmp_path):
    raw = tmp_path / "pixel"
    raw.write_bytes(b"rgb")
    assert verified_file(raw, sha256(b"rgb").hexdigest()) == raw
    raw.write_bytes(b"rGb")
    with pytest.raises(ValueError, match="hash"):
        verified_file(raw, sha256(b"rgb").hexdigest())


def test_changed_role_or_capture_identity_is_rejected():
    old = {"role": "REGISTERED_PER_PHYSICS_STEP", "operation_id": 5, "acquisition": "acquisition-4"}
    require_identity(old, dict(old))
    for change in ({"role": "IMPLICIT_SENSOR_CACHE_UPDATE"}, {"operation_id": 6}):
        with pytest.raises(ValueError, match="identity"):
            require_identity(old, {**old, **change})


def test_baseline_reencoding_requires_identical_bytes():
    verify_baseline_bytes(b"original", b"original")
    with pytest.raises(ValueError, match="baseline"):
        verify_baseline_bytes(b"original", b"re-encoded")


def test_exclusive_phase_accounting_rejects_overlap():
    value = phase_residual(12, {"encode": 5, "write": 2})
    with pytest.raises(ValueError, match="overlap"):
        phase_residual(12, {"outer": 8, "inner": 6})
    assert value == 5


def test_output_directory_cannot_be_reused(tmp_path):
    output = tmp_path / "new"
    assert fresh_output(output) == output
    with pytest.raises(FileExistsError):
        fresh_output(output)
    assert not list(output.iterdir())


SOURCE_KEY = "src/cloud_edge_robot_arm/research/native_checkpoint_diagnostic.py"
SOURCE_SHA = "a1c22853004ddddcbc12bdd3c4726d2dc54f7925fe6537d37c6887b5e965073d"


@pytest.fixture
def frozen_layout(tmp_path):
    from benchmark_original_frames import SOURCE_SUFFIX

    copied = tmp_path / SOURCE_SUFFIX / "source" / SOURCE_KEY
    copied.parent.mkdir(parents=True)
    actual = Path.cwd() / SOURCE_SUFFIX / "source" / SOURCE_KEY
    copied.write_bytes(actual.read_bytes())
    observed = tmp_path / SOURCE_KEY
    observed.parent.mkdir(parents=True)
    observed.write_bytes(b"parallel current worktree version")
    return tmp_path, copied, observed


def test_only_registered_old_digest_resolves_the_frozen_copy(frozen_layout):
    from benchmark_original_frames import planned_input

    work, frozen, _ = frozen_layout
    assert planned_input(work, "inputs_sha256", SOURCE_KEY, SOURCE_SHA) == frozen


def test_exact_key_with_another_expected_digest_is_rejected(frozen_layout):
    from benchmark_original_frames import planned_input

    work, _, current = frozen_layout
    with pytest.raises(ValueError, match="registered original"):
        planned_input(work, "inputs_sha256", SOURCE_KEY, sha256(current.read_bytes()).hexdigest())


def test_other_input_cannot_fallback_to_a_frozen_match(frozen_layout):
    from benchmark_original_frames import SOURCE_SUFFIX, planned_input

    work, _, _ = frozen_layout
    key = "src/other.py"
    frozen = work / SOURCE_SUFFIX / "source" / key
    frozen.write_bytes(b"original")
    (work / key).write_bytes(b"drift")
    with pytest.raises(ValueError, match="original hash differs"):
        planned_input(work, "inputs_sha256", key, sha256(b"original").hexdigest())


@pytest.mark.parametrize("fault", ["missing", "tampered", "linked"])
def test_registered_frozen_copy_must_be_intact(frozen_layout, fault):
    from benchmark_original_frames import planned_input

    work, frozen, _ = frozen_layout
    original = frozen.read_bytes()
    frozen.unlink()
    if fault == "tampered":
        frozen.write_bytes(b"tampered")
    if fault == "linked":
        outside = work / "unregistered-copy"
        outside.write_bytes(original)
        frozen.symlink_to(outside)
    with pytest.raises(ValueError, match="missing original|original hash differs"):
        planned_input(work, "inputs_sha256", SOURCE_KEY, SOURCE_SHA)


def test_only_direct_input_category_can_use_the_frozen_mapping(frozen_layout):
    from benchmark_original_frames import planned_input

    work, _, _ = frozen_layout
    with pytest.raises(ValueError, match="original hash differs"):
        planned_input(work, "frame_inputs_sha256", SOURCE_KEY, SOURCE_SHA)


@pytest.fixture
def operation_fixture(tmp_path):
    from types import SimpleNamespace

    from benchmark_original_frames import Input, raw_recorder

    raw_camera = {"qpos": [1, 2, 3]}
    physical = {"physics_step": 4, "qpos": [1, 2, 3]}
    metadata = {
        "capture_source": {
            "operation_id": 5,
            "physics_step": 4,
            "role": "IMPLICIT_SENSOR_CACHE_UPDATE",
        },
        "frame": {
            "interval_id": "operation-5",
            "input_role": "SOURCE",
            "record_seq": 7,
            "camera_state_payload": raw_camera,
            "acquisition_id": "acquisition-1",
            "joined_physics_observation_hash": raw_recorder._digest(physical),
            "pass_state_hashes": ["pass1", "pass1"],
        },
        "instance_ids_present": True,
        "instance_labels_present": True,
        "instances_available": False,
        "instance_count": 0,
        "instance_labels": {},
    }
    event = SimpleNamespace(
        operation_id=5,
        parameters={"camera_state": raw_camera, "physics_state": physical},
        result={"instance_ids": (), "instance_labels": {}, "pass_state_hashes": ["pass1", "pass1"]},
    )
    return Input("acquisition-1", tmp_path, event, None, metadata, "SYNTHETIC")


def test_context_uses_original_parameter_mapping(operation_fixture):
    from benchmark_original_frames import operation_context

    assert operation_context(operation_fixture)["parameters"] is operation_fixture.event.parameters


@pytest.mark.parametrize("problem", ["camera", "physics", "operation", "role", "instance_presence"])
def test_context_rejects_mismatched_original_fields(operation_fixture, problem):
    from benchmark_original_frames import operation_context, validate_operation

    f = operation_fixture
    context = operation_context(f)
    context["parameters"] = f.event.parameters
    if problem == "camera":
        f.event.parameters["camera_state"] = {"qpos": [9]}
    elif problem == "physics":
        f.event.parameters["physics_state"] = {"physics_step": 4, "qpos": [9]}
    elif problem == "operation":
        f.event.operation_id = 6
    elif problem == "role":
        context["input_role"] = "ONLINE"
    else:
        del f.event.result["instance_ids"]
    with pytest.raises(ValueError):
        validate_operation(f, context)
