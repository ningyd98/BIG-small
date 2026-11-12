"""Current marker-model previews keep time/source identity and no execution authority."""

import base64
import hashlib
import importlib
import importlib.util
import io
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.research import native_collection_grounding as collection
from cloud_edge_robot_arm.vision import registered_objects, tracking
from cloud_edge_robot_arm.vision.marker_families import LEGACY_FAMILY, marker_family
from cloud_edge_robot_arm.vision.native_calibration import NativeGeometryRegistration
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_registered_object_geometry import frame as synthetic_frame
from tests.test_registered_object_geometry import revised
from tests.test_visual_owner_registration import values

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime(2026, 11, 12, tzinfo=UTC)
SOURCES = frozenset(
    [
        "src/cloud_edge_robot_arm/vision/registered_object_tracking.py",
        "src/cloud_edge_robot_arm/vision/registered_objects.py",
        "src/cloud_edge_robot_arm/vision/pose_markers.py",
        "src/cloud_edge_robot_arm/vision/native_calibration.py",
        "src/cloud_edge_robot_arm/vision/marker_families.py",
        "src/cloud_edge_robot_arm/vision/observations.py",
        "src/cloud_edge_robot_arm/vision/tracking.py",
        "src/cloud_edge_robot_arm/vision/worker_owner.py",
        "src/cloud_edge_robot_arm/vision/top_grasp.py",
        "src/cloud_edge_robot_arm/research/native_collection_grounding.py",
        "src/cloud_edge_robot_arm/vision/owner_registration.py",
    ]
)


def api():
    name = "cloud_edge_robot_arm.vision.registered_object_tracking"
    assert importlib.util.find_spec(name) is not None, "versioned current-frame tracker missing"
    return importlib.import_module(name)


def environment(tmp_path, monkeypatch):
    module = api()
    clock = [STAMP]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is UTC
            return clock[0]

    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(tracking, "datetime", Clock)
    reference, registration = synthetic_frame()
    root = tmp_path / "sources"
    hashes = {}
    names = SOURCES | {
        registration.to_payload()["asset_path"],
        marker_family(LEGACY_FAMILY).asset_path,
    }
    for name in names:
        blob = (ROOT / name).read_bytes()
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        hashes[name] = hashlib.sha256(blob).hexdigest()
    return module, reference, registration, root, hashes, clock


def tracker_env(tmp_path, monkeypatch):
    module, ref, reg, root, hashes, clock = environment(tmp_path, monkeypatch)
    tracker = module.RegisteredObjectTrackerV1(ref, reg, source_root=root, source_hashes=hashes)
    return tracker, ref, reg, root, hashes, clock


def later(reference, *, index=1, fault=None, rotation=0, fragment=False, region=None):
    current, _ = synthetic_frame(frame_id="current-" + str(index), fault=fault, rotation=rotation)
    current = revised(
        current,
        captured_at=reference.captured_at + timedelta(seconds=index * 0.1),
        sim_time_s=reference.sim_time_s + index * 0.1,
    )
    if fragment or region:
        with Image.open(io.BytesIO(base64.b64decode(current.rgb_png_base64))) as image:
            rgb = np.array(image)
        if fragment:
            rgb[113:133, 178:182] = (255, 255, 255)
        if region == "missing":
            rgb[160:180, 100:120] = (255, 255, 255)
        if region == "ambiguous":
            rgb[190:205, 130:145] = (0, 255, 0)
        if region == "incomplete":
            rgb[169:172, 108:112] = (255, 255, 255)
        output = io.BytesIO()
        Image.fromarray(rgb).save(output, format="PNG")
        current = revised(current, rgb_png_base64=base64.b64encode(output.getvalue()).decode())
    return current


def test_provider_contract_exists():
    assert callable(api().RegisteredObjectTrackerV1)
    assert api().PREVIEW_SOURCE_PATHS == SOURCES


def test_provider_current_geometry_schema_and_immutable_payload(tmp_path, monkeypatch):
    tracker, ref, reg, root, hashes, clock = tracker_env(tmp_path, monkeypatch)
    current = later(ref, rotation=1)
    clock[0] = current.captured_at
    result = tracker.update(current)
    expected = registered_objects.derive_registered_object_geometry(current, reg)
    assert result.status == "DERIVED" and result.geometry == expected
    assert result.observation_id == current.observation_id and result.is_new_frame is True
    assert result.observation_checksum_sha256 == current.checksum_sha256
    assert result.geometry.object_surface_visibility == "UNKNOWN"
    assert result.geometry.geometric_error_bound_m is None
    assert result.geometry.freshness == "NOT_EVALUATED"
    assert result.geometry.asset_validation == "NOT_PERFORMED"
    assert result.geometry.native_authority == "UNAVAILABLE"
    payload = result.to_payload()
    assert payload["schema_version"] == "registered.object.track.v1"
    original = result.digest()
    payload["geometry"]["grasp_tcp_world_m"][0] = 999
    payload["source_hashes"].clear()
    assert result.digest() == original and result.to_payload()["source_hashes"] == hashes
    with pytest.raises(FrozenInstanceError):
        result.status = "UNKNOWN"
    repeated = tracker.update(current)
    assert repeated.status == "DERIVED" and not repeated.is_new_frame
    assert not hasattr(tracker, "facts")


