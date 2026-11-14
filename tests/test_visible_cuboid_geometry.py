"""可见顶面与像素尺度回归；真实RGB-D输入不产生动作或补造深度。"""

from __future__ import annotations

import base64
import io
import json
from datetime import UTC, datetime

import cv2
import numpy as np
import pytest
from PIL import Image

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker
from tests.test_molmo_point_association import association_scene


def cuboid(*, size=14, angle=0, damage=None):
    observation = association_scene()
    rgb = np.full((240, 320, 3), 225, dtype=np.uint8)
    depth = np.full((240, 320), 1.4, dtype="<f4")
    rgb[59:89, 117:147] = [20, 240, 20]
    mask = np.zeros(depth.shape, dtype=np.uint8)
    box = cv2.boxPoints(((179, 120), (size, size), angle))
    cv2.fillConvexPoly(mask, np.rint(box).astype(np.int32), 1)
    rgb[mask > 0] = [240, 50, 50]
    depth[mask > 0] = 1.33
    core = cv2.erode(mask, np.ones((3, 3), np.uint8)) > 0
    boundary = (mask > 0) & ~core
    if damage == "mixed_boundary":
        # 原始有效背景深度略低于支撑面，不是补深度或隐藏前景。
        depth[boundary] = 1.4005
    elif damage == "foreground_boundary":
        by, bx = np.nonzero(boundary)
        depth[by[0], bx[0]] = 1.1
    elif damage == "interior_spike":
        depth[120, 179] = 1.1
    elif damage == "below_calibrated_support":
        depth[boundary] = 1.5
    elif damage == "invalid_boundary":
        by, bx = np.nonzero(boundary)
        depth[by[0], bx[0]] = 0
        depth[by[0] - 1, bx[0]] = 0
    elif damage == "invalid_interior":
        depth[120, 179] = 0
    elif damage == "notch":
        left = int(np.nonzero(mask)[1].min())
        rgb[118:123, left : left + size // 3 + 1] = 225
        depth[118:123, left : left + size // 3 + 1] = 1.4
    elif damage == "interior_hole":
        rgb[120, 180] = 225
        depth[120, 180] = 1.1
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    payload = observation.model_dump()
    payload.update(
        rgb_png_base64=base64.b64encode(stream.getvalue()).decode(),
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(),
        valid_mask_base64=None,
        checksum_sha256="",
        captured_at=datetime.now(UTC),
    )
    return RGBDObservation.model_validate(payload)


def track(observation, bound=None):
    return OpenCVTargetTracker(
        observation,
        {
            "original_pixel_target": [179, 120],
            "original_pixel_destination": [132, 74],
            "top_grasp_support_height_m": 0.0,
            "depth_error_bound_m": bound,
        },
    )


def test_mixed_lower_boundary_is_not_used_as_top_without_invented_bound():
    observation = cuboid(damage="mixed_boundary")
    checksum = observation.checksum_sha256
    geometry = track(observation).initial
    assert geometry["top_pixels"] < geometry["visible_pixels"]
    assert geometry["observed_top_min"][2] > 0.069
    assert geometry["observed_body_min"][2] < 0
    assert geometry["extent_complete"] is False
    assert geometry["top_plane_height_interval_m"] is None
    assert observation.checksum_sha256 == checksum


@pytest.mark.parametrize("damage", ["foreground_boundary", "interior_spike"])
def test_unbounded_sensor_cannot_hide_foreground_in_a_top_fallback(damage):
    with pytest.raises(ValueError, match="initial RGB-D identity/extent unavailable"):
        track(cuboid(damage=damage))


def test_calibrated_top_does_not_ignore_boundary_below_support():
    with pytest.raises(ValueError, match="initial RGB-D identity/extent unavailable"):
        track(cuboid(damage="below_calibrated_support"), bound=0.001)


@pytest.mark.parametrize(
    "row,reason",
    [
        (113, "boundary_depth_in_front_of_observed_top"),
        (116, "top_support_height_span_unresolved"),
    ],
    ids=["boundary", "interior"],
)
def test_unresolved_equal_gap_depths_never_become_a_whole_top(row, reason):
    observation = cuboid()
    depth = np.asarray(observation.depth_values(), dtype="<f4").reshape(240, 320)
    depth[113:128, 172:187] = 1.3125
    depth[row, 175] = 1.28125
    depth[row, 176] = 1.25
    payload = observation.model_dump()
    payload.update(
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(), checksum_sha256=""
    )
    with pytest.raises(ValueError, match=reason):
        track(RGBDObservation.model_validate(payload))


def test_continuous_boundary_side_levels_do_not_replace_visible_interior_top():
    observation = cuboid()
    depth = np.asarray(observation.depth_values(), dtype="<f4").reshape(240, 320)
    depth[113:128, 172:187] = 1.3125
    boundary = np.ones((15, 15), dtype=np.uint8)
    boundary[1:-1, 1:-1] = 0
    ys, xs = np.nonzero(boundary)
    for index, (y, x) in enumerate(zip(ys, xs, strict=True)):
        depth[y + 113, x + 172] = (1.3125, 1.34375, 1.375)[index % 3]
    payload = observation.model_dump()
    payload.update(
        depth_float32_base64=base64.b64encode(depth.tobytes()).decode(), checksum_sha256=""
    )
    geometry = track(RGBDObservation.model_validate(payload)).initial
    assert geometry["top_pixels"] < geometry["visible_pixels"]
    assert geometry["observed_top_min"][2] == pytest.approx(0.0875)
    assert geometry["observed_body_min"][2] == pytest.approx(0.025)
    assert geometry["extent_complete"] is False


@pytest.mark.parametrize("size", [14, 24, 32])
@pytest.mark.parametrize("angle", [5, 17, 33, 45, 73])
def test_complete_rotated_raster_top_uses_pixel_footprint_instead_of_solidity(size, angle):
    observation = cuboid(size=size, angle=angle)
    geometry = track(observation, bound=0.001).initial
    assert geometry["silhouette_complete"] is True
    assert geometry["raster_support"]["missing_interior_pixels"] == 0
    assert geometry["extent_complete"] is True
    assert geometry["mask"][120, 179]


@pytest.mark.parametrize("damage", ["notch", "interior_hole", "invalid_boundary"])
def test_missing_color_or_depth_cannot_be_completed_by_rectangle_fit(damage):
    with pytest.raises(ValueError, match="initial RGB-D identity/extent unavailable"):
        track(cuboid(angle=17, damage=damage))


@pytest.mark.parametrize(
    "damage,kind",
    [
        ("invalid_boundary", "BOUNDARY_ADJACENT_INVALID_BACKGROUND"),
        ("invalid_interior", "INTERIOR_INVALID_DEPTH"),
    ],
)
def test_invalid_depth_diagnosis_distinguishes_background_from_interior(damage, kind):
    from cloud_edge_robot_arm.vision.point_association import (
        PointAssociationError,
        associate_target_point,
    )

    observation = cuboid(damage=damage)
    with pytest.raises(PointAssociationError, match="invalid original depth") as caught:
        associate_target_point(observation, (179, 109), target_phrase="red block")
    evidence = caught.value.evidence["invalid_depth_diagnosis"]
    assert evidence["classification"] == kind
    assert evidence["invalid_component_pixels"] == 1
    assert evidence["physical_occluder_identity"] == "UNKNOWN"


def test_episode_source_snapshot_seals_modified_tracking_code(tmp_path):
    from cloud_edge_robot_arm.research.sol_molmo_single_episode import run_single_episode

    output = tmp_path / "episode"
    run_single_episode(output=output)
    snapshot = json.loads((output / "source-hashes.json").read_text())
    assert len(snapshot["files"]["src/cloud_edge_robot_arm/vision/tracking.py"]) == 64
    assert len(snapshot["files"]["src/cloud_edge_robot_arm/vision/top_grasp.py"]) == 64
