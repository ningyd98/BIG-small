"""Current RGBD support for a static development region under foreground occlusion.

The initial complete world rectangle is reprojected with the current camera.
Missing color needs measured foreground depth and at least three current corner
anchors. This is not an extent certificate or a fallback to an old pixel mask.
"""

from __future__ import annotations

import base64
from typing import Any

import cv2
import numpy as np

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.top_grasp import _MAX_TOP_PATCH_Z_SPAN_M
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker, _rgb

_MIN_CURRENT_CORNER_ANCHORS = 3


def measure_servo_region(
    observation: RGBDObservation, tracker: OpenCVTargetTracker,
    *, diagnostics: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    reference = tracker._reference
    region = tracker.destination
    if region is None or observation.source != "mujoco_camera" or any(
        getattr(observation, field) != getattr(reference, field)
        for field in ("episode_id", "scene_id", "source", "width", "height", "intrinsics")
    ):
        return None, "region_reference_binding_changed"
    transform = np.array(observation.camera_to_world).reshape(4, 4)
    original = np.array(reference.camera_to_world).reshape(4, 4)
    if (not np.array_equal(transform, original)) != (
        observation.calibration_version != reference.calibration_version
    ):
        return None, "region_reference_calibration_disagrees"
    if np.array_equal(transform, original):
        complete, reason = tracker._geometry(observation, tracker.destination_color, target=False)
        if complete is not None:
            return complete | {"source": "CURRENT_OPENCV_RGBD"}, None
        if reason not in {
            "region_topology_not_supported_axis_aligned_rectangle", "color_identity_ambiguous",
        }:
            return None, reason
    left, top, right, bottom = region["inside_pixel_rectangle"]
    corner_x = np.array([left, right, right, left])
    corner_y = np.array([top, top, bottom, bottom])
    reference_depth = np.frombuffer(
        base64.b64decode(reference.depth_float32_base64), dtype="<f4",
    ).reshape(reference.height, reference.width)
    world = tracker._points(reference, corner_x, corner_y, reference_depth[corner_y, corner_x])
    camera = (world - transform[:3, 3]) @ transform[:3, :3]
    if np.any(camera[:, 2] <= 0):
        return None, "region_reference_behind_camera"
    fx, fy, cx, cy = observation.intrinsics
    pixels = np.column_stack((fx * camera[:, 0] / camera[:, 2] + cx,
                              fy * camera[:, 1] / camera[:, 2] + cy))
    corners = np.rint(pixels).astype(np.int32)
    if np.any(corners < 1) or np.any(corners[:, 0] >= observation.width - 1) or np.any(
        corners[:, 1] >= observation.height - 1
    ):
        return None, "region_reference_truncated"
    expected = np.zeros((observation.height, observation.width), dtype=np.uint8)
    cv2.fillConvexPoly(expected, corners, 1)
    rgb = _rgb(observation).astype(float)
    chroma = rgb / np.maximum(rgb.sum(axis=2, keepdims=True), 1)
    color = ((np.linalg.norm(chroma - tracker.destination_color, axis=2) < 0.14)
             & (np.ptp(rgb, axis=2) > 30)).astype(np.uint8)
    # The existing tracker removes a gray lighting component for observed
    # target edges. Apply the same hue check to the region's current one-pixel
    # color fringe, retaining all paired-depth and world-reference checks.
    fringe = (cv2.dilate(color, np.ones((3, 3), np.uint8)) > 0) & (color == 0)
    ey, ex = np.nonzero(fringe)
    edge_rgb = rgb[ey, ex]
    edge_pure = edge_rgb - edge_rgb.min(axis=1, keepdims=True)
    edge_chroma = edge_pure / np.maximum(edge_pure.sum(axis=1, keepdims=True), 1)
    region_pure = tracker.destination_color - tracker.destination_color.min()
    region_pure /= max(float(region_pure.sum()), 1e-6)
    shaded = ((np.linalg.norm(edge_chroma - region_pure, axis=1) < 0.20)
              & (np.ptp(edge_rgb, axis=1) >= 14))
    color[ey[shaded], ex[shaded]] = 1
    count, labels, stats, _ = cv2.connectedComponentsWithStats(color, connectivity=8)
    candidates = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 8]
    selected = np.isin(labels, candidates)
    if not candidates:
        return None, "region_current_color_missing"
    depth = np.frombuffer(base64.b64decode(observation.depth_float32_base64), dtype="<f4").reshape(
        observation.height, observation.width,
    )
    valid = np.frombuffer(observation.valid_mask_bytes(), dtype=np.uint8).reshape(depth.shape) > 0
    if not valid[selected].all():
        return None, "region_current_color_depth_invalid"
    ys, xs = np.nonzero(selected)
    points = tracker._points(observation, xs, ys, depth[ys, xs])
    bound = tracker.depth_error_bound_m or 0.0
    span = 2 * bound if bound else _MAX_TOP_PATCH_Z_SPAN_M
    plane = float(region["center"][2])
    plane_points = np.abs(points[:, 2] - plane) <= span
    visible_plane = np.zeros(selected.shape, dtype=bool)
    visible_plane[ys[plane_points], xs[plane_points]] = True
    core = cv2.erode(selected.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    if (
        not core.any() or not visible_plane[core].all()
        or (bound > 0 and np.ptp(points[plane_points, 2]) > span)
    ):
        return None, "region_current_plane_unresolved"
    # Mixed silhouette pixels can retain green RGB while their paired depth
    # belongs to the foreground. They are occlusion, never plane support;
    # interior spikes and non-foreground boundary errors remain rejected.
    if np.any(points[~plane_points, 2] <= plane + span + bound):
        return None, "region_color_boundary_depth_unresolved"
    rays = np.column_stack(((xs - cx) / fx, (ys - cy) / fy, np.ones(len(xs))))
    denominators = rays @ transform[2, :3]
    if np.any(np.abs(denominators) < 1e-9):
        return None, "region_plane_projection_unresolved"
    plane_depth = (plane - transform[2, 3]) / denominators
    if not np.isfinite(plane_depth).all() or np.any(plane_depth <= 0):
        return None, "region_plane_projection_unresolved"
    projected = tracker._points(observation, xs, ys, plane_depth)
    # Propagate the initial measured pixel footprint when comparing a new
    # sampling grid/plane projection; it is already part of the tracker evidence.
    xy_uncertainty = np.array(region["uncertainty_m"])[:2] + bound
    if np.any(projected[:, :2] < np.array(region["min"])[:2] - xy_uncertainty) or np.any(
        projected[:, :2] > np.array(region["max"])[:2] + xy_uncertainty
    ):
        return None, "region_current_color_outside_world_reference"
    anchors = sum(bool(visible_plane[y - 1:y + 2, x - 1:x + 2].any()) for x, y in corners)
    if diagnostics is not None:
        diagnostics["observed_corner_anchors"] = anchors
        diagnostics["minimum_corner_anchors"] = _MIN_CURRENT_CORNER_ANCHORS
    if anchors < _MIN_CURRENT_CORNER_ANCHORS:
        return None, "region_current_corner_anchors_insufficient"
    missing = (expected > 0) & ~visible_plane
    if not valid[missing].all():
        return None, "region_occluder_depth_invalid"
    ys, xs = np.nonzero(missing)
    foreground = tracker._points(observation, xs, ys, depth[ys, xs])
    result = {
        "center": list(region["center"]),
        "source": "CURRENT_RGBD_REPROJECTED_STATIC_REGION_SUPPORT",
        "occluded_pixels": len(foreground), "observed_corner_anchors": anchors,
        "mixed_foreground_edge_pixels": int((~plane_points).sum()),
        "low_object_sidewall_pixels": 0,
        "mixed_occluder_footprint_pixels": 0,
        "formal_geometry_qualification": "UNKNOWN",
    }
    pixel_z_scale = abs(transform[2, 0]) / (2 * fx) + abs(transform[2, 1]) / (2 * fy)
    z_footprint = (
        region["uncertainty_m"][2]
        + np.abs(transform[2, 0] * (xs - cx) / fx + transform[2, 1] * (ys - cy) / fy
                 + transform[2, 2]) * bound
        + (depth[ys, xs] + bound) * pixel_z_scale
    )
    if np.all(foreground[:, 2] > plane + np.maximum(span + bound, z_footprint)):
        return result, None
    yy, xx = np.indices(depth.shape)
    ray_z = (
        transform[2, 0] * (xx - cx) / fx + transform[2, 1] * (yy - cy) / fy
        + transform[2, 2]
    )
    heights = transform[2, 3] + depth * ray_z
    height_errors = (region["uncertainty_m"][2] + np.abs(ray_z) * bound
                     + (depth + bound) * pixel_z_scale)
    high_foreground = valid & (heights > plane + np.maximum(span + bound, height_errors))
    # A placed cube's sidewall approaches the table continuously. Its last
    # measured pixel need not exceed the 8 mm plane-visibility band. Require
    # current target color, connection to high foreground and positive
    # height after propagating the measured pixel/depth footprint. This never
    # excuses an isolated, coplanar or invalid missing-color hole.
    colors = rgb[ys, xs]
    pure_rgb = colors - colors.min(axis=1, keepdims=True)
    pure_chroma = pure_rgb / np.maximum(pure_rgb.sum(axis=1, keepdims=True), 1)
    pure_target = tracker.target_color - tracker.target_color.min()
    pure_target /= max(float(pure_target.sum()), 1e-6)
    pure_region = tracker.destination_color - tracker.destination_color.min()
    pure_region /= max(float(pure_region.sum()), 1e-6)
    # At the object/table silhouette the raster pixel can mix both known colors.
    color_axis = pure_target - pure_region
    weight = np.clip(
        (pure_chroma - pure_region) @ color_axis / max(float(color_axis @ color_axis), 1e-6),
        0, 1,
    )
    mixed_color = pure_region + weight[:, None] * color_axis
    target_side_color = (
        (weight > 0) & (np.linalg.norm(pure_chroma - mixed_color, axis=1) < 0.20)
        & (np.ptp(colors, axis=1) >= 14)
    )
    positive_side = target_side_color & (foreground[:, 2] > plane + z_footprint)
    foreground_mask = high_foreground.copy()
    foreground_mask[ys[positive_side], xs[positive_side]] = True
    _, foreground_labels = cv2.connectedComponents(foreground_mask.astype(np.uint8), connectivity=8)
    connected = np.isin(foreground_labels[ys, xs], np.unique(foreground_labels[high_foreground]))
    sidewall = ~high_foreground[ys, xs] & positive_side & connected
    measured_foreground = high_foreground.copy()
    measured_foreground[ys[sidewall], xs[sidewall]] = True
    near_measured_foreground = cv2.dilate(
        measured_foreground.astype(np.uint8), np.ones((3, 3), np.uint8),
    ) > 0
    # Uncalibrated visibility only: RGB can mix the two surfaces while the
    # paired depth selects the plane. Exclude this one-pixel foreground raster
    # footprint from plane support, never fill it with region color. Both pure
    # color bands, detached holes and depths outside the observed plane band
    # remain unsupported. Calibrated inputs retain the positive-height check.
    mixed_footprint = (
        (bound == 0) & ~high_foreground[ys, xs] & near_measured_foreground[ys, xs]
        & target_side_color
        & (np.linalg.norm(pure_chroma - pure_target, axis=1) >= 0.20)
        & (np.linalg.norm(pure_chroma - pure_region, axis=1) >= 0.20)
        & (np.abs(foreground[:, 2] - plane) <= span)
    )
    if np.any(~high_foreground[ys, xs] & ~sidewall & ~mixed_footprint):
        return None, "region_missing_color_not_explained_by_foreground"
    result["low_object_sidewall_pixels"] = int(sidewall.sum())
    result["mixed_occluder_footprint_pixels"] = int(mixed_footprint.sum())
    return result, None
