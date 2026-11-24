"""Independent current-frame G1 mark, plane, and rigid-grasp estimates for both mounts."""

import base64
import hashlib
import io
import json
import math
from functools import lru_cache
from itertools import combinations

import cv2
import numpy as np
from PIL import Image
from scripts.graduation.g1_visibility_grid import CELLS, find_grids

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import (
    _MAX_MARKER_PLANE_RESIDUAL_M,
    PoseMarkerEstimate,
    PoseMarkerRegistration,
)


def _empty(code):
    return dict(
        marker_id=code,
        observed=False,
        usable=False,
        status="UNKNOWN",
        reason="known_marker_not_observed",
        ordered_corners_px=None,
        side_lengths_px=None,
        depth_samples=[],
        plane=None,
        marker_center_world_m=None,
        rotation_marker_to_world=None,
        measured_edge_lengths_m=None,
        upright_zz=None,
        object_center_world_m=None,
        rotation_object_to_world=None,
        object_top_world_m=None,
        grasp_world_m=None,
        grid_support=None,
    )


@lru_cache(maxsize=36)
def _triples(count):
    idx = np.int32(list(combinations(range(count), 3)))
    if len(idx) > 192:
        idx = idx[np.linspace(0, len(idx) - 1, 192, dtype=int)]
    return idx


def _rays(xy, intrinsics):
    fx, fy, cx, cy = intrinsics
    xy = (xy - [cx, cy]) / [fx, fy]
    return np.column_stack((xy, np.ones(len(xy))))


def _plane(frame, grid, depth, side):
    centers = CELLS @ grid["basis"] + grid["center"]
    pixels = np.rint(centers).astype(int)
    z = depth[pixels[:, 1], pixels[:, 0]].astype(float)
    good = np.flatnonzero(np.isfinite(z) & (z > 0))
    side["depth_samples"] = [
        dict(
            cell=j,
            pixel=p.tolist(),
            valid=bool(np.isfinite(z[j]) and z[j] > 0),
            optical_z_m=float(z[j]) if np.isfinite(z[j]) and z[j] > 0 else None,
        )
        for j, p in enumerate(pixels)
    ]
    if len(good) < 12 or len(np.unique(pixels[good], axis=0)) < 12:
        return "marker_metric_depth_unavailable"
    points = _rays(pixels[good], frame.intrinsics) * z[good, None]
    nearest = points[_triples(len(points))]
    normals = np.cross(nearest[:, 1] - nearest[:, 0], nearest[:, 2] - nearest[:, 0])
    sizes = np.linalg.norm(normals, axis=1)
    use = sizes > 1e-8
    if not use.any():
        return "marker_depth_not_planar"
    normals = normals[use] / sizes[use, None]
    intercepts = np.sum(normals * nearest[use, 0], axis=1)
    deviations = abs(normals @ points.T - intercepts[:, None])
    counts = (deviations <= _MAX_MARKER_PLANE_RESIDUAL_M).sum(axis=1)
    best = np.lexsort((np.median(deviations, axis=1), -counts))[0]
    selected = deviations[best] <= _MAX_MARKER_PLANE_RESIDUAL_M
    for _ in range(2):
        if selected.sum() < max(12, math.ceil(0.75 * len(points))):
            return "marker_depth_not_planar"
        cloud = points[selected]
        origin = cloud.mean(axis=0)
        _, _, vectors = np.linalg.svd(cloud - origin, full_matrices=False)
        normal = vectors[-1]
        residuals = abs((points - origin) @ normal)
        selected = residuals <= _MAX_MARKER_PLANE_RESIDUAL_M
    cells = good[selected]
    quadrants = {(bool(CELLS[i, 0] > 0), bool(CELLS[i, 1] > 0)) for i in cells}
    side["plane"] = dict(
        threshold_m=_MAX_MARKER_PLANE_RESIDUAL_M,
        valid_cells=len(good),
        inlier_cells=len(cells),
        quadrant_count=len(quadrants),
        inlier_cell_indices=cells.tolist(),
        unit_normal_camera=normal.tolist(),
        point_on_plane_camera_m=origin.tolist(),
        residuals_m=residuals.tolist(),
        positive_cell_indices=good.tolist(),
    )
    if len(cells) < max(12, math.ceil(0.75 * len(good))) or len(quadrants) != 4:
        return "marker_depth_not_planar"
    rays = _rays(np.vstack((grid["corners"], grid["center"])), frame.intrinsics)
    cosines = rays @ normal
    if (abs(cosines) < 1e-8).any():
        return "marker_depth_not_planar"
    ranges = (normal @ origin) / cosines
    if not np.isfinite(ranges).all() or (ranges <= 0).any():
        return "marker_metric_depth_unavailable"
    tx = np.reshape(frame.camera_to_world, (4, 4))
    return (rays * ranges[:, None]) @ tx[:3, :3].T + tx[:3, 3]


