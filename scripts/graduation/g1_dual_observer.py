"""Read the two registered prints from one unmodified full RGB-D frame, without world state."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math

import cv2
import numpy as np
from PIL import Image
from scripts.graduation import g1_dual_asset as asset

from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import (
    _MAX_MARKER_PLANE_RESIDUAL_M,
    PoseMarkerEstimate,
    _decode_subpix_rejected_candidates,
)


def physical_candidates(direct, recovered):
    """Merge two observations of the same printed quad; separate same-ID prints stay distinct."""
    candidates = []
    ambiguous = False
    for origin, rows in (("direct", direct), ("exact_rejected", recovered)):
        for code, raw_corners in rows:
            corners = np.asarray(raw_corners, dtype=float).reshape(4, 2)
            for previous in candidates:
                # Permit a different starting corner when comparing geometric footprints.
                shift, distance = min(
                    (
                        (
                            k,
                            float(
                                np.linalg.norm(
                                    corners - np.roll(previous["corners"], k, axis=0), axis=1
                                ).max()
                            ),
                        )
                        for k in range(4)
                    ),
                    key=lambda pair: pair[1],
                )
                if distance <= 1.0:
                    if previous["id"] != code or shift or origin in previous["origins"]:
                        ambiguous = True
                    previous["origins"].append(origin)
                    break
            else:
                candidates.append(dict(id=int(code), corners=corners, origins=[origin]))
    return candidates, ambiguous


def _decode(gray):
    params = cv2.aruco.DetectorParameters()
    params.errorCorrectionRate = 0.0
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    corners, ids, rejected = cv2.aruco.ArucoDetector(dictionary, params).detectMarkers(gray)
    direct = [] if ids is None else list(zip(ids.ravel(), corners, strict=True))
    recovered = []
    if rejected:
        try:
            extra, extra_ids = _decode_subpix_rejected_candidates(gray, rejected, dictionary)
        except ValueError as exc:
            if str(exc) != "ambiguous exact marker dictionary match":
                raise
            candidates, _ = physical_candidates(direct, [])
            return candidates, True, len(rejected)
        if extra_ids is not None:
            recovered = list(zip(extra_ids.ravel(), extra, strict=True))
    candidates, ambiguous = physical_candidates(direct, recovered)
    return candidates, ambiguous, len(rejected)


def _empty_side(marker_id):
    return dict(
        marker_id=marker_id,
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
    )


def _measure_side(frame, geometry, candidate, depth):
    code, corners = candidate["id"], candidate["corners"]
    marker = geometry["development_dual"]["markers"][str(code)]
    side = _empty_side(code)
    side.update(observed=True, ordered_corners_px=corners.tolist(), origins=candidate["origins"])

    def refuse(reason):
        side["reason"] = reason
        return side

    if not np.isfinite(corners).all() or any(
        not (1 <= x < frame.width - 2 and 1 <= y < frame.height - 2) for x, y in corners
    ):
        return refuse("marker_boundary_clipped")
    side_px = np.linalg.norm(np.roll(corners, -1, axis=0) - corners, axis=1)
    side["side_lengths_px"] = side_px.tolist()
    if side_px.min() < 8:
        return refuse("marker_resolution_insufficient")
    tx = np.asarray(frame.camera_to_world).reshape(4, 4)
    fx, fy, cx, cy = frame.intrinsics
    world = []
    for x, y in (*corners, corners.mean(axis=0)):
        u, v = int(round(float(x))), int(round(float(y)))
        patch = depth[v - 1 : v + 2, u - 1 : u + 2]
        positive = np.isfinite(patch) & (patch > 0)
        valid = patch.shape == (3, 3) and bool(positive.all())
        z = float(np.median(patch)) if valid else None
        side["depth_samples"].append(
            dict(
                pixel=[float(x), float(y)],
                positive_count=int(positive.sum()),
                optical_depth_values_m=patch.ravel().tolist(),
                median_optical_depth_m=z,
            )
        )
        if valid:
            world.append((tx @ [(x - cx) * z / fx, (y - cy) * z / fy, z, 1])[:3])
    if len(world) != 5:
        return refuse("marker_metric_depth_unavailable")
    metric = np.asarray(world[:4])
    lengths = np.linalg.norm(np.roll(metric, -1, axis=0) - metric, axis=1)
    side["measured_edge_lengths_m"] = lengths.tolist()
    if np.any(abs(lengths / marker["marker_size_m"] - 1) > 0.30):
        return refuse("registered_marker_size_inconsistent")
    center = metric.mean(axis=0)
    _, _, basis = np.linalg.svd(metric - center)
    plane = dict(
        threshold_m=_MAX_MARKER_PLANE_RESIDUAL_M,
        center_residual_m=abs(float((world[4] - center) @ basis[-1])),
        max_corner_residual_m=float(abs((metric - center) @ basis[-1]).max()),
    )
    side["plane"] = plane
    if max(plane["center_residual_m"], plane["max_corner_residual_m"]) > plane["threshold_m"]:
        return refuse("marker_depth_not_planar")
    x_axis = metric[1] - metric[0]
    x_axis /= np.linalg.norm(x_axis)
    normal = np.cross(x_axis, metric[0] - metric[3])
    if np.linalg.norm(normal) < 1e-8:
        return refuse("ordered_marker_axes_degenerate")
    normal /= np.linalg.norm(normal)
    world_marker = np.eye(4)
    world_marker[:3, :3] = np.column_stack((x_axis, np.cross(normal, x_axis), normal))
    world_marker[:3, 3] = world[4]
    world_object = world_marker @ np.linalg.inv(np.asarray(marker["object_T_marker"]).reshape(4, 4))
    grasp = (world_object @ np.asarray(geometry["object_to_tcp"]).reshape(4, 4))[:3, 3]
    top = (world_object @ [0, 0, geometry["object_half_extent_m"][2], 1])[:3]
    side.update(
        marker_center_world_m=world[4].tolist(),
        rotation_marker_to_world=world_marker[:3, :3].ravel().tolist(),
        rotation_object_to_world=world_object[:3, :3].ravel().tolist(),
        upright_zz=float(world_object[2, 2]),
    )
    if world_object[2, 2] < 0.98:
        return refuse("registered_object_not_upright")
    side.update(
        usable=True,
        status="OBSERVED",
        reason="uncalibrated_single_frame_pose_estimate",
        object_center_world_m=world_object[:3, 3].tolist(),
        object_top_world_m=top.tolist(),
        grasp_world_m=grasp.tolist(),
    )
    return side


def measure_frame(observation, geometry):
    """Also used in fresh offline workers; no history, crops, label masks or simulator inputs."""
    asset.validate_geometry(geometry)
    if type(observation) is not RGBDObservation:
        raise TypeError("exact original RGB-D observation required")
    frame = RGBDObservation.model_validate(observation.model_dump())
    sides = {str(i): _empty_side(i) for i in asset.CENTERS}
    result = dict(
        observation_id=frame.observation_id,
        frame_id=frame.frame_id,
        checksum=frame.checksum_sha256,
        captured_at=frame.captured_at.isoformat(),
        sim_time_s=frame.sim_time_s,
        scene_id=frame.scene_id,
        episode_id=frame.episode_id,
        registration_id=geometry["registration_id"],
        asset_sha256=asset.ASSET_SHA,
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

    def refuse(reason):
        result["reason"] = reason
        return result

    if frame.scene_id != asset.SCENE_ID or not frame.episode_id:
        return refuse("registered_scene_mismatch")
    camera = frame.model_dump(mode="json", include=set(geometry["camera"]))
    if camera != geometry["camera"]:
        return refuse("registered_camera_mismatch")
    with Image.open(io.BytesIO(base64.b64decode(frame.rgb_png_base64))) as im:
        gray = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2GRAY)
    candidates, ambiguous, rejected_count = _decode(gray)
    result["rejected_candidate_count"] = rejected_count
    result["candidates"] = [
        dict(id=c["id"], ordered_corners_px=c["corners"].tolist(), origins=c["origins"])
        for c in candidates
    ]
    ids = sorted(c["id"] for c in candidates)
    result["observed_ids"] = ids
    for code in set(ids) & asset.CENTERS.keys():
        sides[str(code)]["observed"] = True
    if ambiguous or any(i not in asset.CENTERS for i in ids) or len(ids) != len(set(ids)):
        reason = (
            "ambiguous_marker_identity"
            if ambiguous
            else "foreign_marker_id"
            if any(i not in asset.CENTERS for i in ids)
            else "duplicate_marker_id"
        )
        for side in sides.values():
            if side["observed"]:
                side["reason"] = reason
        return refuse(reason)
    depth = np.frombuffer(base64.b64decode(frame.depth_float32_base64), dtype="<f4").reshape(
        frame.height, frame.width
    )
    for candidate in candidates:
        sides[str(candidate["id"])] = _measure_side(frame, geometry, candidate, depth)
    valid = sorted(i for i in ids if sides[str(i)]["usable"])
    result["usable_ids"] = valid
    if not valid:
        reasons = [sides[str(i)]["reason"] for i in ids]
        return refuse(
            reasons[0]
            if len(set(reasons)) == 1
            else "no_valid_registered_marker"
            if reasons
            else "known_marker_not_observed"
        )
    if len(valid) == 2:
        distance = float(
            np.linalg.norm(np.asarray(sides["7"]["grasp_world_m"]) - sides["8"]["grasp_world_m"])
        )
        result["target_disagreement_m"] = distance
        if distance > geometry["development_dual"]["agreement_m"]:
            return refuse("dual_marker_grasp_conflict")
    selected = valid[0]
    result.update(usable=True, reason="development_registered_current_rgbd", selected_id=selected)
    for field in (
        "object_center_world_m",
        "object_top_world_m",
        "rotation_object_to_world",
        "grasp_world_m",
    ):
        result[field] = sides[str(selected)][field]
    return result


def _pose_estimate(frame, result, geometry):
    code = result["selected_id"]
    ids = tuple(result["observed_ids"])
    if code is None:
        h = hashlib.sha256(
            json.dumps(geometry["development_dual"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return PoseMarkerEstimate(
            "UNKNOWN",
            result["reason"],
            frame.observation_id,
            frame.checksum_sha256,
            frame.captured_at,
            h,
            ids,
        )
    side = result["by_id"][str(code)]
    rotation = side["rotation_marker_to_world"]
    return PoseMarkerEstimate(
        "OBSERVED",
        side["reason"],
        frame.observation_id,
        frame.checksum_sha256,
        frame.captured_at,
        asset.pose_registration(code).digest(),
        ids,
        tuple(tuple(p) for p in side["ordered_corners_px"]),
        tuple(side["marker_center_world_m"]),
        tuple(rotation),
        math.atan2(rotation[3], rotation[0]),
        tuple(side["measured_edge_lengths_m"]),
        min(side["side_lengths_px"]),
    )


def derive(frame, geometry, provenance):
    from cloud_edge_robot_arm.vision.registered_objects import RegisteredObjectGeometry

    result = measure_frame(frame, geometry)
    marker = _pose_estimate(frame, result, geometry)
    common = dict(
        provenance, marker_registration_hash=marker.registration_hash, marker_estimate=marker
    )
    if not result["usable"]:
        return RegisteredObjectGeometry("UNKNOWN", result["reason"], **common)
    return RegisteredObjectGeometry(
        "DERIVED",
        "uncalibrated_registered_model_derivation",
        **common,
        object_center_world_m=tuple(result["object_center_world_m"]),
        rotation_object_to_world=tuple(result["rotation_object_to_world"]),
        grasp_tcp_world_m=tuple(result["grasp_world_m"]),
    )


def servo_measure(frame, diagnostics=None):
    geometry = asset.geometry_descriptor()
    result = measure_frame(frame, geometry)
    if diagnostics is not None:
        diagnostics.update(result)
    marker = _pose_estimate(frame, result, geometry)
    if result["usable"]:
        return np.asarray(result["grasp_world_m"]), marker
    if result["reason"] in {
        "known_marker_not_observed",
        "marker_boundary_clipped",
        "marker_resolution_insufficient",
    }:
        return None, marker
    raise ValueError("servo registered marker rejected: " + result["reason"])


def selected_id(estimate):
    return next(
        (
            i
            for i in estimate.observed_marker_ids
            if i in asset.CENTERS
            and asset.pose_registration(i).digest() == estimate.registration_hash
        ),
        None,
    )


def matches_current_owner(frame, registration, geometry):
    payload = registration.to_payload()
    result = measure_frame(frame, payload)
    if not result["usable"]:
        return False
    expected = _pose_estimate(frame, result, payload)
    return (
        expected == geometry.marker_estimate
        and expected.registration_hash == geometry.marker_registration_hash
        and tuple(result["grasp_world_m"]) == geometry.grasp_tcp_world_m
        and tuple(result["object_center_world_m"]) == geometry.object_center_world_m
        and tuple(result["rotation_object_to_world"]) == geometry.rotation_object_to_world
    )
