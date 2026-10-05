"""Conservative OpenCV evidence for the scoped fixed-camera upright colored block.

Connected color contours, registered metric depth and fresh capture times are the
only geometry inputs. Robot feedback can corroborate grasp/release; it never moves
the estimated object. Missing extent or calibration error bounds remain UNKNOWN.
This is a scoped estimator, not an arbitrary object detector or occlusion completion.
"""

from __future__ import annotations

import base64
import hashlib
import io
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from PIL import Image

from cloud_edge_robot_arm.contracts import RobotState
from cloud_edge_robot_arm.vision.observations import RGBDObservation

_CONDITIONS = (
    "target_visible",
    "target_reachable",
    "object_inside_target_region",
    "object_lifted",
    "object_stable",
    "placement_stable",
    "object_placed",
)
_MAX_SAMPLE_GAP_S = 0.2
_STABILITY_M = 0.012
_MAX_VISUAL_SPEED_M_S = 1.5
_MAX_STABLE_SPEED_M_S = 0.02
_MAX_STABLE_ANGULAR_SPEED_RAD_S = 0.5


def _rgb(observation: RGBDObservation) -> np.ndarray:
    with Image.open(io.BytesIO(base64.b64decode(observation.rgb_png_base64))) as image:
        return np.asarray(image.convert("RGB"))


