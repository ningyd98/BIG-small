"""Real RGB-D payloads exercise the paused post-cloud consistency policy."""

from __future__ import annotations

import base64
import io
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from tests.test_opencv_target_evidence import scene

START = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
BOUNDARY = START + timedelta(seconds=6)


def rebuild(observation, **updates):
    payload = observation.model_dump()
    payload.update(updates)
    payload["checksum_sha256"] = ""
    if "frame_id" in updates:
        payload["observation_id"] = updates["frame_id"]
    if "depth_float32_base64" in updates:
        payload["valid_mask_base64"] = None
    return RGBDObservation.model_validate(payload)


def pair(delta=None):
    reference = scene(
        "reference", started=START, source="mujoco_camera", scene_id="S01_TEST_STATIC"
    )
    fresh = rebuild(reference, frame_id="fresh", captured_at=BOUNDARY + timedelta(seconds=0.01))
    if delta is not None:
        depths = np.asarray(reference.depth_values(), dtype=np.float64)
        depths = (depths + np.asarray(delta)).astype("<f4")
        fresh = rebuild(fresh, depth_float32_base64=base64.b64encode(depths.tobytes()).decode())
    return reference, fresh


def check(reference, fresh, **kwargs):
    from cloud_edge_robot_arm.vision.revalidation import validate_post_cloud_observation

    return validate_post_cloud_observation(reference, fresh, not_before=kwargs.get("at", BOUNDARY))


def test_independent_depth_noise_is_measured_without_certification():
    delta = np.resize([0.001, -0.001], 80 * 64)
    reference, fresh = pair(delta)
    result = check(reference, fresh)
    assert result["policy_id"] == "paused_mujoco_rgb_depth_v1"
    assert result["reference_checksum"] == reference.checksum_sha256
    assert result["fresh_checksum"] == fresh.checksum_sha256
    assert result["valid_pixels"] == 80 * 64
    assert result["depth_max_abs_delta_m"] == pytest.approx(0.001, abs=1e-7)
    assert result["depth_rms_delta_m"] == pytest.approx(0.001, abs=1e-7)
    assert result["depth_mean_delta_m"] == pytest.approx(0, abs=1e-7)
    assert result["physical_identity_or_stability_certified"] is False
    assert "depth_error_bound_m" not in result
    assert reference.captured_at == START and fresh.captured_at > BOUNDARY


@pytest.mark.parametrize("delta", [None, np.zeros(80 * 64)])
def test_equal_depth_bytes_are_allowed_for_a_genuinely_distinct_capture(delta):
    reference, fresh = pair(delta)
    assert check(reference, fresh)["depth_rms_delta_m"] == 0


@pytest.mark.parametrize(
    "kind,value,accepted,reason",
    [
        ("max", 0.009999, True, "depth_max"),
        ("max", 0.010001, False, "depth_max"),
        ("rms", 0.001999, True, "depth_rms"),
        ("rms", 0.002001, False, "depth_rms"),
        ("mean", 0.000249, True, "depth_mean"),
        ("mean", 0.000251, False, "depth_mean"),
    ],
)
def test_each_depth_guard_has_independent_representable_boundary_cases(
    kind, value, accepted, reason
):
    if kind == "max":
        delta = np.zeros(80 * 64)
        delta[0] = value
    elif kind == "rms":
        delta = np.resize([value, -value], 80 * 64)
    else:
        delta = np.full(80 * 64, value)
    reference, fresh = pair(delta)
    if accepted:
        check(reference, fresh)
    else:
        with pytest.raises(ValueError, match=reason):
            check(reference, fresh)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scene_id", "another-scene"),
        ("episode_id", "another-episode"),
        ("calibration_version", "another-calibration"),
        ("source", "rgbd_camera"),
        ("intrinsics", (101, 100, 40, 32)),
        ("camera_to_world", (1, 0, 0, 0.01, 0, -1, 0, 0, 0, 0, -1, 1, 0, 0, 0, 1)),
        ("sim_time_s", 0.1),
    ],
)
def test_changed_session_camera_or_simulation_state_is_rejected(field, value):
    reference, fresh = pair()
    fresh = rebuild(fresh, **{field: value})
    with pytest.raises(ValueError, match="post_cloud_.*(changed|unsupported)"):
        check(reference, fresh)


