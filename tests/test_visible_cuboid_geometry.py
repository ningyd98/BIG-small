"""可见顶面与像素尺度回归；真实RGB-D输入不产生动作或补造深度。"""

from __future__ import annotations

import base64
import io
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
    elif damage == "interior_hole":
        rgb[120, 179] = 225
        depth[120, 179] = 1.1
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