def _measure_side(frame, geometry, marker, grid, depth):
    code = grid["id"]
    p = grid["corners"]
    side = _empty(code)
    side.update(
        observed=True,
        ordered_corners_px=p.tolist(),
        origins=grid["origins"],
        side_lengths_px=np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1).tolist(),
        grid_support=grid["grid_support"],
    )
    world = _plane(frame, grid, depth, side)
    if isinstance(world, str):
        side["reason"] = world
        return side
    metric = world[:4]
    lengths = np.linalg.norm(np.roll(metric, -1, axis=0) - metric, axis=1)
    side["measured_edge_lengths_m"] = lengths.tolist()
    if (abs(lengths / marker["marker_size_m"] - 1) > 0.30).any():
        side["reason"] = "registered_marker_size_inconsistent"
        return side
    # Fit the two registered axes to all four edges before composing the rigid attachment.
    xy = np.column_stack(
        (
            metric[1] - metric[0] + metric[2] - metric[3],
            metric[0] - metric[3] + metric[1] - metric[2],
        )
    )
    left, singular, right = np.linalg.svd(xy, full_matrices=False)
    if singular.min() < 1e-8:
        side["reason"] = "ordered_marker_axes_degenerate"
        return side
    xy = left @ right
    marker_pose = np.eye(4)
    marker_pose[:3, :3] = np.column_stack((xy, np.cross(xy[:, 0], xy[:, 1])))
    marker_pose[:3, 3] = world[4]
    object_pose = marker_pose @ np.linalg.inv(np.reshape(marker["object_T_marker"], (4, 4)))
    side.update(
        marker_center_world_m=world[4].tolist(),
        rotation_marker_to_world=marker_pose[:3, :3].ravel().tolist(),
        rotation_object_to_world=object_pose[:3, :3].ravel().tolist(),
        upright_zz=float(object_pose[2, 2]),
    )
    if object_pose[2, 2] < 0.98:
        side["reason"] = "registered_object_not_upright"
        return side
    side.update(
        usable=True,
        status="OBSERVED",
        reason="uncalibrated_single_frame_pose_estimate",
        object_center_world_m=object_pose[:3, 3].tolist(),
        object_top_world_m=(object_pose @ [0, 0, geometry["object_half_extent_m"][2], 1])[
            :3
        ].tolist(),
        grasp_world_m=(object_pose @ np.reshape(geometry["object_to_tcp"], (4, 4)))[:3, 3].tolist(),
    )
    return side


