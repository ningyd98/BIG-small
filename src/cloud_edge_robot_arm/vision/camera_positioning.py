"""Frame measured world features from a movable development RGBD camera."""

from __future__ import annotations

import numpy as np


def position_camera_for_features(
    points_m: np.ndarray, *, current_position_m: tuple[float, float, float],
    intrinsics: tuple[float, float, float, float], image_size: tuple[int, int],
    marker_size_m: float, lowest_marker_z_m: float, target_side_px: float = 28,
) -> tuple[float, float, float] | None:
    points = np.asarray(points_m, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3 or not len(points) or not np.isfinite(points).all():
        raise ValueError("camera framing requires finite measured world features")
    fx, fy, cx, cy = intrinsics
    width, height = image_size
    half_x, half_y = min(cx, width - 1 - cx) - 16, min(cy, height - 1 - cy) - 16
    if min(fx, fy, half_x, half_y, marker_size_m, target_side_px) <= 0:
        raise ValueError("camera framing parameters must be positive")
    center = (points[:, :2].min(axis=0) + points[:, :2].max(axis=0)) / 2
    required_z = float(np.max(points[:, 2] + np.maximum(
        np.abs(points[:, 0] - center[0]) * fx / half_x,
        np.abs(points[:, 1] - center[1]) * fy / half_y,
    )))
    desired_z = lowest_marker_z_m + fy * marker_size_m / target_side_px
    z = max(0.6, required_z, min(current_position_m[2], desired_z))
    position = (float(center[0]), float(center[1]), z)
    if not (-0.1 <= position[0] <= 0.8 and -0.5 <= position[1] <= 0.5 and z <= 2):
        return None
    return position


def oblique_camera_for_features(
    points_m: np.ndarray, *, marker_corners_m: np.ndarray,
    intrinsics: tuple[float, float, float, float], image_size: tuple[int, int],
    current_height_m: float,
    view_direction_xy: tuple[float, float] = (-1, 1),
    angles_deg: tuple[int, ...] = (25, 35, 45),
    image_margin_px: int = 16,
    look_at_m: tuple[float, float, float] | None = None,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """Choose a side-above view using measured features, never scene truth.

    The registered side-outboard tag lies toward +Y. Looking from that side
    separates it and the region from the wrist silhouette. Image measurements
    must still validate every subsequent frame; this is only a framing proposal.
    """
    points, markers = np.asarray(points_m, dtype=float), np.asarray(marker_corners_m, dtype=float)
    if (points.ndim != 2 or points.shape[1] != 3 or not len(points)
            or markers.ndim != 2 or markers.shape[1] != 3 or len(markers) % 4
            or not len(markers) or not np.isfinite(points).all()
            or not np.isfinite(markers).all()):
        raise ValueError("oblique framing requires finite measured features and marker corners")
    aim = ((points.min(axis=0) + points.max(axis=0)) / 2
           if look_at_m is None else np.asarray(look_at_m, dtype=float))
    if aim.shape != (3,) or not np.isfinite(aim).all():
        raise ValueError("camera look-at requires three finite measured coordinates")
    fx, fy, cx, cy = intrinsics
    width, height = image_size
    if type(image_margin_px) is not int or image_margin_px < 3:
        raise ValueError("camera framing must retain the marker depth-patch margin")
    best = None
    best_side = 0.0
    direction = np.asarray(view_direction_xy, dtype=float)
    if not np.isfinite(direction).all() or np.linalg.norm(direction) == 0:
        raise ValueError("camera view direction must be finite and nonzero")
    direction /= np.linalg.norm(direction)
    for height_m in np.linspace(0.6, min(2, max(0.6, current_height_m)), 24):
        if height_m <= aim[2]:
            continue
        for angle in angles_deg:
            distance = (height_m - aim[2]) * np.tan(np.deg2rad(angle))
            position = aim + np.array([distance * direction[0], distance * direction[1],
                                       height_m - aim[2]])
            if not (-0.1 <= position[0] <= 0.8 and -0.5 <= position[1] <= 0.5):
                continue
            backward = position - aim
            backward /= np.linalg.norm(backward)
            right = np.cross([0, 1, 0], backward)
            right /= np.linalg.norm(right)
            up = np.cross(backward, right)
            optical = np.column_stack((right, -up, -backward))
            camera = (np.vstack((points, markers)) - position) @ optical
            if np.any(camera[:, 2] <= 0):
                continue
            pixels = camera[:, :2] / camera[:, 2, None] * [fx, fy] + [cx, cy]
            if np.any(pixels < image_margin_px) or np.any(
                pixels > [width - 1 - image_margin_px, height - 1 - image_margin_px]
            ):
                continue
            corners = pixels[len(points):].reshape(-1, 4, 2)
            side = float(np.linalg.norm(np.roll(corners, -1, axis=1) - corners, axis=2).min())
            if side > best_side:
                best_side = side
                best = ((float(position[0]), float(position[1]), float(position[2])),
                        (float(aim[0]), float(aim[1]), float(aim[2])))
    return best