@pytest.mark.parametrize(
    "field",
    [
        "episode_id",
        "scene_id",
        "calibration_version",
        "source",
        "width",
        "height",
        "intrinsics",
        "camera_to_world",
    ],
)
def test_provider_rejects_changed_context(tmp_path, monkeypatch, field):
    tracker, ref, reg, root, hashes, clock = tracker_env(tmp_path, monkeypatch)
    changes = {
        "episode_id": "other",
        "scene_id": "other",
        "calibration_version": "other",
        "source": "rgbd_camera",
        "intrinsics": (300, 300, 159.5, 119.5),
        "camera_to_world": (1, 0, 0, 0.35, 0, -1, 0, 0, 0, 0, -1, 1.5, 0, 0, 0, 1),
    }
    current = later(ref)
    clock[0] = current.captured_at
    if field in {"width", "height"}:
        current = current.crop((0, 0, 319, 240) if field == "width" else (0, 0, 320, 239))
    else:
        current = revised(current, **{field: changes[field]})
    result = tracker.update(current)
    assert result.status == "UNKNOWN" and result.geometry is None
    assert field in result.reason


@pytest.mark.parametrize("delta", [-0.051, 5.001])
def test_provider_rechecks_freshness_even_on_repeat(tmp_path, monkeypatch, delta):
    tracker, ref, reg, root, hashes, clock = tracker_env(tmp_path, monkeypatch)
    clock[0] = ref.captured_at + timedelta(seconds=delta)
    result = tracker.update(ref)
    assert result.status == "UNKNOWN" and result.geometry is None and "fresh" in result.reason


@pytest.mark.parametrize("fault", ["missing", "foreign", "duplicate", "zero_depth"])
def test_provider_failed_marker_has_no_fallback_and_consumes_identity(tmp_path, monkeypatch, fault):
    tracker, ref, reg, root, hashes, clock = tracker_env(tmp_path, monkeypatch)
    bad = later(ref, index=1, fault=fault)
    clock[0] = bad.captured_at
    assert tracker.update(bad).status == "UNKNOWN"
    assert tracker.update(bad).geometry is None
    good = later(ref, index=2)
    clock[0] = good.captured_at
    assert tracker.update(good).status == "DERIVED"
    replay = tracker.update(bad)
    assert replay.status == "UNKNOWN" and "replay" in replay.reason


@pytest.mark.parametrize("case", ["reused_changed", "nonmonotonic_capture", "nonmonotonic_sim"])
def test_provider_rejects_reuse_and_nonmonotonic_times(tmp_path, monkeypatch, case):
    tracker, ref, reg, root, hashes, clock = tracker_env(tmp_path, monkeypatch)
    current = later(ref)
    if case == "reused_changed":
        current = revised(current, frame_id=ref.frame_id, observation_id=ref.observation_id)
    if case == "nonmonotonic_capture":
        current = revised(current, captured_at=ref.captured_at)
    if case == "nonmonotonic_sim":
        current = revised(current, sim_time_s=ref.sim_time_s)
    clock[0] = current.captured_at
    assert tracker.update(current).status == "UNKNOWN"


def test_provider_failed_frame_does_not_retime_last_successful_pose(tmp_path, monkeypatch):
    tracker, ref, reg, root, hashes, clock = tracker_env(tmp_path, monkeypatch)
    missing = later(ref, index=9, fault="missing")
    clock[0] = missing.captured_at
    assert tracker.update(missing).status == "UNKNOWN"
    current = later(ref, index=10)
    clock[0] = current.captured_at
    original = api().derive_registered_object_geometry

    def displaced(obs, scope):
        result = original(obs, scope)
        center = result.object_center_world_m
        return replace(result, object_center_world_m=(center[0] + 0.3, center[1], center[2]))

    monkeypatch.setattr(api(), "derive_registered_object_geometry", displaced)
    # .3m over1s is valid, but would be falsely rejected
    # if the missing .9s frame retimed the old pose.
    assert tracker.update(current).status == "DERIVED"
    farther = later(ref, index=11)
    clock[0] = farther.captured_at

    def jump(obs, scope):
        result = original(obs, scope)
        center = result.object_center_world_m
        return replace(result, object_center_world_m=(center[0] + 1.0, center[1], center[2]))

    monkeypatch.setattr(api(), "derive_registered_object_geometry", jump)
    result = tracker.update(farther)
    assert result.status == "UNKNOWN" and result.geometry is None and "jump" in result.reason