def measure_frame(observation, geometry):
    """Decode current physical prints under the caller's bound scene and asset registration."""
    if type(observation) is not RGBDObservation:
        raise TypeError("current RGBDObservation required")
    frame = RGBDObservation.model_validate(observation.model_dump())
    pose = geometry["pose_marker"]
    dual = geometry.get("development_dual")
    if dual is not None:
        if dual["agreement_m"] != 0.010 or set(dual["markers"]) != {"7", "8"}:
            raise ValueError("registered G1 two-marker arbitration changed")
        markers = {int(k): v for k, v in dual["markers"].items()}
    else:
        markers = {pose["marker_id"]: dict(**pose, object_T_marker=geometry["marker_to_object"])}
    if any(m["dictionary"] != "DICT_4X4_50" for m in markers.values()):
        raise ValueError("unsupported registered dictionary")
    sides = {str(code): _empty(code) for code in markers}
    result = dict(
        observation_id=frame.observation_id,
        frame_id=frame.frame_id,
        checksum=frame.checksum_sha256,
        captured_at=frame.captured_at.isoformat(),
        sim_time_s=frame.sim_time_s,
        scene_id=frame.scene_id,
        episode_id=frame.episode_id,
        registration_id=geometry["registration_id"],
        asset_sha256=pose["marked_asset_sha256"],
        usable=False,
        selected_id=None,
        observed_ids=[],
        usable_ids=[],
        by_id=sides,
        candidates=[],
        rejected_candidate_count=None,
        target_disagreement_m=None,
        object_center_world_m=None,
        object_top_world_m=None,
        rotation_object_to_world=None,
        grasp_world_m=None,
    )
    if not frame.scene_id or not frame.episode_id or not frame.calibration_version:
        result["reason"] = "registered_camera_context_missing"
        return result
    if frame.model_dump(mode="json", include=set(geometry["camera"])) != geometry["camera"]:
        result["reason"] = "registered_camera_mismatch"
        return result
    with Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))) as im:
        gray = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2GRAY)
    depth = np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<f4").reshape(
        frame.height, frame.width
    )
    candidates, ambiguous, rejected_count = find_grids(
        gray, depth, math.sqrt(frame.intrinsics[0] * frame.intrinsics[1]), pose["marker_size_m"]
    )
    result["rejected_candidate_count"] = rejected_count
    result["candidates"] = [
        dict(
            id=c["id"],
            ordered_corners_px=c["corners"].tolist(),
            origins=c["origins"],
            front_face_ambiguous=c["front_face_ambiguous"],
        )
        for c in candidates
    ]
    ids = sorted(c["id"] for c in candidates)
    result["observed_ids"] = ids
    if ambiguous or any(code not in markers for code in ids) or len(set(ids)) != len(ids):
        reason = (
            "ambiguous_marker_identity"
            if ambiguous
            else "foreign_marker_id"
            if any(code not in markers for code in ids)
            else "duplicate_marker_id"
        )
        result["reason"] = reason
        for code in set(ids) & markers.keys():
            sides[str(code)].update(observed=True, reason=reason)
        return result
    for c in candidates:
        code = c["id"]
        sides[str(code)] = _measure_side(frame, geometry, markers[code], c, depth)
    valid = sorted(code for code in ids if sides[str(code)]["usable"])
    result["usable_ids"] = valid
    if not valid:
        reasons = {sides[str(code)]["reason"] for code in ids}
        result["reason"] = (
            next(iter(reasons))
            if len(reasons) == 1
            else "no_valid_registered_marker"
            if reasons
            else "known_marker_not_observed"
        )
        return result
    if len(valid) == 2:
        distance = float(
            np.linalg.norm(np.subtract(sides["7"]["grasp_world_m"], sides["8"]["grasp_world_m"]))
        )
        result["target_disagreement_m"] = distance
        if distance > dual["agreement_m"]:
            result["reason"] = "dual_marker_grasp_conflict"
            return result
    selected = valid[0]
    result.update(usable=True, selected_id=selected, reason="development_registered_current_rgbd")
    for field in (
        "object_center_world_m",
        "object_top_world_m",
        "rotation_object_to_world",
        "grasp_world_m",
    ):
        result[field] = sides[str(selected)][field]
    return result


def pose_estimate(frame, result, geometry):
    """Carry the selected mark's registered identity and this frame's evidence into the servo."""
    code = result["selected_id"]
    pose = geometry["pose_marker"]
    ids = tuple(result["observed_ids"])
    if code is None:
        digest = PoseMarkerRegistration(**pose).digest()
        if "development_dual" in geometry:
            data = json.dumps(geometry["development_dual"], sort_keys=True, separators=(",", ":"))
            digest = hashlib.sha256(data.encode()).hexdigest()
        return PoseMarkerEstimate(
            "UNKNOWN",
            result["reason"],
            frame.observation_id,
            frame.checksum_sha256,
            frame.captured_at,
            digest,
            ids,
        )
    side = result["by_id"][str(code)]
    registration = PoseMarkerRegistration(**dict(pose, marker_id=code))
    rotation = tuple(side["rotation_marker_to_world"])
    return PoseMarkerEstimate(
        "OBSERVED",
        side["reason"],
        frame.observation_id,
        frame.checksum_sha256,
        frame.captured_at,
        registration.digest(),
        ids,
        tuple(tuple(p) for p in side["ordered_corners_px"]),
        tuple(side["marker_center_world_m"]),
        rotation,
        math.atan2(rotation[3], rotation[0]),
        tuple(side["measured_edge_lengths_m"]),
        min(side["side_lengths_px"]),
    )
