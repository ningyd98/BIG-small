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


def registered_camera_bearing(marker_rotation, attachment):
    """Return the horizontal bearing of the registered rigid outboard offset."""
    rotation = np.asarray(marker_rotation, dtype=float).reshape(3, 3)
    attachment = np.asarray(attachment, dtype=float).reshape(4, 4)
    attached_rotation = attachment[:3, :3]
    for matrix in (rotation, attached_rotation):
        if (
            not np.isfinite(matrix).all()
            or not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-8, rtol=0)
            or not np.isclose(np.linalg.det(matrix), 1, atol=1e-8, rtol=0)
        ):
            raise ValueError("camera proposal requires finite proper rotations")
    if not np.isfinite(attachment).all() or not np.array_equal(attachment[3], [0, 0, 0, 1]):
        raise ValueError("camera proposal requires a finite registered attachment")
    offset = attachment[:3, 3]
    registered_horizontal = float(np.linalg.norm(offset[:2]))
    if registered_horizontal <= 0:
        raise ValueError("camera proposal requires a nonzero registered horizontal offset")
    object_rotation = rotation @ attached_rotation.T
    outward_world = object_rotation @ offset
    horizontal = float(np.linalg.norm(outward_world[:2]))
    if not np.isfinite(horizontal) or horizontal < registered_horizontal / 2:
        raise ValueError("registered outboard camera bearing is degenerate in world XY")
    return outward_world[:2] / horizontal, object_rotation, outward_world, horizontal


def _clear_observation_rays(position, features, occluders):
    """Predict occlusion using only measured object and registered robot boxes."""
    clear = np.ones(len(features), dtype=bool)
    for center, rotation, half_size in occluders:
        origin = (position - center) @ rotation
        rays = (features - position) @ rotation
        parallel = np.abs(rays) < 1e-9
        outside = np.any(parallel & (np.abs(origin) > half_size), axis=1)
        divisor = np.where(parallel, 1, rays)
        a, b = (-half_size - origin) / divisor, (half_size - origin) / divisor
        near = np.where(parallel, -np.inf, np.minimum(a, b)).max(axis=1)
        far = np.where(parallel, np.inf, np.maximum(a, b)).min(axis=1)
        hits = ~outside & (np.maximum(near, 0) <= np.minimum(far, 1 - 1e-6))
        clear &= ~hits
    return clear


def registered_current_view_proposals(
    *, marker_center, marker_rotation, attachment, marker_size_m,
    region_corners, intrinsics, image_size, occluders,
):
    """Rank a bounded family of views. A proposal supplies no current visibility evidence."""
    center = np.asarray(marker_center, dtype=float)
    rotation = np.asarray(marker_rotation, dtype=float).reshape(3, 3)
    region = np.asarray(region_corners, dtype=float)
    fx, fy, cx, cy = np.asarray(intrinsics, dtype=float)
    if (
        center.shape != (3,) or region.shape != (4, 3) or not np.isfinite(center).all()
        or not np.isfinite(region).all() or not np.isfinite([fx, fy, cx, cy, marker_size_m]).all()
        or min(fx, fy, marker_size_m) <= 0
    ):
        raise ValueError("camera proposal requires finite registered measured features")
    bearing, object_rotation, outward_world, horizontal = registered_camera_bearing(
        rotation, attachment,
    )
    local_marker = np.array([[-0.5, -0.5, 0], [0.5, -0.5, 0], [0.5, 0.5, 0], [-0.5, 0.5, 0]])
    marker_corners = center + marker_size_m * local_marker @ rotation.T
    features = np.vstack((center, marker_corners, region))
    aim = (features.min(axis=0) + features.max(axis=0)) / 2
    width, height = image_size
    image_max = np.array([width - 1, height - 1])
    margin_px = 16
    for box_center, box_rotation, box_size in occluders:
        if (not np.isfinite(box_center).all() or not np.isfinite(box_rotation).all()
                or not np.isfinite(box_size).all() or np.any(box_size <= 0)):
            raise ValueError("camera proposal requires finite positive occluder geometry")
    ranked = []
    x, y = bearing
    directions = ((x, y), (-y, x), (-x, -y), (y, -x))
    for index, direction in enumerate(directions):
        for height_m in (0.80, 1.05):
            if height_m <= aim[2]:
                continue
            distance = (height_m - aim[2]) * np.tan(np.deg2rad(35))
            position = np.r_[aim[:2] + distance * np.asarray(direction), height_m]
            if not (-0.1 <= position[0] <= 0.8 and -0.5 <= position[1] <= 0.5):
                continue
            backward = position - aim
            backward /= np.linalg.norm(backward)
            right = np.cross([0, 1, 0], backward)
            right /= np.linalg.norm(right)
            up = np.cross(backward, right)
            optical = np.column_stack((right, -up, -backward))
            camera = (features - position) @ optical
            if np.any(camera[:, 2] <= 0):
                continue
            camera_ray = position - center
            facing = float(camera_ray @ rotation[:, 2] / np.linalg.norm(camera_ray))
            if facing <= 0:
                continue
            pixels = camera[:, :2] / camera[:, 2, None] * [fx, fy] + [cx, cy]
            margin = float(np.minimum(pixels, image_max - pixels).min())
            if margin < margin_px:
                continue
            corners = pixels[1:5]
            side_px = float(np.linalg.norm(np.roll(corners, -1, axis=0) - corners, axis=1).min())
            if side_px < 8:
                continue
            visible = _clear_observation_rays(position, features, occluders)
            marker_clear = int(visible[:5].sum())
            region_clear = int(visible[5:].sum())
            score = (
                int(marker_clear == 5 and region_clear >= 3), marker_clear,
                min(region_clear, 3), side_px, facing, margin,
            )
            ranked.append((score, {
                "camera_position_m": position.tolist(),
                "camera_look_at_m": aim.tolist(),
                "relative_azimuth_deg": index * 90,
                "predicted_clear_marker_rays": marker_clear,
                "predicted_clear_region_corners": region_clear,
                "projected_marker_min_side_px": side_px,
                "projected_image_margin_px": margin,
                "marker_facing_cosine": facing,
            }))
    # Python's stable sort preserves the preregistered azimuth/height order on ties.
    ranked.sort(key=lambda candidate: candidate[0], reverse=True)
    return {
        "bearing_xy": bearing.tolist(),
        "world_horizontal_offset_m": horizontal,
        "outward_world_m": outward_world.tolist(),
        "object_rotation": object_rotation.tolist(),
        "ranked": [candidate[1] for candidate in ranked],
    }