def test_provider_checks_source_asset_and_lexical_aliases(tmp_path, monkeypatch):
    module, ref, reg, root, hashes, clock = environment(tmp_path, monkeypatch)
    missing = dict(hashes)
    missing.pop(next(iter(SOURCES)))
    with pytest.raises(ValueError):
        module.RegisteredObjectTrackerV1(ref, reg, source_root=root, source_hashes=missing)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        module.RegisteredObjectTrackerV1(ref, reg, source_root=alias, source_hashes=hashes)
    tracker = module.RegisteredObjectTrackerV1(ref, reg, source_root=root, source_hashes=hashes)
    original = tracker.update(ref).digest()
    hashes.clear()
    assert tracker.update(ref).digest() == original
    path = root / reg.to_payload()["asset_path"]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        tracker.update(ref)


def test_provider_detects_mid_processing_expiry_and_source_drift(tmp_path, monkeypatch):
    tracker, ref, reg, root, hashes, clock = tracker_env(tmp_path, monkeypatch)
    original = api().derive_registered_object_geometry

    def expire(obs, scope):
        result = original(obs, scope)
        clock[0] = obs.captured_at + timedelta(seconds=6)
        return result

    monkeypatch.setattr(api(), "derive_registered_object_geometry", expire)
    result = tracker.update(ref)
    assert result.status == "UNKNOWN" and result.geometry is None and "fresh" in result.reason
    clock[0] = ref.captured_at

    def drift(obs, scope):
        result = original(obs, scope)
        path = root / "src/cloud_edge_robot_arm/vision/tracking.py"
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(api(), "derive_registered_object_geometry", drift)
    with pytest.raises(ValueError):
        tracker.update(ref)


def test_provider_registration_snapshot_and_marker_output_binding(tmp_path, monkeypatch):
    tracker, ref, reg, root, hashes, clock = tracker_env(tmp_path, monkeypatch)
    payload = reg.to_payload()
    payload["object_id"] = "foreign-object"
    object.__setattr__(reg, "_payload_json", json.dumps(payload))
    assert tracker.update(ref).geometry.object_id == "object"
    original = registered_objects.detect_pose_marker

    def mismatch(obs, registration):
        return replace(original(obs, registration), observation_id="wrong")

    monkeypatch.setattr(registered_objects, "detect_pose_marker", mismatch)
    assert tracker.update(ref).geometry is None
    with pytest.raises(ValueError):
        tracker.update(ref.model_copy(update={"checksum_sha256": "0" * 64}))


def test_preview_contract_exists():
    assert callable(getattr(collection, "bootstrap_registered_collection_tracker_v1", None)), (
        "collection preview bootstrap missing"
    )
    assert callable(getattr(collection, "registered_collection_grounding_preview_v1", None))


def preview_env(tmp_path, monkeypatch):
    module, ref, reg, root, hashes, clock = environment(tmp_path, monkeypatch)
    tracker = collection.bootstrap_registered_collection_tracker_v1(
        ref, reg, source_root=root, source_hashes=hashes
    )
    state = values()["online"].robot_state
    return tracker, ref, reg, root, hashes, clock, state


