"""Estimate ID8 print pose on the current common red-top/ink plane.

Initialize once with the registered asset and the prebuilt red-ink-grid.cpp library.
This estimator supplies measurements. Downstream bounds and contact permissions are
separate and require independent qualification.
"""

from __future__ import annotations

import ctypes
import hashlib
import itertools
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

_ASSET_SHA = "35f50ef8d18a13828541226552678b8ac3fcff4d597794957332f65eb623e1b6"
# Offscreen four-sample locations, expressed in top-down image coordinates.
_SAMPLES = np.array([[0.375, 0.875], [0.875, 0.625], [0.125, 0.375], [0.625, 0.125]]) - 0.5
_GRID = np.array(
    [
        (np.deg2rad(a), dx / 1000, dy / 1000)
        for a, dx, dy in itertools.product(
            np.arange(-3, 3.001, 0.2), np.arange(-1.5, 1.501, 0.5), np.arange(-1.5, 1.501, 0.5)
        )
    ]
)


class RedInkGeometry:
    def __init__(self, asset_path: Path, library_path: Path, library_sha256: str):
        if hashlib.sha256(asset_path.read_bytes()).hexdigest() != _ASSET_SHA:
            raise ValueError("unsupported ID8 assembly")
        if hashlib.sha256(library_path.read_bytes()).hexdigest() != library_sha256:
            raise ValueError("unregistered print kernel")
        tree = ET.parse(asset_path)
        self.bits = np.array(
            [
                float(tree.find(f'.//geom[@name="g1_dual_id8_r{r}c{c}"]').attrib["rgba"].split()[0])
                > 0.5
                for r in range(6)
                for c in range(6)
            ],
            dtype=np.int32,
        )
        self.library = ctypes.CDLL(str(library_path.resolve()))
        doubles = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
        ints = np.ctypeslib.ndpointer(dtype=np.int32, flags="C_CONTIGUOUS")
        self.library.grid.argtypes = [
            ctypes.c_int,
            doubles,
            doubles,
            ints,
            ctypes.c_int,
            doubles,
            ctypes.c_int,
            doubles,
            doubles,
        ]
        self.library.grid.restype = None

    def refine(self, frame, raw_pose: dict, rgb: np.ndarray, depth: np.ndarray) -> dict | None:
        """Fit the current registered ID8 and red plane from decoded RGB and axial depth."""
        if not raw_pose or (
            raw_pose.get("method") != "id8_and_red_top"
            or raw_pose.get("ids") != [8]
            or raw_pose.get("frame_id") != frame.frame_id
            or raw_pose.get("checksum_sha256") != frame.checksum_sha256
            or frame.calibration_version != "f33940579c533afe"
            or tuple(frame.intrinsics) != (257.34083046114705, 257.34083046114705, 159.5, 119.5)
            or tuple(frame.camera_to_world)
            != (1.0, 0.0, 0.0, 0.35, 0.0, -1.0, 0.0, 0.0, 0.0, 0.0, -1.0, 1.4, 0.0, 0.0, 0.0, 1.0)
            or (frame.width, frame.height) != (320, 240)
            or rgb.shape != (frame.height, frame.width, 3)
            or depth.shape != (frame.height, frame.width)
        ):
            return None
        lever = np.asarray(raw_pose["anchor_object_m"])
        if not np.array_equal(lever, [0.13, 0.0, 0.03505]):
            return None
        rotation = np.asarray(raw_pose["rotation_object_to_world"])
        anchor = np.asarray(raw_pose["anchor_world_m"])
        center = np.asarray(raw_pose["center_world_m"])
        normal = rotation[:, 2]
        transform = np.asarray(frame.camera_to_world).reshape(4, 4)
        eye, axes = transform[:3, 3], transform[:3, :3]
        fx, fy, cx, cy = frame.intrinsics

        def region(world):
            xyz = (world - eye) @ axes
            u, v = np.rint([cx + fx * xyz[0] / xyz[2], cy + fy * xyz[1] / xyz[2]]).astype(int)
            ys, xs = np.mgrid[
                max(0, v - 17) : min(frame.height, v + 18),
                max(0, u - 17) : min(frame.width, u + 18),
            ]
            return np.stack((xs, ys), -1).reshape(-1, 2)

        def project(pixels):
            xy = (pixels - [cx, cy]) / [fx, fy]
            rays = np.concatenate((xy, np.ones((*pixels.shape[:-1], 1))), axis=-1) @ axes.T
            axial = ((anchor - eye) @ normal) / (rays @ normal)
            local = (eye + axial[..., None] * rays - anchor) @ rotation
            return local[..., :2], axial

        uv = region(anchor)
        xy, expected = project(uv)
        x, y = uv.T
        color = rgb[y, x].astype(float)
        printed = (
            (np.abs(xy).max(axis=1) < 0.043)
            & (np.abs(depth[y, x] - expected) < 0.004)
            & (np.ptp(color, axis=1) < 40)
        )
        if printed.sum() < 110:
            return None
        levels = color[printed].mean(axis=1)
        black, white = np.percentile(levels, [12, 85])
        if white - black < 60:
            return None
        intensity = np.ascontiguousarray(np.clip((levels - black) / (white - black), 0, 1))
        sample_xy, _ = project(uv[printed, None, :] + _SAMPLES[None, :, :])
        face_uv = region(center + normal * 0.035)
        face_xy, face_depth = project(face_uv)
        x, y = face_uv.T
        red, green, blue = rgb[y, x].astype(float).T
        visible = (
            (red > 1.25 * green + 7)
            & (red > 1.25 * blue + 7)
            & (np.abs(depth[y, x] - face_depth) < 0.004)
            & (np.abs(face_xy + [0.13, 0]).max(axis=1) < 0.043)
        )
        face = np.ascontiguousarray(face_xy[visible])
        if len(face) < 12 or np.ptp(face, axis=0).max() < 0.053:
            return None
        scores = np.empty((len(_GRID), 3))
        self.library.grid(
            len(intensity),
            np.ascontiguousarray(sample_xy),
            intensity,
            self.bits,
            len(face),
            face,
            len(_GRID),
            _GRID,
            scores,
        )
        footprint = (
            0.5 * np.hypot(1 / fx, 1 / fy) * np.max(face_depth) / abs(normal @ axes[:, 2]) + 0.00005
        )
        accepted = (scores[:, 1] <= footprint) & (scores[:, 0] <= 0.16)
        if not accepted.any():
            return None
        best = np.min(scores[accepted, 0])
        near = _GRID[accepted & (scores[:, 0] <= best + 0.001)]
        if np.any(abs(near[:, 0]) > np.deg2rad(2.99)) or np.any(abs(near[:, 1:]) > 0.00149):
            return None
        # A one-degree full yaw span displaces the 130 mm lever end by 2.27 mm.
        # This is an ambiguity veto, not an accuracy interval.
        if np.ptp(near[:, 0]) > np.deg2rad(1.0) + 1e-12:
            return None
        distance = (near - np.median(near, axis=0)) / [np.deg2rad(0.2), 0.0005, 0.0005]
        selected = int(np.argmin(np.linalg.norm(distance, axis=1)))
        centers = []
        for index, (theta, dx, dy) in enumerate(near):
            cos, sin = np.cos(theta), np.sin(theta)
            adjusted = rotation @ np.array([[cos, -sin, 0], [sin, cos, 0], [0, 0, 1]])
            origin = anchor + rotation[:, :2] @ [dx, dy]
            centers.append(origin - adjusted @ lever)
            if index == selected:
                estimated_rotation, estimated_anchor = adjusted, origin
        return dict(
            center_world_m=centers[selected].tolist(),
            rotation_object_to_world=estimated_rotation.tolist(),
            anchor_world_m=estimated_anchor.tolist(),
            fit_evidence=dict(
                method="id8_print_grid_and_visible_red_top",
                frame_id=frame.frame_id,
                checksum_sha256=frame.checksum_sha256,
                print_pixels=len(intensity),
                red_pixels=len(face),
                best_mean_absolute_residual=float(best),
                near_optimal_count=len(near),
                near_optimal_yaw_span_deg=float(np.rad2deg(np.ptp(near[:, 0]))),
                near_optimal_center_span_m=np.ptp(centers, axis=0).tolist(),
            ),
        )
