"""SOFTWARE_ONLY registration/reconstruction tests never mint native admission."""

import base64
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from importlib import import_module, util
from math import sqrt
from pathlib import Path

import pytest

from tests.test_raw_episode_v3 import fixture as raw_fixture
from tests.test_visual_owner_registration import values as owner_values

ROOT = Path(__file__).resolve().parents[1]
ASSET = "assets/robots/franka_panda/scene_pose_marker_outboard_v3.xml"
ASSET_SHA = "ddc34b13d8df403f3fdeeab94be75ca988541f2eac0a3e534704f68200c39a23"


def api():
    names = (
        "cloud_edge_robot_arm.vision.native_calibration",
        "cloud_edge_robot_arm.research.native_geometry_calibration",
    )
    for name in names:
        assert util.find_spec(name) is not None, "missing production native calibration source"
    return tuple(import_module(name) for name in names)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(x=0, y=0, z=0):
    return [1, 0, 0, x, 0, 1, 0, y, 0, 0, 1, z, 0, 0, 0, 1]


def geometry(camera=None):
    if camera is None:
        envelope, records = raw_fixture()
        observation = records.frames[0].observation_payload
        camera = {
            key: observation[key]
            for key in (
                "calibration_version",
                "intrinsics",
                "camera_to_world",
                "width",
                "height",
                "source",
            )
        }
    return dict(
        registration_id="registered-box-grasp",
        object_id="object",
        object_class="cube",
        target_region_id="target_region",
        asset_path=ASSET,
        pose_marker=dict(
            marker_id=7,
            marker_size_m=0.045,
            marked_asset_sha256=ASSET_SHA,
            dictionary="DICT_4X4_50",
        ),
        marker_to_object=transform(0.1, 0, 0.03505),
        object_half_extent_m=[0.035] * 3,
        contact_points_m={"top": [0, 0, 0.035], "left": [0, 0.035, 0], "right": [0, -0.035, 0]},
        object_to_tcp=transform(0, 0, 0.01),
        tool_to_tcp=transform(0.105, 0, 0),
        camera=camera,
        region_world_m=[0.2, 0.25, 0.004],
        support_height_m=0.0,
    )


def registration(tmp_path):
    module, _ = api()
    envelope, records = raw_fixture()
    identity = replace(envelope.identity, asset_hash=ASSET_SHA)
    envelope = replace(envelope, identity=identity)
    records = replace(
        records,
        **{
            name: tuple(replace(row, identity=identity) for row in getattr(records, name))
            for name in ("intervals", "physics", "commands", "actions", "frames", "joins")
        },
    )
    case = tmp_path / "case-1"
    case.mkdir(parents=True)
    (case / "envelope.json").write_text(json.dumps(envelope.to_payload()))
    (case / "records.json").write_text(json.dumps(records.to_payload()))
    for frame in records.frames:
        for path, attr in (
            ("rgb.png", "rgb_png_base64"),
            ("depth.f32", "depth_float32_base64"),
            ("mask.u8", "valid_mask_base64"),
        ):
            target = case / "frames" / frame.acquisition_id / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(base64.b64decode(frame.observation_payload[attr]))
    payload = dict(
        schema_version="native.calibration.registry.v1",
        calibration_id="calibration-1",
        source_scope="SOFTWARE_ONLY",
        recipe="FULL_RIGID_GEOMETRY_AND_TERMINAL_JOINT_V1",
        coverage=0.9,
        preregistered_at="2026-01-01T00:00:00+00:00",
        geometry=geometry(),
        supported_actions={"MOVE_ABOVE": 10.0},
        support={
            "object_center_min_m": [-1, -1, -1],
            "object_center_max_m": [1, 1, 1],
            "endpoint_min_m": [-1, -1, -1],
            "endpoint_max_m": [1, 1, 1],
            "min_marker_side_px": 8.0,
        },
        source_hashes={name: digest(ROOT / name) for name in module.required_native_source_paths()},
        groups=[
            dict(
                group_id="group-1",
                directory="case-1",
                envelope_path="case-1/envelope.json",
                records_path="case-1/records.json",
                owner_inputs_paths={},
                split="calibration",
                prior_usage=["UNVIEWED"],
                ancestor_ids=["original-scene-instance-1"],
                clock_reference_path=None,
            )
        ],
        original_file_hashes={
            str(p.relative_to(tmp_path)): digest(p) for p in tmp_path.rglob("*") if p.is_file()
        },
    )
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(payload))
    return module.NativeCalibrationRegistration(
        tmp_path, ROOT, "registry.json", digest(path)
    ), payload


def rewrite(reg, payload):
    module, _ = api()
    path = reg.artifact_root / reg.registry_path
    path.write_text(json.dumps(payload))
    return module.NativeCalibrationRegistration(
        reg.artifact_root, ROOT, reg.registry_path, digest(path)
    )


