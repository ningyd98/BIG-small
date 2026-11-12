"""Synthetic marker/model derivation; no native or admission qualification."""

from __future__ import annotations

import base64
import copy
import importlib
import importlib.util
import io
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.research import native_collection_grounding as grounding
from cloud_edge_robot_arm.vision import native_calibration as calibration
from cloud_edge_robot_arm.vision.marker_families import (
    LEGACY_FAMILY,
    PREPARE_ONLY_FAMILY,
    SIDE_PREPARE_ONLY_FAMILY,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests import test_native_calibration_source as calibration_cases
from tests import test_pose_marker_evidence as marker_cases

ROOT = Path(__file__).resolve().parents[1]
HELPER = "src/cloud_edge_robot_arm/vision/registered_objects.py"


def api():
    name = "cloud_edge_robot_arm.vision.registered_objects"
    assert importlib.util.find_spec(name) is not None, "shared registered-object geometry missing"
    return importlib.import_module(name)


def frame(*, family=SIDE_PREPARE_ONLY_FAMILY, rotation=0, fault=None, frame_id="synthetic-1"):
    """Known tag above a generated table; all pixels/depth are newly synthetic."""
    payload = grounding.geometry_registration(marker_family_id=family)
    rgb = np.full((240, 320, 3), 255, dtype=np.uint8)
    rgb[160:180, 100:120] = (0, 255, 0)
    rgb[113:133, 169:191] = (255, 0, 0)
    # Same optical depth for the tag and box top, separated from table depth.
    depth = np.full((240, 320), 1.4, dtype="<f4")
    depth[113:133, 169:191] = 1.33
    glyph = np.repeat(np.repeat(marker_cases.BITS7, 3, axis=0), 3, axis=1)
    if fault == "foreign":
        import cv2

        glyph = cv2.aruco.generateImageMarker(
            cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), 8, 18
        )
    glyph = np.rot90(glyph, rotation)
    if fault != "missing":
        rgb[91:109, 171:189] = glyph[:, :, None]
    depth[89:111, 169:191] = 1.32995
    if fault == "duplicate":
        rgb[41:59, 231:249] = glyph[:, :, None]
        depth[39:61, 229:251] = 1.32995
    if family == LEGACY_FAMILY:
        depth[89:111, 169:191] = 0.7
    if fault == "zero_depth":
        depth[89:111, 169:191] = 0
    if fault == "nonplanar":
        depth[98:102, 178:182] = 1.1
    if fault == "scale":
        depth[89:111, 169:191] = 0.3
    image = io.BytesIO()
    Image.fromarray(rgb).save(image, format="PNG")
    observation = RGBDObservation(
        frame_id=frame_id,
        captured_at=datetime(2026, 11, 12, tzinfo=UTC),
        sim_time_s=0,
        rgb_png_base64=base64.b64encode(image.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        episode_id="SOFTWARE_ONLY_R610",
        scene_id="generated-table",
        **payload["camera"],
    )
    return observation, calibration.NativeGeometryRegistration(payload)


def revised(observation, **changes):
    return RGBDObservation.model_validate(
        {**observation.model_dump(), "checksum_sha256": "", **changes}
    )


def test_shared_api_exists_and_is_bound_for_all_native_families():
    assert callable(api().derive_registered_object_geometry)
    for family in (None, PREPARE_ONLY_FAMILY, SIDE_PREPARE_ONLY_FAMILY):
        assert HELPER in calibration.required_native_source_paths(marker_family_id=family)


@pytest.mark.parametrize("rotation", [0, 1])
def test_real_tag_rotation_rotates_attachment_before_subtraction(rotation):
    observation, registration = frame(rotation=rotation)
    result = api().derive_registered_object_geometry(observation, registration)
    assert result.status == "DERIVED"
    marker = result.marker_estimate
    assert marker.status == "OBSERVED"
    # Hand-derived offsets for side +Y0.1 and +Z0.03505, not a measured silhouette.
    offset = (0.0, -0.1, -0.03505) if rotation == 0 else (0.1, 0.0, -0.03505)
    assert np.subtract(result.object_center_world_m, marker.marker_center_world_m) == pytest.approx(
        offset, abs=1e-12
    )
    assert np.subtract(result.grasp_tcp_world_m, result.object_center_world_m) == pytest.approx(
        (0.0, 0.0, 0.01), abs=1e-12
    )
    expected_rotation = (
        (1, 0, 0, 0, 1, 0, 0, 0, 1) if rotation == 0 else (0, -1, 0, 1, 0, 0, 0, 0, 1)
    )
    assert result.rotation_object_to_world == pytest.approx(expected_rotation, abs=1e-12)
    # Pixel discretization check, not a sensor accuracy certificate.
    assert marker.marker_center_world_m == pytest.approx((0.45336, 0.10336, 0.07005), abs=3e-6)
    rotation_matrix = np.asarray(result.rotation_object_to_world).reshape(3, 3)
    recovered_marker = np.asarray(result.object_center_world_m) + rotation_matrix @ (
        0,
        0.1,
        0.03505,
    )
    assert recovered_marker == pytest.approx(marker.marker_center_world_m, abs=1e-12)


@pytest.mark.parametrize("family", [LEGACY_FAMILY, PREPARE_ONLY_FAMILY])
def test_existing_families_share_model_arithmetic_without_new_authority(family):
    observation, registration = frame(family=family)
    result = api().derive_registered_object_geometry(observation, registration)
    assert result.status == "DERIVED"
    assert np.subtract(
        result.object_center_world_m, result.marker_estimate.marker_center_world_m
    ) == pytest.approx((-0.1, 0, -0.03505), abs=1e-12)
    assert result.geometric_error_bound_m is None
    assert result.object_surface_visibility == "UNKNOWN"
    assert result.freshness == "NOT_EVALUATED"
    assert result.native_authority == "UNAVAILABLE"
    assert result.asset_validation == "NOT_PERFORMED"
    assert result.geometry_basis == "REGISTERED_RIGID_MODEL"


@pytest.mark.parametrize(
    "fault", ["foreign", "duplicate", "missing", "zero_depth", "nonplanar", "scale"]
)
def test_unavailable_current_marker_never_reuses_previous_geometry(fault):
    observation, registration = frame()
    assert api().derive_registered_object_geometry(observation, registration).status == "DERIVED"
    unknown, _ = frame(fault=fault, frame_id="later-unavailable")
    result = api().derive_registered_object_geometry(unknown, registration)
    assert result.status == "UNKNOWN"
    assert result.observation_id == "later-unavailable"
    assert result.object_center_world_m is None
    assert result.rotation_object_to_world is None and result.grasp_tcp_world_m is None
    assert result.geometric_error_bound_m is None


@pytest.mark.parametrize("change", ["calibration", "source", "intrinsics", "transform", "context"])
def test_valid_camera_mismatch_returns_no_model_coordinates(change):
    observation, registration = frame()
    changes = {
        "calibration": {"calibration_version": "different"},
        "source": {"source": "rgbd_camera"},
        "intrinsics": {"intrinsics": (300, 300, 159.5, 119.5)},
        "transform": {"camera_to_world": (1, 0, 0, 0.35, 0, -1, 0, 0, 0, 0, -1, 1.5, 0, 0, 0, 1)},
        "context": {"calibration_version": None},
    }
    result = api().derive_registered_object_geometry(
        revised(observation, **changes[change]), registration
    )
    assert result.status == "UNKNOWN"
    assert result.marker_estimate is None
    assert result.object_center_world_m is None and result.grasp_tcp_world_m is None


@pytest.mark.parametrize("change", ["checksum", "mask", "depth"])
def test_unvalidated_pair_mutation_is_rejected_before_derivation(change):
    observation, registration = frame()
    mutations = {
        "checksum": {"checksum_sha256": "0" * 64},
        "mask": {"valid_mask_base64": base64.b64encode(bytes(320 * 240)).decode()},
        "depth": {"depth_float32_base64": "AAAA"},
    }
    with pytest.raises(ValueError):
        api().derive_registered_object_geometry(
            observation.model_copy(update=mutations[change]), registration
        )


def test_exact_input_types_are_required_without_relaxing_for_lookalikes():
    observation, registration = frame()

    class ObservationAlias(RGBDObservation):
        pass

    class RegistrationAlias(calibration.NativeGeometryRegistration):
        pass

    with pytest.raises(TypeError):
        api().derive_registered_object_geometry(
            ObservationAlias.model_validate(observation.model_dump()), registration
        )
    with pytest.raises(TypeError):
        api().derive_registered_object_geometry(
            observation, RegistrationAlias(registration.to_payload())
        )


def test_result_provenance_is_detached_frozen_and_hashes_complete_registration():
    observation, registration = frame()
    result = api().derive_registered_object_geometry(observation, registration)
    assert (result.observation_id, result.observation_checksum_sha256, result.captured_at) == (
        observation.observation_id,
        observation.checksum_sha256,
        observation.captured_at,
    )
    assert (result.episode_id, result.calibration_version, result.observation_source) == (
        observation.episode_id,
        observation.calibration_version,
        observation.source,
    )
    data = registration.to_payload()
    assert result.registration_id == data["registration_id"] and result.object_id == "object"
    assert result.asset_path == data["asset_path"]
    assert result.asset_sha256 == data["pose_marker"]["marked_asset_sha256"]
    assert result.marker_registration_hash == registration.pose_marker.digest()
    data["contact_points_m"]["top"][2] += 0.001
    changed = api().derive_registered_object_geometry(
        observation, calibration.NativeGeometryRegistration(data)
    )
    assert changed.geometry_sha256 != result.geometry_sha256
    assert changed.marker_registration_hash == result.marker_registration_hash
    assert changed.grasp_tcp_world_m == result.grasp_tcp_world_m
    data["marker_to_object"][7] = 900
    assert result.object_center_world_m == changed.object_center_world_m
    with pytest.raises(FrozenInstanceError):
        result.status = "DERIVED"
    with pytest.raises(TypeError):
        result.object_center_world_m[0] = 900


@pytest.mark.parametrize(
    "field", ["observation_id", "observation_checksum_sha256", "captured_at", "registration_hash"]
)
def test_cross_frame_or_registration_detector_result_cannot_bind(monkeypatch, field):
    observation, registration = frame()
    module = api()
    marker = module.derive_registered_object_geometry(observation, registration).marker_estimate
    wrong = observation.captured_at + timedelta(seconds=1) if field == "captured_at" else "foreign"
    monkeypatch.setattr(
        module, "detect_pose_marker", lambda *args: replace(marker, **{field: wrong})
    )
    result = module.derive_registered_object_geometry(observation, registration)
    assert result.status == "UNKNOWN" and result.object_center_world_m is None


def test_original_asset_and_attachment_validators_still_reject_changed_claims(tmp_path):
    _, registration = frame()
    registration.validate_asset(ROOT)
    data = registration.to_payload()
    path = tmp_path / data["asset_path"]
    path.parent.mkdir(parents=True)
    path.write_bytes((ROOT / data["asset_path"]).read_bytes() + b"\n")
    with pytest.raises(ValueError, match="asset bytes"):
        registration.validate_asset(tmp_path)
    bad = copy.deepcopy(data)
    bad["marker_to_object"][7] += 0.01
    with pytest.raises(ValueError):
        calibration.NativeGeometryRegistration(bad)
    bad = copy.deepcopy(data)
    bad["pose_marker"]["marked_asset_sha256"] = "b" * 64
    with pytest.raises(ValueError):
        calibration.NativeGeometryRegistration(bad)


def test_bootstrap_keeps_original_pixels_and_pixel_depth_grasp(monkeypatch):
    observation, registration = frame()
    original = api().derive_registered_object_geometry
    calls = []

    def shared(*args):
        result = original(*args)
        calls.append(result)
        return result

    monkeypatch.setattr(grounding, "derive_registered_object_geometry", shared)
    evidence = grounding.collection_bootstrap_evidence(observation, registration.to_payload())
    assert len(calls) == 1
    assert evidence["original_pixel_target"] == (179, 119)
    assert evidence["original_pixel_destination"] == (109, 169)
    assert evidence["resolved_top_grasp_tcp"]["z"] == pytest.approx(0.045, abs=5e-8)
    # Original depth-derived x/y are not silently replaced by the registered model.
    assert evidence["resolved_top_grasp_tcp"]["x"] == pytest.approx(0.45078, abs=3e-6)
    assert evidence["depth_error_bound_m"] is None


@pytest.mark.parametrize("mode", ["unchanged", "grasp_drift", "unknown"])
def test_native_consumer_retains_quantile_and_recipe_gates(tmp_path, monkeypatch, mode):
    original = api().derive_registered_object_geometry
    calls = []

    def shared(*args):
        result = original(*args)
        calls.append(result)
        if mode == "grasp_drift":
            x, y, z = result.grasp_tcp_world_m
            return replace(result, grasp_tcp_world_m=(x + 1e-6, y, z))
        if mode == "unknown":
            return replace(
                result,
                status="UNKNOWN",
                object_center_world_m=None,
                rotation_object_to_world=None,
                grasp_tcp_world_m=None,
            )
        return result

    monkeypatch.setattr(calibration, "derive_registered_object_geometry", shared)
    result = calibration_cases.isolated_estimate(tmp_path, monkeypatch)
    assert len(calls) == 1
    if mode == "unchanged":
        assert result.geometric_error_bound_m == 0.001
    else:
        assert result.geometric_error_bound_m is None
        reason = (
            "owner_geometry_recipe_differs_from_registered_estimator"
            if mode == "grasp_drift"
            else "current_camera_or_full_geometry_unavailable"
        )
        assert reason in result.reasons


def test_missing_helper_source_blocks_original_registry(tmp_path):
    reg, payload = calibration_cases.registration(tmp_path)
    payload["source_hashes"].pop(HELPER)
    with pytest.raises(ValueError, match="source inventory incomplete"):
        calibration_cases.rewrite(reg, payload)


def test_rehashed_helper_copy_cannot_become_executing_source(tmp_path):
    reg, payload = calibration_cases.registration(tmp_path / "records")
    copied_root = tmp_path / "source"
    for name in calibration.required_native_source_paths():
        target = copied_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    modified = copied_root / HELPER
    modified.write_bytes(modified.read_bytes() + b"\n# altered software source\n")
    payload["source_hashes"][HELPER] = calibration_cases.digest(modified)
    registry_path = reg.artifact_root / reg.registry_path
    import json

    registry_path.write_text(json.dumps(payload))
    changed = calibration.NativeCalibrationRegistration(
        reg.artifact_root, copied_root, reg.registry_path, calibration_cases.digest(registry_path)
    )
    with pytest.raises(ValueError, match="current native implementation"):
        changed.revalidate()