def test_preview_fragmented_object_uses_current_marker_and_independent_region(
    tmp_path, monkeypatch
):
    tracker, ref, reg, root, hashes, clock, state = preview_env(tmp_path, monkeypatch)
    current = later(ref, rotation=1, fragment=True)
    clock[0] = current.captured_at
    legacy, _ = collection.bootstrap_collection_tracker(ref, reg.to_payload())
    assert legacy.facts(current, state)["target_visible"]["value"] is None
    result = collection.registered_collection_grounding_preview_v1(tracker, current, state)
    expected = registered_objects.derive_registered_object_geometry(current, reg)
    assert result.status == "DERIVED" and result.grasp_tcp_world_m == expected.grasp_tcp_world_m
    initial = registered_objects.derive_registered_object_geometry(ref, reg)
    assert result.grasp_tcp_world_m != initial.grasp_tcp_world_m
    assert (
        result.destination_world_m is not None
        and result.destination_observation_id == current.observation_id
    )
    assert result.prepare_only is True and result.execution_allowed is False
    assert result.geometric_error_bound_m is None and result.region_geometric_error_bound_m is None
    assert result.region_basis == "RGBD_COLOR_REGION_UNCALIBRATED"
    assert (
        result.geometry_basis == "REGISTERED_RIGID_MODEL"
        and result.object_surface_visibility == "UNKNOWN"
    )
    payload = result.to_payload()
    assert payload["schema_version"] == "native.collection.registered-preview.v1"
    old_digest = result.digest()
    payload["grasp_tcp_world_m"][0] = 999
    assert result.digest() == old_digest
    from cloud_edge_robot_arm.vision.owner_registration import GroundingFrameInputs

    with pytest.raises(TypeError):
        GroundingFrameInputs(**result.to_payload())
    assert (
        not hasattr(result, "target_visible")
        and result.track.observation_checksum_sha256 == current.checksum_sha256
    )


@pytest.mark.parametrize("region", ["missing", "ambiguous", "incomplete"])
def test_preview_requires_independent_complete_current_green_region(tmp_path, monkeypatch, region):
    tracker, ref, reg, root, hashes, clock, state = preview_env(tmp_path, monkeypatch)
    current = later(ref, fragment=True, region=region)
    clock[0] = current.captured_at
    result = collection.registered_collection_grounding_preview_v1(tracker, current, state)
    assert (
        result.status == "UNKNOWN"
        and result.grasp_tcp_world_m is None
        and result.destination_world_m is None
    )


@pytest.mark.parametrize("field", ["connected", "estop_engaged", "collision_detected"])
def test_preview_robot_state_flags_fail_closed(tmp_path, monkeypatch, field):
    tracker, ref, reg, root, hashes, clock, state = preview_env(tmp_path, monkeypatch)
    state = state.model_copy(update={field: field != "connected"})
    result = collection.registered_collection_grounding_preview_v1(tracker, ref, state)
    assert result.status == "UNKNOWN" and result.destination_world_m is None


def test_preview_after_region_expiry_source_checks_and_old_bootstrap_remain(tmp_path, monkeypatch):
    tracker, ref, reg, root, hashes, clock, state = preview_env(tmp_path, monkeypatch)
    original = tracking.OpenCVTargetTracker._geometry

    def expire(self, obs, *args, **kwargs):
        result = original(self, obs, *args, **kwargs)
        clock[0] = obs.captured_at + timedelta(seconds=6)
        return result

    monkeypatch.setattr(tracking.OpenCVTargetTracker, "_geometry", expire)
    result = collection.registered_collection_grounding_preview_v1(tracker, ref, state)
    assert result.status == "UNKNOWN" and result.grasp_tcp_world_m is None
    assert result.track.wrapper_freshness == "REJECTED"
    assert result.track.status == "UNKNOWN" and result.track.geometry is None
    assert result.evaluated_at == result.track.evaluated_at == clock[0]
    assert result.reason == result.track.reason == "capture_time_not_fresh"
    assert result.destination_world_m is None and result.object_center_world_m is None
    assert result.to_payload()["track"]["wrapper_freshness"] == "REJECTED"
    monkeypatch.setattr(tracking.OpenCVTargetTracker, "_geometry", original)
    clock[0] = ref.captured_at
    result = collection.registered_collection_grounding_preview_v1(tracker, ref, state)
    assert result.status == "DERIVED"
    legacy, _ = collection.bootstrap_collection_tracker(ref, reg.to_payload())
    assert legacy.facts(ref, state)["target_visible"]["value"] is True

    def drift(self, obs, *args, **kwargs):
        result = original(self, obs, *args, **kwargs)
        path = root / "src/cloud_edge_robot_arm/vision/tracking.py"
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(tracking.OpenCVTargetTracker, "_geometry", drift)
    with pytest.raises(ValueError):
        collection.registered_collection_grounding_preview_v1(tracker, ref, state)


def test_provider_initial_prerequisites_and_new_family_tag_fail_closed(tmp_path, monkeypatch):
    module, ref, reg, root, hashes, clock = environment(tmp_path, monkeypatch)
    assert type(ref) is RGBDObservation
    for field in ("scene_id", "episode_id", "calibration_version"):
        invalid = revised(ref, **{field: None})
        with pytest.raises(ValueError):
            module.RegisteredObjectTrackerV1(invalid, reg, source_root=root, source_hashes=hashes)
    payload = reg.to_payload()
    payload.pop("marker_family")
    with pytest.raises(ValueError):
        scope = NativeGeometryRegistration(payload)
        module.RegisteredObjectTrackerV1(ref, scope, source_root=root, source_hashes=hashes)
    clock[0] = ref.captured_at + timedelta(seconds=6)
    with pytest.raises(ValueError, match="fresh"):
        module.RegisteredObjectTrackerV1(ref, reg, source_root=root, source_hashes=hashes)
    with pytest.raises(TypeError):
        module.RegisteredObjectTrackerV1(object(), reg, source_root=root, source_hashes=hashes)