def test_full_geometry_uses_eight_vertices_contact_and_tcp_lever_arms():
    module, producer = api()
    scope = module.NativeGeometryRegistration(geometry())
    errors = producer.full_rigid_geometry_errors(
        scope, [0, 0, 0], [0, -1, 0, 1, 0, 0, 0, 0, 1], [0, 0, 0], [1, 0, 0, 0, 1, 0, 0, 0, 1]
    )
    assert errors.vertex_error_m == pytest.approx(0.07)
    assert errors.contact_error_m == pytest.approx(0.035 * sqrt(2))
    assert errors.tcp_contact_error_m == 0
    assert errors.joint_geometry_error_m == pytest.approx(0.07)
    assert errors.vertex_count == 8 and errors.contact_count == 3


@pytest.mark.parametrize("count,bound", [(8, None), (9, 0.009), (10, None)])
def test_rank_keeps_every_missing_group_in_denominator(count, bound):
    _, producer = api()
    groups = {f"group-{n}": (n + 1) / 1000 for n in range(min(count, 9))}
    if count == 10:
        groups["failed-original-group"] = None
    result = producer.conformal_group_quantile(groups, coverage=0.9)
    assert result.bound_m == bound
    assert result.group_count == count
    assert result.rank == {8: 9, 9: 9, 10: 10}[count]
    if count == 10:
        assert result.unavailable_group_ids == ("failed-original-group",)


def test_registered_original_pipeline_retains_unknown_frames_failed_action_and_clock_gap(tmp_path):
    _, producer = api()
    reg, _ = registration(tmp_path)
    result = producer.reconstruct_registered_calibration(reg)
    assert result.source_scope == "SOFTWARE_ONLY"
    assert result.assigned_group_count == 1
    assert result.independent_group_count == 1
    assert result.geometry_quantile.bound_m is None
    assert result.action_quantiles["MOVE_ABOVE"].bound_m is None
    assert result.groups[0].allocated_frames == 2
    assert result.groups[0].unknown_frames == 2
    assert result.groups[0].failed_actions == 1
    assert "clock_mapping_unavailable" in result.groups[0].reasons
    assert not hasattr(result, "geometric_error_bound_m")


@pytest.mark.parametrize(
    "field,value",
    [
        ("bound_m", 0.0001),
        ("source_accepted", True),
        ("accepted_flag", "VALID"),
        ("quantity", "MARKER_CENTER_TRANSLATION"),
    ],
)
def test_rehashed_caller_scalar_flags_and_marker_only_quantity_are_rejected(tmp_path, field, value):
    api()
    reg, payload = registration(tmp_path)
    payload[field] = value
    with pytest.raises(ValueError):
        rewrite(reg, payload)


@pytest.mark.parametrize("change", ["marker_offset", "object_extent", "tcp_frame", "asset"])
def test_complete_geometry_registration_is_recomputed_from_asset(tmp_path, change):
    api()
    reg, payload = registration(tmp_path)
    geometry_payload = payload["geometry"]
    if change == "marker_offset":
        geometry_payload["marker_to_object"][3] = 0
    elif change == "object_extent":
        geometry_payload["object_half_extent_m"][0] = 0.01
    elif change == "tcp_frame":
        geometry_payload["tool_to_tcp"][3] = 0.1
    else:
        geometry_payload["pose_marker"]["marked_asset_sha256"] = "a" * 64
    with pytest.raises(ValueError):
        rewrite(reg, payload)


@pytest.mark.parametrize("change", ["missing", "extra", "symlink", "source_drift"])
def test_original_inventory_and_current_source_are_rechecked(tmp_path, change):
    module, producer = api()
    reg, payload = registration(tmp_path)
    target = tmp_path / "case-1/frames/before/rgb.png"
    if change == "missing":
        target.unlink()
    elif change == "extra":
        (tmp_path / "unassigned-frame.json").write_text("{}")
    elif change == "symlink":
        target.unlink()
        target.symlink_to(tmp_path / "case-1/frames/after/rgb.png")
    else:
        payload["source_hashes"][module.required_native_source_paths()[0]] = "f" * 64
        reg = rewrite(reg, payload)
    with pytest.raises(ValueError):
        producer.reconstruct_registered_calibration(reg)


@pytest.mark.parametrize("history", [["DEVELOPMENT_FEEDBACK"], ["TRAIN"], ["UNKNOWN"], ["TEST"]])
def test_viewed_or_leaking_original_ancestors_cannot_be_relabelled_calibration(tmp_path, history):
    api()
    reg, payload = registration(tmp_path)
    payload["groups"][0]["prior_usage"] = history
    with pytest.raises(ValueError):
        rewrite(reg, payload)


