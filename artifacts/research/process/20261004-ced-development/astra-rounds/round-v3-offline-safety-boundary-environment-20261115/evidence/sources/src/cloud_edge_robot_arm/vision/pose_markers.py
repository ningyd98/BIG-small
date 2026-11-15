"""Developmental RGBD marker estimates; no calibrated or continuous-motion bounds.

Only RGBDObservation and registered marker geometry enter detection. Scene/physics
truth and instance IDs are not inputs. This does not admit a grasp profile or
change native safety/evidence status.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

from cloud_edge_robot_arm.vision.observations import RGBDObservation

BASE_ASSET_SHA256 = "66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2"
MARKER_SIZE_M = 0.0525  # six cells plus one quiet cell on either side fit the 70mm face


@dataclass(frozen=True)
class PoseMarkerRegistration:
    marker_id: int
    marker_size_m: float
    marked_asset_sha256: str
    dictionary: Literal["DICT_4X4_50"] = "DICT_4X4_50"

    def __post_init__(self) -> None:
        if (
            type(self.marker_id) is not int
            or not 0 <= self.marker_id < 50
            or type(self.marker_size_m) not in {int, float}
            or not math.isfinite(self.marker_size_m)
            or self.marker_size_m <= 0
            or self.dictionary != "DICT_4X4_50"
            or not isinstance(self.marked_asset_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", self.marked_asset_sha256)
        ):
            raise ValueError("known marker geometry and marked asset SHA256 are required")

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()


@dataclass(frozen=True)
class PoseMarkerEstimate:
    status: Literal["OBSERVED", "UNKNOWN"]
    reason: str
    observation_id: str
    observation_checksum_sha256: str
    captured_at: datetime
    registration_hash: str
    observed_marker_ids: tuple[int, ...] = ()
    ordered_corners_px: tuple[tuple[float, float], ...] | None = None
    marker_center_world_m: tuple[float, float, float] | None = None
    rotation_marker_to_world: tuple[float, ...] | None = None
    yaw_world_rad: float | None = None
    measured_edge_lengths_m: tuple[float, ...] | None = None
    measured_min_side_px: float | None = None
    geometric_error_bound_m: None = None
    angular_velocity_bound_rad_s: None = None
    stability_status: Literal["UNKNOWN"] = "UNKNOWN"


def _decode_subpix_rejected_candidates(
    gray: Any, rejected: Any, dictionary: Any
) -> tuple[tuple[Any, ...], Any]:
    """在SUBPIX模式下对四角候选先做亚像素角点细化与双线性透视采样，仍要求0比特误差精确匹配。"""
    import cv2
    import numpy as np

    expected = np.stack([
        (cv2.aruco.generateImageMarker(dictionary, marker_id, 6) > 0).astype(np.uint8)
        for marker_id in range(50)
    ])
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    ppc = 8
    side = 6 * ppc
    margin = 2
    dst = np.array(
        [[0, 0], [side - 1, 0], [side - 1, side - 1], [0, side - 1]], dtype=np.float32
    )
    matched_corners = []
    matched_ids = []
    height, width = gray.shape
    for candidate in rejected:
        pts = np.asarray(candidate, dtype=np.float32).reshape(4, 2)
        if (
            np.any(pts[:, 0] < 2.0)
            or np.any(pts[:, 0] >= width - 2.0)
            or np.any(pts[:, 1] < 2.0)
            or np.any(pts[:, 1] >= height - 2.0)
        ):
            continue
        if float(np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1).min()) < 8.0:
            continue
        edge0 = pts[1] - pts[0]
        edge1 = pts[2] - pts[1]
        if float(edge0[0] * edge1[1] - edge0[1] * edge1[0]) < 0.0:
            pts = pts[[0, 3, 2, 1]]
        refined = cv2.cornerSubPix(
            gray.copy(), pts.reshape(-1, 1, 2).copy(), (2, 2), (-1, -1), criteria
        ).reshape(4, 2)
        transform = cv2.getPerspectiveTransform(refined, dst)
        warped = cv2.warpPerspective(gray, transform, (side, side), flags=cv2.INTER_LINEAR)
        _, thresholded = cv2.threshold(warped, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        bits = np.zeros((6, 6), dtype=np.uint8)
        for row in range(6):
            for col in range(6):
                cell = thresholded[
                    row * ppc + margin : (row + 1) * ppc - margin,
                    col * ppc + margin : (col + 1) * ppc - margin,
                ]
                bits[row, col] = 1 if float(cell.mean()) > 127.5 else 0
        matches = []
        for rotation_k in range(4):
            marker_ids = np.flatnonzero(np.all(expected == np.rot90(bits, rotation_k), axis=(1, 2)))
            matches.extend((int(marker_id), rotation_k) for marker_id in marker_ids)
        if len(matches) > 1:
            raise ValueError("ambiguous exact marker dictionary match")
        if matches:
            marker_id, rotation_k = matches[0]
            ordered = np.roll(refined, -rotation_k, axis=0).reshape(1, 4, 2)
            matched_corners.append(ordered)
            matched_ids.append([marker_id])
    if not matched_ids:
        return (), None
    return tuple(matched_corners), np.array(matched_ids, dtype=np.int32)


def detect_pose_marker(
    observation: RGBDObservation,
    registration: PoseMarkerRegistration,
    *,
    corner_refinement: Literal["NONE", "SUBPIX"] = "NONE",
) -> PoseMarkerEstimate:
    """Decode exactly one known marker and estimate its ordered pose from depth.

    Planarity/nominal size are sanity checks, not a sensor calibration. A single
    frame, or agreement of endpoints, cannot bound motion between observations.
    No source scope is promoted and no native VALID flag is returned.
    """

    if type(corner_refinement) is not str or corner_refinement not in {"NONE", "SUBPIX"}:
        raise ValueError("unsupported marker corner refinement")

    def unknown(reason: str, ids: tuple[int, ...] = ()) -> PoseMarkerEstimate:
        return PoseMarkerEstimate(
            "UNKNOWN",
            reason,
            observation.observation_id,
            observation.checksum_sha256,
            observation.captured_at,
            registration.digest(),
            ids,
        )

    try:
        current = RGBDObservation.model_validate(observation.model_dump())
    except Exception:
        return unknown("invalid_registered_rgbd")
    if not current.calibration_version or not current.episode_id:
        return unknown("registered_camera_context_missing")
    try:
        import cv2
        import numpy as np
        from PIL import Image

        params = cv2.aruco.DetectorParameters()
        params.errorCorrectionRate = 0.0  # do not repair unknown marker bits into the expected ID
        if corner_refinement == "SUBPIX":
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        detector = cv2.aruco.ArucoDetector(dictionary, params)
        rgb = np.asarray(
            Image.open(io.BytesIO(base64.b64decode(current.rgb_png_base64))).convert("RGB")
        )
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        corners, ids, rejected = detector.detectMarkers(gray)
        if ids is None and corner_refinement == "SUBPIX" and rejected:
            corners, ids = _decode_subpix_rejected_candidates(
                gray, rejected, dictionary
            )
    except (ImportError, AttributeError):
        return unknown("aruco_decoder_unavailable")
    if ids is None:
        return unknown("known_marker_not_observed")
    observed = tuple(int(item) for item in ids.reshape(-1))
    if len(observed) != 1 or observed[0] != registration.marker_id:
        return unknown("foreign_or_ambiguous_marker", observed)
    points = np.asarray(corners[0], dtype=float).reshape(4, 2)
    if not np.isfinite(points).all() or any(
        not (1 <= x < current.width - 2 and 1 <= y < current.height - 2) for x, y in points
    ):
        return unknown("marker_boundary_clipped", observed)
    side_px = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
    if float(side_px.min()) < 8:
        return unknown("marker_resolution_insufficient", observed)
    depths = np.asarray(current.depth_values()).reshape(current.height, current.width)
    transform = np.asarray(current.camera_to_world).reshape(4, 4)
    fx, fy, cx, cy = current.intrinsics
    world = []
    for x, y in (*points, points.mean(axis=0)):
        u, v = int(round(float(x))), int(round(float(y)))
        patch = depths[v - 1 : v + 2, u - 1 : u + 2]
        if patch.shape != (3, 3) or not np.isfinite(patch).all() or (patch <= 0).any():
            return unknown("marker_metric_depth_unavailable", observed)
        z = float(np.median(patch))
        camera = np.array([(x - cx) * z / fx, (y - cy) * z / fy, z, 1.0])
        world.append((transform @ camera)[:3])
    metric = np.array(world[:4])
    lengths = np.linalg.norm(np.roll(metric, -1, axis=0) - metric, axis=1)
    if any(abs(float(value) / registration.marker_size_m - 1) > 0.30 for value in lengths):
        return unknown("registered_marker_size_inconsistent", observed)
    center = metric.mean(axis=0)
    _, _, basis = np.linalg.svd(metric - center)
    if (
        abs(float((world[4] - center) @ basis[-1])) > 0.002
        or max(abs(float(point @ basis[-1])) for point in metric - center) > 0.002
    ):
        return unknown("marker_depth_not_planar", observed)
    x_axis = metric[1] - metric[0]
    x_axis /= np.linalg.norm(x_axis)
    y_hint = metric[0] - metric[3]  # bitmap row increases opposite marker +y
    z_axis = np.cross(x_axis, y_hint)
    if np.linalg.norm(z_axis) < 1e-8:
        return unknown("ordered_marker_axes_degenerate", observed)
    z_axis /= np.linalg.norm(z_axis)
    y_axis = np.cross(z_axis, x_axis)
    rotation = np.column_stack((x_axis, y_axis, z_axis))
    yaw = math.atan2(float(x_axis[1]), float(x_axis[0]))
    return PoseMarkerEstimate(
        "OBSERVED",
        "uncalibrated_single_frame_pose_estimate",
        current.observation_id,
        current.checksum_sha256,
        current.captured_at,
        registration.digest(),
        observed,
        tuple((float(x), float(y)) for x, y in points),
        (float(world[4][0]), float(world[4][1]), float(world[4][2])),
        tuple(float(value) for value in rotation.ravel()),
        yaw,
        tuple(float(value) for value in lengths),
        float(side_px.min()),
    )


def build_pose_marked_xml(base_xml: bytes) -> bytes:
    """Add portable visual-only ID7 cells to the exact unmodified v2 base asset.

    The new asset needs its own source binding; compiled physical equivalence
    does not make it a registered grasp v3 or a calibrated pose source.
    """
    if hashlib.sha256(base_xml).hexdigest() != BASE_ASSET_SHA256:
        raise ValueError("pose marker requires exact frozen base v2 asset")
    import cv2

    tree = ET.fromstring(base_xml)
    body = tree.find("./worldbody/body[@name='object']")
    if body is None:
        raise ValueError("registered object body missing")
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    bits = cv2.aruco.generateImageMarker(dictionary, 7, 6)

    def geom(
        name: str,
        position: tuple[float, float, float],
        size: tuple[float, float, float],
        white: bool,
    ) -> None:
        attributes = {
            "name": name,
            "type": "box",
            "pos": " ".join(f"{value:.10f}" for value in position),
            "size": " ".join(f"{value:.10f}" for value in size),
            "mass": "0",
            "density": "0",
            "contype": "0",
            "conaffinity": "0",
            "group": "2",
            "rgba": ("0.98 0.98 0.98 1" if white else "0.01 0.01 0.01 1"),
        }
        ET.SubElement(body, "geom", attributes)

    geom("pose_marker_quiet_v1", (0.0, 0.0, 0.03502), (0.035, 0.035, 0.00001), True)
    cell = MARKER_SIZE_M / 6
    for row in range(6):
        for column in range(6):
            geom(
                f"pose_marker_v1_r{row}c{column}",
                ((column - 2.5) * cell, (2.5 - row) * cell, 0.03504),
                (cell / 2, cell / 2, 0.00001),
                bool(bits[row, column]),
            )
    tree.insert(
        0, ET.Comment("DEVELOPMENTAL POSE MARKER V1: visual only; no grasp calibration acceptance")
    )
    ET.indent(tree, space="  ")
    return bytes(ET.tostring(tree, encoding="utf-8")) + b"\n"