class OpenCVTargetTracker:
    """Track unique colored supports without extrapolating hidden object surfaces.

    Grounding supplies original target/region pixels, support height and a positive
    ``depth_error_bound_m`` supported by the sensor/calibration. An omitted bound
    permits visibility estimates but cannot prove metric effects or full placement.
    Pixel footprint uncertainty is half a pixel in this fixed registered-camera
    scope. The initial fully observed upright top defines its horizontal extent;
    current top dimensions must agree within 15% (sampling/perspective tolerance).
    This module has no verified continuous-motion or symmetry-resolving sensor
    evidence. Stability/placement completion facts therefore remain UNKNOWN;
    endpoint consistency is retained only as a diagnostic, never a certificate.
    """

    def __init__(self, observation: RGBDObservation, grounding: dict[str, Any]) -> None:
        self.target_pixel = tuple(grounding["original_pixel_target"])
        self.destination_pixel = tuple(grounding["original_pixel_destination"])
        self.support_z = float(grounding["top_grasp_support_height_m"])
        if not math.isfinite(self.support_z):
            raise ValueError("support height must be finite")
        bound = grounding.get("depth_error_bound_m")
        self.depth_error_bound_m = (
            float(bound)
            if isinstance(bound, (int, float))
            and not isinstance(bound, bool)
            and math.isfinite(bound)
            and bound > 0
            else None
        )
        self._reference = observation
        reason = self._binding_reason(observation)
        if reason:
            raise ValueError(f"initial acquisition unavailable: {reason}")
        rgb = _rgb(observation)
        self.target_color = self._color(rgb, self.target_pixel)
        self.destination_color = self._color(rgb, self.destination_pixel)
        self.initial, reason = self._geometry(observation, self.target_color, target=True)
        self.destination, region_reason = self._geometry(
            observation, self.destination_color, target=False
        )
        if self.initial is None or self.destination is None:
            raise ValueError(
                f"initial RGB-D identity/extent unavailable: {reason or region_reason}"
            )
        for pixel, geometry in (
            (self.target_pixel, self.initial),
            (self.destination_pixel, self.destination),
        ):
            if not geometry["mask"][pixel[1], pixel[0]]:
                raise ValueError("grounded pixel does not belong to unique support")
        self._last_geometry = self.initial
        self._last_observation = observation
        self._seen = {observation.observation_id}
        self._lift_samples: list[dict[str, Any]] = []
        self._placement_samples: list[dict[str, Any]] = []
        self.algorithm_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.calibration_sha256 = hashlib.sha256(
            repr(
                (
                    observation.intrinsics,
                    observation.camera_to_world,
                    observation.calibration_version,
                    self.depth_error_bound_m,
                    self.support_z,
                )
            ).encode()
        ).hexdigest()

    @staticmethod
    def _color(rgb: np.ndarray, pixel: tuple[int, ...]) -> np.ndarray:
        if len(pixel) != 2 or any(type(value) is not int for value in pixel):
            raise ValueError("grounding pixel must contain two integers")
        x, y = pixel
        if not 0 <= x < rgb.shape[1] or not 0 <= y < rgb.shape[0]:
            raise ValueError("grounding pixel outside registered camera")
        color = rgb[y, x].astype(float)
        if np.ptp(color) < 35:
            raise ValueError("grounding pixel lacks distinguishable color")
        return cast(np.ndarray, color / max(float(color.sum()), 1.0))

    @staticmethod
    def _points(
        observation: RGBDObservation, xs: np.ndarray, ys: np.ndarray, depths: np.ndarray
    ) -> np.ndarray:
        fx, fy, cx, cy = observation.intrinsics
        camera = np.column_stack(((xs - cx) * depths / fx, (ys - cy) * depths / fy, depths))
        transform = np.asarray(observation.camera_to_world).reshape(4, 4)
        return cast(np.ndarray, camera @ transform[:3, :3].T + transform[:3, 3])

    def _top_support(
        self,
        points: np.ndarray,
        selected: np.ndarray,
        ys: np.ndarray,
        xs: np.ndarray,
    ) -> tuple[np.ndarray, list[float] | None, str | None]:
        """Separate a measured dominant horizontal top from boundary-only sides.

        Otsu supplies a data-derived candidate split, not a metric tolerance or
        calibration. Only source-supplied depth intervals can validate its plane.
        The lower mode must occur exclusively on the complete silhouette boundary;
        interior anomalies cannot be relabelled as cuboid sides.
        """
        heights = points[:, 2]
        top = np.ones(len(heights), dtype=bool)
        bound = self.depth_error_bound_m
        full_plane_possible = bound is not None and float(np.ptp(heights)) <= 2 * bound
        if not full_plane_possible and np.ptp(heights) > 0:
            normalized = np.rint((heights - heights.min()) / np.ptp(heights) * 255).astype(np.uint8)
            split, _ = cv2.threshold(normalized, 0, 255, cv2.THRESH_OTSU)
            candidate = normalized > split
            boundary = cv2.erode(selected.astype(np.uint8), np.ones((3, 3), np.uint8)) == 0
            if (
                int(candidate.sum()) >= 8
                and np.all(boundary[ys[~candidate], xs[~candidate]])
                and np.all(heights[~candidate] >= self.support_z - (bound or 0.0))
            ):
                top = candidate
        if bound is None:
            return top, None, None
        interval = [float((heights[top] - bound).max()), float((heights[top] + bound).min())]
        if interval[0] > interval[1]:
            return top, None, "top_plane_depth_intervals_do_not_overlap"
        if np.any(heights[~top] - bound > interval[1]):
            return top, None, "side_depth_not_below_observed_top"
        return top, interval, None

    def _geometry(
        self,
        observation: RGBDObservation,
        color: np.ndarray,
        *,
        target: bool,
        occlusion_geometry: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        rgb = _rgb(observation).astype(float)
        chroma = rgb / np.maximum(rgb.sum(axis=2, keepdims=True), 1.0)
        mask = (
            (np.linalg.norm(chroma - color, axis=2) < 0.14) & (np.ptp(rgb, axis=2) > 30)
        ).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        candidates = [index for index in range(1, count) if stats[index, cv2.CC_STAT_AREA] >= 8]
        if len(candidates) != 1:
            return None, "target_missing" if not candidates else "color_identity_ambiguous"
        selected = labels == candidates[0]
        topology = selected.copy()
        inside_pixel_rectangle = None
        if not target and occlusion_geometry is not None:
            # Only the currently complete, independently depth-verified block can
            # account for missing region color. Arbitrary holes remain unsupported.
            reference_region = self.destination["mask"] if self.destination else topology
            topology |= occlusion_geometry["mask"] & reference_region
        if not target:
            ty, tx = np.nonzero(topology)
            left, top, right, bottom = (
                int(tx.min()) + 1,
                int(ty.min()) + 1,
                int(tx.max()) - 1,
                int(ty.max()) - 1,
            )
            if (
                left >= right
                or top >= bottom
                or not topology[top : bottom + 1, left : right + 1].all()
            ):
                return None, "region_topology_not_supported_axis_aligned_rectangle"
            inside_pixel_rectangle = [left, top, right, bottom]
        ys, xs = np.nonzero(selected)
        if (
            xs.min() == 0
            or ys.min() == 0
            or xs.max() == observation.width - 1
            or ys.max() == observation.height - 1
        ):
            return None, "extent_truncated_at_image_boundary"
        contours, _ = cv2.findContours(
            selected.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contour = contours[0]
        hull_area = cv2.contourArea(cv2.convexHull(contour))
        area = cv2.contourArea(contour)
        if target and (hull_area <= 0 or area / hull_area < 0.95):
            return None, "target_contour_incomplete_or_occluded"
        if target:
            filled = np.zeros_like(mask)
            cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
            if np.any((filled > 0) & ~selected):
                return None, "target_interior_occluded"
        depth = np.asarray(observation.depth_values()).reshape(mask.shape)
        valid = np.frombuffer(observation.valid_mask_bytes(), dtype=np.uint8).reshape(mask.shape)
        if not np.all((depth[ys, xs] > 0) & np.isfinite(depth[ys, xs]) & (valid[ys, xs] > 0)):
            return None, "target_depth_incomplete"
        points = self._points(observation, xs, ys, depth[ys, xs])
        top_selector = np.ones(len(points), dtype=bool)
        plane_interval = None
        if target:
            top_selector, plane_interval, reason = self._top_support(points, selected, ys, xs)
            if reason:
                return None, reason
            # RGB antialias pixels can sample the table rather than the block.
            # Retain them in the conservative measured silhouette; compare the
            # adjacent depth against the observed top, not those background samples.
            # Nearer/coplanar or invalid neighbors still cannot prove a complete top.
            ring = cv2.dilate(selected.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            ring &= ~selected
            bound = self.depth_error_bound_m or 0.0
            top_depth_max = float(depth[ys[top_selector], xs[top_selector]].max())
            if not np.all(
                (valid[ring] > 0)
                & np.isfinite(depth[ring])
                & (depth[ring] - bound > top_depth_max + bound)
            ):
                return None, "target_outer_boundary_depth_unresolved"
        elif self.depth_error_bound_m is not None:
            bound = self.depth_error_bound_m
            plane_interval = [
                float((points[:, 2] - bound).max()),
                float((points[:, 2] + bound).min()),
            ]
            if plane_interval[0] > plane_interval[1]:
                return None, "region_plane_depth_unresolved"
        center = np.median(points[top_selector], axis=0)
        bound = self.depth_error_bound_m or 0.0
        corners = [
            self._points(observation, xs + dx, ys + dy, depth[ys, xs] + dz)
            for dx in (-0.5, 0.5)
            for dy in (-0.5, 0.5)
            for dz in (-bound, bound)
        ]
        outer = np.concatenate(corners)
        if np.any(depth[ys, xs] <= bound):
            return None, "depth_error_exceeds_distance"
        lower, upper = outer.min(axis=0), outer.max(axis=0)
        uncertainty = np.max(np.abs(np.stack(corners) - points), axis=(0, 1))
        inner_min = points.min(axis=0) + uncertainty
        inner_max = points.max(axis=0) - uncertainty
        if not target:
            assert inside_pixel_rectangle is not None
            left, top, right, bottom = inside_pixel_rectangle
            corner_x = np.array([left, right, right, left])
            corner_y = np.array([top, top, bottom, bottom])
            if not np.all(selected[corner_y, corner_x]):
                return None, "region_inside_corner_depth_not_observed"
            if plane_interval is not None:
                # A horizontal plane validated by every observed depth interval
                # intersects these inside rays at one common height. Intersect the
                # possible rectangles over its height interval; never fill color.
                camera_z = observation.camera_to_world[11]
                inner_rectangles = [
                    self._points(
                        observation,
                        corner_x + np.array([0.5, -0.5, -0.5, 0.5]),
                        corner_y + np.array([0.5, 0.5, -0.5, -0.5]),
                        np.full(4, camera_z - height),
                    )
                    for height in plane_interval
                ]
                inner_min = np.maximum.reduce(
                    [rectangle.min(axis=0) for rectangle in inner_rectangles]
                )
                inner_max = np.minimum.reduce(
                    [rectangle.max(axis=0) for rectangle in inner_rectangles]
                )
            else:
                observed_corners = self._points(
                    observation, corner_x, corner_y, depth[corner_y, corner_x]
                )
                inner_min = observed_corners.min(axis=0) + uncertainty
                inner_max = observed_corners.max(axis=0) - uncertainty
        nearest = int(np.argmin(np.linalg.norm(points[top_selector] - center, axis=1)))
        top_indices = np.flatnonzero(top_selector)
        nearest = int(top_indices[nearest])
        _, rectangle_size, angle = cv2.minAreaRect(points[top_selector, :2].astype(np.float32))
        diagonal = float(np.linalg.norm(rectangle_size))
        orientation_error = math.atan2(
            2 * float(np.linalg.norm(uncertainty[:2])), max(diagonal, 1e-12)
        )
        return {
            "pixel": [int(xs[nearest]), int(ys[nearest])],
            "center": center.tolist(),
            "min": lower.tolist(),
            "max": upper.tolist(),
            "inner_min": inner_min.tolist(),
            "inner_max": inner_max.tolist(),
            "uncertainty_m": uncertainty.tolist(),
            "orientation_rad": math.radians(angle) % (math.pi / 2),
            "orientation_error_rad": orientation_error,
            "visible_pixels": int(len(xs)),
            "silhouette_complete": True,
            "extent_complete": plane_interval is not None,
            "top_pixels": int(top_selector.sum()),
            "side_pixels": int((~top_selector).sum()),
            "observed_body_min": points.min(axis=0).tolist(),
            "observed_body_max": points.max(axis=0).tolist(),
            "observed_top_min": points[top_selector].min(axis=0).tolist(),
            "observed_top_max": points[top_selector].max(axis=0).tolist(),
            "top_plane_height_interval_m": plane_interval,
            "top_plane_status": "CALIBRATED_DEPTH_INTERVAL"
            if plane_interval is not None
            else "UNVALIDATED_DEPTH_ERROR_BOUND",
            "inside_pixel_rectangle": inside_pixel_rectangle,
            "depth_error_bound_m": self.depth_error_bound_m,
            "pixel_footprint_half_width_px": 0.5,
            "mask": selected,
        }, None

    @staticmethod
    def _public(geometry: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in geometry.items() if key != "mask"}

    def _envelope(
        self,
        observation: RGBDObservation,
        geometry: dict[str, Any] | None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "source": "rgbd_estimate",
            "target_id": "object",
            "observation_id": observation.observation_id,
            "frame_id": observation.frame_id,
            "captured_at": observation.captured_at.isoformat(),
            "sim_time_s": observation.sim_time_s,
            "episode_id": observation.episode_id,
            "calibration_version": observation.calibration_version,
            "calibration_sha256": self.calibration_sha256,
            "algorithm_sha256": self.algorithm_sha256,
            "observation_sha256": observation.checksum_sha256,
            "identity_confirmed": geometry is not None,
            "pixel": geometry["pixel"] if geometry else None,
            "extent_complete": geometry is not None and geometry["extent_complete"],
            "reasons": [reason] if reason else [],
        }

    def _unknown(self, observation: RGBDObservation, reason: str) -> dict[str, Any]:
        self._lift_samples.clear()
        self._placement_samples.clear()
        envelope = self._envelope(observation, None, reason)
        return {name: {**envelope, "value": None, "measured_values": {}} for name in _CONDITIONS}

    def _binding_reason(self, observation: RGBDObservation) -> str | None:
        reference = self._reference
        for field in (
            "episode_id",
            "scene_id",
            "calibration_version",
            "source",
            "width",
            "height",
            "intrinsics",
            "camera_to_world",
        ):
            if getattr(observation, field) != getattr(reference, field):
                return f"observation_{field}_changed"
        if not observation.calibration_version:
            return "calibration_version_missing"
        if not observation.episode_id or not observation.episode_id.strip():
            return "episode_binding_missing"
        rotation = np.asarray(observation.camera_to_world).reshape(4, 4)[:3, :3]
        aligned_axis = np.isclose(np.abs(rotation[:2, :2]), 0.0, atol=1e-9) | np.isclose(
            np.abs(rotation[:2, :2]), 1.0, atol=1e-9
        )
        if not (
            np.allclose(rotation[:, 2], [0.0, 0.0, -1.0], atol=1e-9, rtol=0.0)
            and aligned_axis.all()
        ):
            return "camera_orientation_not_supported"
        age = (datetime.now(UTC) - observation.captured_at).total_seconds()
        if age < -0.05 or age > 5.0:
            return "capture_time_not_fresh"
        return None

    @staticmethod
    def _sample(
        observation: RGBDObservation, target: dict[str, Any], lift: float
    ) -> dict[str, Any]:
        return {
            "observation_id": observation.observation_id,
            "captured_at": observation.captured_at.isoformat(),
            "sim_time_s": observation.sim_time_s,
            "center": target["center"],
            "uncertainty_m": target["uncertainty_m"],
            "orientation_rad": target["orientation_rad"],
            "orientation_error_rad": target["orientation_error_rad"],
            "minimum_visual_lift_m": lift,
        }

    def _append(self, samples: list[dict[str, Any]], sample: dict[str, Any]) -> None:
        if samples:
            previous = samples[-1]
            elapsed = (
                sample["sim_time_s"] - previous["sim_time_s"]
                if self._reference.source in {"mujoco_camera", "isaac_camera"}
                else (
                    datetime.fromisoformat(sample["captured_at"])
                    - datetime.fromisoformat(previous["captured_at"])
                ).total_seconds()
            )
            displacement = float(
                np.linalg.norm(np.asarray(sample["center"]) - np.asarray(previous["center"]))
            )
            uncertainty = float(np.linalg.norm(sample["uncertainty_m"])) + float(
                np.linalg.norm(previous["uncertainty_m"])
            )
            speed_upper = (displacement + uncertainty) / elapsed
            delta_angle = abs(sample["orientation_rad"] - previous["orientation_rad"])
            delta_angle = min(delta_angle, math.pi / 2 - delta_angle)
            angular_upper = (
                delta_angle + sample["orientation_error_rad"] + previous["orientation_error_rad"]
            ) / elapsed
            sample["net_endpoint_displacement_rate_upper_m_s"] = speed_upper
            sample["modulo_quarter_turn_endpoint_rate_upper_rad_s"] = angular_upper
            first_center = np.asarray(samples[0]["center"])
            if (
                speed_upper > _MAX_STABLE_SPEED_M_S
                or angular_upper > _MAX_STABLE_ANGULAR_SPEED_RAD_S
                or np.linalg.norm(np.asarray(sample["center"]) - first_center) > _STABILITY_M
            ):
                samples.clear()
        samples.append(sample)
        # Bounded history keeps the active one-second stability window plus margin.
        if len(samples) > 256:
            del samples[:-256]

    def _window(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        duration = samples[-1]["sim_time_s"] - samples[0]["sim_time_s"] if samples else 0.0
        capture_duration = (
            (
                datetime.fromisoformat(samples[-1]["captured_at"])
                - datetime.fromisoformat(samples[0]["captured_at"])
            ).total_seconds()
            if samples
            else 0.0
        )
        centers = np.asarray([sample["center"] for sample in samples])
        return {
            "samples": [dict(sample) for sample in samples],
            "observed_sim_duration_s": duration,
            "observed_capture_duration_s": capture_duration,
            "evidence_duration_s": duration
            if self._reference.source in {"mujoco_camera", "isaac_camera"}
            else capture_duration,
            "duration_source": "physics_sensor_time"
            if self._reference.source in {"mujoco_camera", "isaac_camera"}
            else "capture_time",
            "max_displacement_m": float(np.linalg.norm(centers - centers[0], axis=1).max())
            if samples
            else None,
            "minimum_visual_lift_m": min(sample["minimum_visual_lift_m"] for sample in samples)
            if samples
            else None,
            "maximum_sample_gap_s": _MAX_SAMPLE_GAP_S,
            "stability_tolerance_m": _STABILITY_M,
            "maximum_stable_linear_speed_m_s": _MAX_STABLE_SPEED_M_S,
            "maximum_stable_angular_speed_rad_s": _MAX_STABLE_ANGULAR_SPEED_RAD_S,
        }

    @staticmethod
    def _physical_stability_unknown(
        envelope: dict[str, Any],
        window: dict[str, Any],
        required_duration_s: float,
        **measurements: Any,
    ) -> dict[str, Any]:
        """Do not convert endpoint consistency into unsupported interval proof.

        No input gate enables this fact. A future separately verified sensor
        integration must establish interval-wide object-speed envelopes, source
        identity/freshness/coverage and symmetry-resolved orientation. Grounding
        booleans, synthetic error bounds and robot TCP endpoints cannot do so.
        """
        return {
            **envelope,
            "value": None,
            "measured_values": {
                **window,
                **measurements,
                "required_duration_s": required_duration_s,
                "endpoint_window_consistent": window["evidence_duration_s"]
                >= required_duration_s - 1e-9,
                "physical_stability_support": {
                    "status": "UNAVAILABLE",
                    "accepted_support_sources": [],
                    "required_evidence": [
                        "source_attested_same_episode_object_identity_and_capture_coverage",
                        "validated_interval_wide_object_linear_speed_upper_bound_le_0.02_m_s",
                        "symmetry_resolved_interval_wide_angular_speed_upper_bound_le_0.5_rad_s",
                    ],
                },
            },
            "reasons": ["inter_frame_motion_not_bounded", "quarter_turn_symmetry_unresolved"],
        }

    def facts(
        self, observation: RGBDObservation, robot_state: RobotState | None = None
    ) -> dict[str, Any]:
        reason = self._binding_reason(observation)
        if reason:
            return self._unknown(observation, reason)
        previous = self._last_observation
        repeat = observation.observation_id == previous.observation_id
        initial_repeat = repeat and observation is self._reference
        if repeat and observation.checksum_sha256 != previous.checksum_sha256:
            return self._unknown(observation, "reused_frame_with_changed_payload")
        dt = observation.sim_time_s - previous.sim_time_s
        capture_dt = (observation.captured_at - previous.captured_at).total_seconds()
        elapsed = dt if observation.source in {"mujoco_camera", "isaac_camera"} else capture_dt
        if not repeat and (observation.observation_id in self._seen or dt <= 0 or capture_dt <= 0):
            return self._unknown(observation, "capture_not_new_and_monotonic")
        if not repeat:
            self._seen.add(observation.observation_id)
            self._last_observation = observation
            if elapsed > _MAX_SAMPLE_GAP_S + 1e-9:
                self._lift_samples.clear()
                self._placement_samples.clear()
        target, reason = self._geometry(observation, self.target_color, target=True)
        if target is None:
            return self._unknown(observation, reason or "target_extent_missing")
        assert self.initial is not None and self.destination is not None
        widths = np.asarray(target["max"])[:2] - np.asarray(target["min"])[:2]
        initial_widths = np.asarray(self.initial["max"])[:2] - np.asarray(self.initial["min"])[:2]
        if np.any(np.abs(widths / initial_widths - 1.0) > 0.15):
            return self._unknown(observation, "target_extent_changed_or_partially_occluded")
        # Sampling tolerance cannot shrink the full body's conservative envelope.
        for axis in (0, 1):
            deficit = max(0.0, initial_widths[axis] - widths[axis])
            target["min"][axis] -= deficit
            target["max"][axis] += deficit
        displacement = np.linalg.norm(
            np.asarray(target["center"]) - np.asarray(self._last_geometry["center"])
        )
        if not repeat and displacement > _MAX_VISUAL_SPEED_M_S * elapsed + 0.012:
            return self._unknown(observation, "target_identity_temporal_jump")
        self._last_geometry = target
        envelope = self._envelope(observation, target)
        public = self._public(target)
        # The scoped rigid upright body extends down by its initially observed
        # top-to-support height. Full xy bounds retain top silhouette uncertainty.
        body_height = max(0.0, self.initial["center"][2] - self.support_z)
        public["full_extent_min"] = list(public["min"])
        public["full_extent_min"][2] = min(
            public["min"][2],
            public["center"][2]
            - body_height
            - self.initial["uncertainty_m"][2]
            - target["uncertainty_m"][2],
        )
        public["full_extent_max"] = list(public["max"])
        public["extent_source"] = "unique_complete_rgbd_top_and_initial_upright_support_height"
        public["conservative_full_extent_min"] = (
            public["full_extent_min"] if target["extent_complete"] else None
        )
        public["conservative_full_extent_max"] = (
            public["full_extent_max"] if target["extent_complete"] else None
        )
        result = {
            name: {
                **envelope,
                "value": None,
                "measured_values": {},
                "reasons": ["effect_evidence_incomplete"],
            }
            for name in _CONDITIONS
        }
        result["target_visible"] = {**envelope, "value": True, "measured_values": public}
        stationary = all(
            target["min"][axis] >= self.initial["min"][axis] - 0.018
            and target["max"][axis] <= self.initial["max"][axis] + 0.018
            for axis in (0, 1)
        )
        result["target_reachable"] = {
            **envelope,
            "value": stationary,
            "measured_values": {"stationary_support": stationary},
        }
        if self.depth_error_bound_m is None:
            result["target_reachable"]["value"] = None
            result["target_reachable"]["reasons"] = ["calibrated_depth_error_bound_missing"]
            for name in _CONDITIONS[2:]:
                result[name]["reasons"] = ["calibrated_depth_error_bound_missing"]
            return result
        error = target["uncertainty_m"][2] + self.initial["uncertainty_m"][2]
        lift = float(target["center"][2] - self.initial["center"][2] - error)
        lift_upper = float(target["center"][2] - self.initial["center"][2] + error)
        lifted = True if lift >= 0.05 else False if lift_upper < 0.05 else None
        result["object_lifted"] = {
            **envelope,
            "value": lifted,
            "measured_values": {
                "minimum_visual_lift_m": lift,
                "maximum_visual_lift_m": lift_upper,
                "required_lift_m": 0.05,
                "height_difference_error_bound_m": error,
                "target": public,
            },
            "reasons": ["lift_threshold_overlaps_measurement_interval"] if lifted is None else [],
        }
        holding = bool(
            robot_state
            and robot_state.connected
            and not robot_state.gripper_open
            and robot_state.holding_object_id == "object"
            and not robot_state.estop_engaged
            and not robot_state.collision_detected
        )
        released = bool(
            robot_state
            and robot_state.connected
            and robot_state.gripper_open
            and robot_state.holding_object_id is None
            and not robot_state.estop_engaged
            and not robot_state.collision_detected
        )
        if lifted and holding:
            if not repeat:
                self._append(self._lift_samples, self._sample(observation, target, lift))
            window = self._window(self._lift_samples)
            result["object_stable"] = self._physical_stability_unknown(
                envelope, window, 0.5, holding_feedback_at_sampled_endpoints=True
            )
        else:
            self._lift_samples.clear()
        destination, reason = self._geometry(
            observation, self.destination_color, target=False, occlusion_geometry=target
        )
        inside: bool | None = None
        if destination is not None:
            # Current visible region must retain every previously established boundary.
            region_error = np.asarray(self.destination["uncertainty_m"])[:2] * 2 + 0.003
            boundary_complete = np.all(
                np.abs(np.asarray(destination["min"])[:2] - np.asarray(self.destination["min"])[:2])
                <= region_error
            ) and np.all(
                np.abs(np.asarray(destination["max"])[:2] - np.asarray(self.destination["max"])[:2])
                <= region_error
            )
            if boundary_complete:
                contained = all(
                    target["min"][axis] >= destination["inner_min"][axis]
                    and target["max"][axis] <= destination["inner_max"][axis]
                    for axis in (0, 1)
                )
                height_delta = abs(target["center"][2] - self.initial["center"][2])
                on_support = height_delta + error <= 0.012
                definitely_outside = any(
                    target["inner_min"][axis] < destination["min"][axis]
                    or target["inner_max"][axis] > destination["max"][axis]
                    for axis in (0, 1)
                )
                definitely_off_support = height_delta - error > 0.012
                inside = (
                    True
                    if contained and on_support
                    else False
                    if definitely_outside or definitely_off_support
                    else None
                )
                result["object_inside_target_region"] = {
                    **envelope,
                    "value": inside,
                    "measured_values": {
                        "whole_object_inside": inside,
                        "on_support": on_support,
                        "extent_complete": True,
                        "target": public,
                        "destination": self._public(destination),
                    },
                    "reasons": ["placement_threshold_overlaps_measurement_interval"]
                    if inside is None
                    else [],
                }
            else:
                result["object_inside_target_region"]["reasons"] = ["region_boundary_incomplete"]
        else:
            result["object_inside_target_region"]["reasons"] = [reason or "region_missing"]
        if inside and released:
            if not repeat and not initial_repeat:
                self._append(self._placement_samples, self._sample(observation, target, lift))
            window = self._window(self._placement_samples)
            for name in ("placement_stable", "object_placed"):
                result[name] = self._physical_stability_unknown(
                    envelope,
                    window,
                    1.0,
                    release_observed_at_sampled_endpoints=True,
                    whole_object_inside_at_sampled_endpoints=True,
                )
        else:
            self._placement_samples.clear()
        return result