def test_preview_context_unknown_is_not_a_visibility_fact(tmp_path, monkeypatch):
    tracker, ref, reg, root, hashes, clock, state = preview_env(tmp_path, monkeypatch)
    invalid = revised(ref, scene_id="other-scene")
    result = collection.registered_collection_grounding_preview_v1(tracker, invalid, state)
    assert result.status == "UNKNOWN" and result.track.geometry is None
    assert result.grasp_tcp_world_m is None and result.destination_world_m is None
    valid = collection.registered_collection_grounding_preview_v1(tracker, ref, state)
    from cloud_edge_robot_arm.edge.evidence.conditions import (
        ConditionSpec,
        OnlineEvidenceSnapshot,
        evaluate_conditions,
    )

    online = OnlineEvidenceSnapshot(
        ref, state, {"registered_preview": valid.to_payload()}, 1, 1, "preview"
    )
    verdict = evaluate_conditions(
        [ConditionSpec("target_visible", "object")], online, now=clock[0]
    )[0]
    assert verdict.status.value == "UNKNOWN"
    with pytest.raises(TypeError):
        collection.registered_collection_grounding_preview_v1(object(), ref, state)


def cut_region(reference, edge):
    current = later(reference, fragment=True)
    with Image.open(io.BytesIO(base64.b64decode(current.rgb_png_base64))) as image:
        rgb = np.array(image)
    depth = (
        np.frombuffer(base64.b64decode(current.depth_float32_base64), dtype="<f4")
        .copy()
        .reshape(240, 320)
    )
    cuts = {
        "left": (slice(160, 180), slice(100, 110)),
        "right": (slice(160, 180), slice(110, 120)),
        "top": (slice(160, 170), slice(100, 120)),
        "bottom": (slice(170, 180), slice(100, 120)),
    }
    rgb[cuts[edge]] = (40, 40, 40)
    depth[cuts[edge]] = 1.2
    output = io.BytesIO()
    Image.fromarray(rgb).save(output, format="PNG")
    return revised(
        current,
        rgb_png_base64=base64.b64encode(output.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
    )


@pytest.mark.parametrize("edge", ["left", "right", "top", "bottom"])
def test_preview_rejects_rectangular_edge_occlusion(tmp_path, monkeypatch, edge):
    tracker, ref, reg, root, hashes, clock, state = preview_env(tmp_path, monkeypatch)
    current = cut_region(ref, edge)
    clock[0] = current.captured_at
    result = collection.registered_collection_grounding_preview_v1(tracker, current, state)
    assert result.status == "UNKNOWN"
    assert result.grasp_tcp_world_m is None and result.destination_world_m is None
    assert result.track.geometry is None
    assert result.track.wrapper_freshness == "CHECKED"


def test_preview_frozen_footprint_cannot_be_rewritten_by_legacy_mask(tmp_path, monkeypatch):
    tracker, ref, reg, root, hashes, clock, state = preview_env(tmp_path, monkeypatch)
    current = cut_region(ref, "right")
    clock[0] = current.captured_at
    mask = tracker._region_tracker.destination["mask"]
    mask[:] = False
    mask[160:180, 100:110] = True
    result = collection.registered_collection_grounding_preview_v1(tracker, current, state)
    assert result.status == "UNKNOWN" and result.destination_world_m is None


def test_preview_rejects_equal_area_translated_region(tmp_path, monkeypatch):
    tracker, ref, reg, root, hashes, clock, state = preview_env(tmp_path, monkeypatch)
    current = later(ref, fragment=True)
    clock[0] = current.captured_at
    with Image.open(io.BytesIO(base64.b64decode(current.rgb_png_base64))) as image:
        rgb = np.array(image)
    rgb[160:180, 100:120] = (255, 255, 255)
    rgb[160:180, 105:125] = (0, 255, 0)
    output = io.BytesIO()
    Image.fromarray(rgb).save(output, format="PNG")
    current = revised(current, rgb_png_base64=base64.b64encode(output.getvalue()).decode())
    result = collection.registered_collection_grounding_preview_v1(tracker, current, state)
    assert result.status == "UNKNOWN" and result.destination_world_m is None
