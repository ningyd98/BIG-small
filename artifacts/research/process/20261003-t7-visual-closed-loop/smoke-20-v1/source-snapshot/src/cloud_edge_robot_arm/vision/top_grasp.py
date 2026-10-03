"""RGB-D top-grasp calibration for upright boxes and the current MJCF gripper."""

from __future__ import annotations

import math

from cloud_edge_robot_arm.vision.observations import RGBDObservation

# The trusted research caller must verify this asset and the upright rigid-box
# scene family before selecting mujoco_upright_box_v1. No online truth is read.
CALIBRATED_ASSET_SHA256 = "182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08"

_MIN_OBJECT_HEIGHT_M = 0.05
_MAX_OBJECT_HEIGHT_M = 0.10
# Compensate float32 depth rounding near 2 m (e.g. 2 - float32(1.9)).
# This is 0.1 micrometre, not a tolerance for physical size or sensor noise.
_HEIGHT_REPRESENTATION_TOLERANCE_M = 1e-7
_MAX_TOP_PATCH_Z_SPAN_M = 0.008
_TCP_ABOVE_ESTIMATED_CENTER_M = 0.01
# scene.xml: finger body x .075 + geom x .025 + half-length .035
# minus TCP x .105. The calibrated top-down orientation points local +x down.
_FINGERTIP_BELOW_TCP_M = 0.03
_MIN_FINGERTIP_CLEARANCE_M = 0.002


def resolve_top_grasp(
    observation: RGBDObservation, pixel: tuple[int, int], support_z: float,
) -> dict[str, object]:
    """Resolve a calibrated TCP from a visible top center and measured support.

    This is restricted to a rigid upright box resting on the supplied local
    horizontal support and the current MJCF gripper in its top-down orientation.
    The center is a geometric estimate, never a scene/instance lookup. A flat
    3x3 patch alone cannot establish the object's shape, material or orientation;
    the caller must keep the stated scope. Unsupported measurements fail closed.
    """
    if type(support_z) not in {int, float} or not math.isfinite(support_z):
        raise ValueError("top grasp requires a finite metric support height")
    if (
        not isinstance(pixel, (tuple, list)) or len(pixel) != 2
        or any(type(value) is not int for value in pixel)
    ):
        raise ValueError("top grasp pixel must contain two integers")
    u, v = pixel
    if not (1 <= u < observation.width - 1 and 1 <= v < observation.height - 1):
        raise ValueError("top grasp pixel needs a complete interior 3x3 patch")

    depths = observation.depth_values()
    fx, fy, cx, cy = observation.intrinsics
    transform = observation.camera_to_world
    patch_heights: list[float] = []
    for y in range(v - 1, v + 2):
        for x in range(u - 1, u + 2):
            depth = depths[y * observation.width + x]
            if not math.isfinite(depth) or depth <= 0:
                raise ValueError("top grasp patch contains invalid metric depth")
            world_z = (
                transform[8] * (x - cx) * depth / fx
                + transform[9] * (y - cy) * depth / fy
                + transform[10] * depth + transform[11]
            )
            if not math.isfinite(world_z):
                raise ValueError("top grasp patch contains nonfinite world depth")
            patch_heights.append(world_z)
    z_span = max(patch_heights) - min(patch_heights)
    if z_span > _MAX_TOP_PATCH_Z_SPAN_M:
        raise ValueError("top grasp patch is not flat within calibrated world-z variation")

    top = observation.world_point((u, v))
    if not all(math.isfinite(value) for value in (top.x, top.y, top.z)):
        raise ValueError("top grasp surface position must be finite")
    height = top.z - support_z
    if not (
        _MIN_OBJECT_HEIGHT_M - _HEIGHT_REPRESENTATION_TOLERANCE_M
        <= height
        <= _MAX_OBJECT_HEIGHT_M + _HEIGHT_REPRESENTATION_TOLERANCE_M
    ):
        raise ValueError("estimated object height is outside calibrated 0.05..0.10 m range")

    center_z = top.z - height / 2
    tcp_z = center_z + _TCP_ABOVE_ESTIMATED_CENTER_M
    fingertip_clearance = tcp_z - _FINGERTIP_BELOW_TCP_M - support_z
    if fingertip_clearance < _MIN_FINGERTIP_CLEARANCE_M:
        raise ValueError("calibrated fingertip clearance above support is below 0.002 m")

    return {
        "top_grasp_offset_status": "CALIBRATED_RGBD_TOP_GRASP_V1",
        "top_grasp_offset_from_surface_m": tcp_z - top.z,
        "resolved_top_grasp_tcp": {"x": top.x, "y": top.y, "z": tcp_z},
        "estimated_object_height_m": height,
        "estimated_object_center": {"x": top.x, "y": top.y, "z": center_z},
        "estimated_object_center_semantics": "RGBD_GEOMETRIC_ESTIMATE_NOT_GROUND_TRUTH",
        "grasp_geometry_assumption": (
            "upright rigid box resting on measured horizontal support; selected pixel "
            "is its visible top center; current MJCF gripper in top-down orientation"
        ),
        "top_grasp_support_height_m": support_z,
        "top_patch_world_z_span_m": z_span,
        "estimated_fingertip_clearance_m": fingertip_clearance,
        "minimum_fingertip_clearance_m": _MIN_FINGERTIP_CLEARANCE_M,
        "fingertip_below_tcp_m": _FINGERTIP_BELOW_TCP_M,
        "calibrated_object_height_range_m": [_MIN_OBJECT_HEIGHT_M, _MAX_OBJECT_HEIGHT_M],
    }