def test_missing_record_retains_complete_assignment_and_no_zero_imputation(tmp_path):
    _, producer = api()
    reg, payload = registration(tmp_path)
    path = tmp_path / "case-1/records.json"
    records = json.loads(path.read_text())
    records["frames"] = records["frames"][:1]
    path.write_text(json.dumps(records))
    payload["original_file_hashes"]["case-1/records.json"] = digest(path)
    reg = rewrite(reg, payload)
    result = producer.reconstruct_registered_calibration(reg)
    assert result.groups[0].allocated_frames == 2
    assert result.groups[0].missing_frames == 1
    assert result.geometry_quantile.group_count == 1
    assert result.geometry_quantile.bound_m is None


def test_upcoming_actuator_n_is_required_for_physics_end_n(tmp_path):
    _, producer = api()
    reg, payload = registration(tmp_path)
    path = tmp_path / "case-1/records.json"
    records = json.loads(path.read_text())
    records["physics"][0]["control_payload"]["physics_step"] = 0
    path.write_text(json.dumps(records))
    payload["original_file_hashes"]["case-1/records.json"] = digest(path)
    reg = rewrite(reg, payload)
    result = producer.reconstruct_registered_calibration(reg)
    assert "control_pre_step_identity_mismatch" in result.groups[0].reasons
    assert result.geometry_quantile.bound_m is None


def test_software_scope_cannot_be_upgraded_by_rehashed_origin_string(tmp_path):
    _, producer = api()
    reg, payload = registration(tmp_path)
    payload["source_scope"] = "REGISTERED_SIMULATION_CALIBRATION"
    reg = rewrite(reg, payload)
    with pytest.raises(ValueError):
        producer.reconstruct_registered_calibration(reg)


def test_public_registration_and_lookalike_role_cannot_mint_application_source(tmp_path):
    module, _ = api()
    reg, _ = registration(tmp_path)
    with pytest.raises(TypeError):
        module.NativeCalibrationSource(reg)
    with pytest.raises(ValueError):
        module.NativeCalibrationSource.from_application(reg)


def test_shared_ancestors_or_raw_content_form_one_independent_component():
    _, producer = api()
    groups = [
        {"group_id": "a", "ancestor_ids": ["source-root-1"], "fingerprints": ["rgb-1"]},
        {"group_id": "b", "ancestor_ids": ["source-root-1"], "fingerprints": ["rgb-2"]},
        {"group_id": "c", "ancestor_ids": ["source-root-3"], "fingerprints": ["rgb-2"]},
    ]
    assert producer.independent_components(groups) == (("a", "b", "c"),)


def test_duplicate_rgbd_fingerprint_ignores_time_and_shared_masks():
    _, producer = api()
    _, records = raw_fixture()
    observation = dict(records.frames[0].observation_payload)
    original = producer.original_rgbd_fingerprint(observation)
    observation["captured_at"] = "2030-01-01T00:00:00+00:00"
    assert producer.original_rgbd_fingerprint(observation) == original
    observation["depth_float32_base64"] = base64.b64encode(b"different depth").decode()
    assert producer.original_rgbd_fingerprint(observation) != original


def owner_originals():
    data = owner_values()
    payload = {
        key: data[key].to_payload()
        for key in ("original", "current_identity", "grounding_inputs", "grounding_policy")
    }
    payload["source_checkpoint"] = data["source_checkpoint"].model_dump(mode="json")
    payload.update(
        owner_revision=1, state_generation=2, required_duration_s=None, duration_check=None
    )
    return data, payload


def test_owner_receipt_horizon_is_reconstructed_and_detached():
    _, producer = api()
    data, payload = owner_originals()
    binding = producer.rebuild_owner_binding(payload, data["online"], now=data["now"])
    original_digest = binding.digest()
    assert binding.expected_duration_s == 10
    payload["grounding_inputs"]["grasp_tcp"]["z"] = 99
    assert binding.digest() == original_digest
    assert binding.grounded_step.parameters["target_pose"]["z"] == 0.16


def test_public_longer_horizon_without_source_duration_check_is_rejected():
    _, producer = api()
    data, payload = owner_originals()
    payload["required_duration_s"] = 15
    with pytest.raises(ValueError):
        producer.rebuild_owner_binding(payload, data["online"], now=data["now"])


def clock_originals(envelope, records):
    pairs = {
        pair.sequence: pair
        for interval in records.intervals
        for pair in (interval.start, interval.end)
        if pair is not None
    }
    return dict(
        schema_version="native.calibration.utc-originals.v1",
        clock_domain_id=envelope.identity.clock_domain_id,
        clock_descriptor_hash=envelope.clock_descriptor.digest(),
        independent_source_hashes={"src/independent_utc_capture.py": "b" * 64},
        samples=[
            dict(
                pair_hash=pair.digest(),
                utc_lower_at=(pair.utc_at - timedelta(microseconds=2)).isoformat(),
                utc_upper_at=(pair.utc_at + timedelta(microseconds=2)).isoformat(),
            )
            for pair in pairs.values()
        ],
    )