@pytest.mark.parametrize("field", ["scene_id", "episode_id", "calibration_version"])
def test_missing_reference_binding_cannot_be_repaired_by_fresh_metadata(field):
    reference, fresh = pair()
    reference = rebuild(reference, **{field: None})
    with pytest.raises(ValueError, match="binding_missing"):
        check(reference, fresh)


@pytest.mark.parametrize("variant", ["id", "time", "before_supplier", "checksum", "type"])
def test_retiming_cached_or_invalid_candidate_is_rejected(variant):
    reference, fresh = pair()
    if variant == "id":
        fresh = rebuild(fresh, frame_id=reference.frame_id)
    elif variant == "time":
        fresh = rebuild(fresh, captured_at=reference.captured_at)
    elif variant == "before_supplier":
        fresh = rebuild(fresh, captured_at=BOUNDARY - timedelta(microseconds=1))
    elif variant == "checksum":
        fresh = fresh.model_copy(update={"checksum_sha256": reference.checksum_sha256})
    else:
        fresh = object()
    with pytest.raises(ValueError, match="post_cloud_"):
        check(reference, fresh)


def test_one_changed_rgb_pixel_is_rejected():
    reference, fresh = pair()
    with Image.open(io.BytesIO(base64.b64decode(fresh.rgb_png_base64))) as image:
        rgb = np.asarray(image).copy()
    rgb[0, 0, 0] += 1
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    fresh = rebuild(fresh, rgb_png_base64=base64.b64encode(stream.getvalue()).decode())
    with pytest.raises(ValueError, match="rgb_changed"):
        check(reference, fresh)


def test_changed_resolution_is_rejected():
    reference, _ = pair()
    fresh = scene(
        "fresh", started=BOUNDARY, source="mujoco_camera", scene_id="S01_TEST_STATIC", resolution=2
    )
    with pytest.raises(ValueError, match="changed"):
        check(reference, fresh)


@pytest.mark.parametrize("damage", ["valid_mask", "nonfinite", "encoding"])
def test_model_copy_cannot_bypass_raw_payload_validation(damage):
    reference, fresh = pair()
    if damage == "valid_mask":
        updates = {"valid_mask_base64": base64.b64encode(bytes(80 * 64)).decode()}
    elif damage == "nonfinite":
        depth = np.asarray(fresh.depth_values(), dtype="<f4")
        depth[0] = np.nan
        updates = {"depth_float32_base64": base64.b64encode(depth.tobytes()).decode()}
    else:
        updates = {"rgb_png_base64": "malformed"}
    fresh = fresh.model_copy(update=updates)
    with pytest.raises(ValueError, match="payload_invalid"):
        check(reference, fresh)


def test_changed_valid_mask_is_rejected_even_if_both_models_are_valid():
    reference, fresh = pair()
    depth = np.asarray(fresh.depth_values(), dtype="<f4")
    depth[0] = 0
    fresh = rebuild(fresh, depth_float32_base64=base64.b64encode(depth.tobytes()).decode())
    with pytest.raises(ValueError, match="valid_mask_changed"):
        check(reference, fresh)


def test_no_valid_depth_is_rejected_without_metrics():
    reference, fresh = pair()
    encoded = base64.b64encode(np.zeros(80 * 64, dtype="<f4").tobytes()).decode()
    reference = rebuild(reference, depth_float32_base64=encoded)
    fresh = rebuild(fresh, depth_float32_base64=encoded)
    with pytest.raises(ValueError, match="no_valid_depth"):
        check(reference, fresh)