def test_independent_clock_originals_recompute_complete_pair_uncertainty():
    _, producer = api()
    envelope, records = raw_fixture()
    payload = clock_originals(envelope, records)
    assert producer.independent_utc_uncertainty_ns(payload, envelope, records) == 2000
    payload["samples"] = payload["samples"][:-1]
    with pytest.raises(ValueError):
        producer.independent_utc_uncertainty_ns(payload, envelope, records)


def test_clock_self_declaration_or_relabelled_local_source_is_rejected():
    _, producer = api()
    envelope, records = raw_fixture()
    payload = clock_originals(envelope, records)
    payload["independent_source_hashes"] = dict(envelope.clock_descriptor.source_hashes)
    with pytest.raises(ValueError):
        producer.independent_utc_uncertainty_ns(payload, envelope, records)
    payload = clock_originals(envelope, records)
    payload["accepted_uncertainty_ns"] = 0
    with pytest.raises(ValueError):
        producer.independent_utc_uncertainty_ns(payload, envelope, records)


def test_public_source_alias_cannot_change_frozen_registration():
    module, _ = api()
    source = object.__new__(module.NativeCalibrationSource)
    with pytest.raises(FrozenInstanceError):
        source._registration = "caller replacement"


def test_rehashed_modified_source_copy_is_not_the_executing_implementation(tmp_path):
    module, producer = api()
    reg, payload = registration(tmp_path / "calibration")
    copied_root = tmp_path / "source"
    for name in module.required_native_source_paths():
        target = copied_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    name = module.required_native_source_paths()[0]
    copied = copied_root / name
    copied.write_bytes(copied.read_bytes() + b"\n# caller-rehashed substitute\n")
    payload["source_hashes"][name] = digest(copied)
    path = reg.artifact_root / reg.registry_path
    path.write_text(json.dumps(payload))
    substituted = module.NativeCalibrationRegistration(
        reg.artifact_root, copied_root, reg.registry_path, digest(path)
    )
    with pytest.raises(ValueError, match="current native implementation"):
        producer.reconstruct_registered_calibration(substituted)


def test_legal_component_ids_cannot_overwrite_unknown_geometry_or_action(monkeypatch):
    """SOFTWARE_ONLY aggregation probe; patched inputs are not native provenance."""
    module, producer = api()
    allocations = [
        {"group_id": "a", "ancestor_ids": ["shared-origin"]},
        {"group_id": "b", "ancestor_ids": ["shared-origin"]},
        {"group_id": "a|b", "ancestor_ids": ["independent-origin-ab"]},
        *[
            {"group_id": f"z{index}", "ancestor_ids": [f"independent-origin-z{index}"]}
            for index in range(8)
        ],
    ]
    payload = {
        "source_scope": "SOFTWARE_ONLY",
        "geometry": geometry(),
        "groups": allocations,
        "supported_actions": {"MOVE_ABOVE": 10.0},
    }

    def original_group(registration, registry, allocated, scope):
        group_id = allocated["group_id"]
        residual = None if group_id == "a" else 0.001
        return producer.CalibrationGroupResult(
            group_id=group_id,
            status="INCOMPLETE" if residual is None else "COMPLETE",
            allocated_frames=1,
            missing_frames=int(residual is None),
            unknown_frames=0,
            failed_actions=int(residual is None),
            geometry_error_m=residual,
            action_errors_m={"MOVE_ABOVE": residual},
            reasons=("software_unknown",) if residual is None else (),
            fingerprints=("software-original:" + group_id,),
        )

    registration = object.__new__(module.NativeCalibrationRegistration)
    monkeypatch.setattr(module.NativeCalibrationRegistration, "revalidate", lambda self: payload)
    monkeypatch.setattr(producer, "_group", original_group)
    result = producer.reconstruct_registered_calibration(registration)
    assert result.assigned_group_count == 11
    assert result.independent_group_count == 10
    assert ("a", "b") in result.components and ("a|b",) in result.components
    actual = tuple(
        (quantile.group_count, quantile.rank, quantile.bound_m, len(quantile.unavailable_group_ids))
        for quantile in (result.geometry_quantile, result.action_quantiles["MOVE_ABOVE"])
    )
    assert actual == ((10, 10, None, 1), (10, 10, None, 1))
    assert (
        result.geometry_quantile.unavailable_group_ids
        == result.action_quantiles["MOVE_ABOVE"].unavailable_group_ids
    )
