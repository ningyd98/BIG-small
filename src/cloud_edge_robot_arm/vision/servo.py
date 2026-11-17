"""Current-frame PBVS measurements for the explicit MuJoCo development path.

Camera motion is supported using each paired frame's full extrinsics. This does
not relax the fixed-camera tracker or grant physical/native acceptance.
"""

from __future__ import annotations

import base64
import json
import math
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np

from cloud_edge_robot_arm.contracts import Pose
from cloud_edge_robot_arm.vision.marker_families import marker_family
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.pose_markers import PoseMarkerRegistration, detect_pose_marker
from cloud_edge_robot_arm.vision.servo_region import measure_servo_region
from cloud_edge_robot_arm.vision.tracking import OpenCVTargetTracker

CameraView = tuple[tuple[float, float, float], tuple[float, float, float]]


def save_servo_frame(observation: RGBDObservation, directory: Path) -> None:
    """Retain original paired bytes and full calibration without a derived PNG depth map."""
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "rgb.png").write_bytes(base64.b64decode(observation.rgb_png_base64))
    (directory / "depth.f32").write_bytes(base64.b64decode(observation.depth_float32_base64))
    (directory / "valid_mask.u8").write_bytes(observation.valid_mask_bytes())
    with (directory / "observation.json").open("x", encoding="utf-8") as stream:
        json.dump(
            observation.evidence() | {"model_image_count": 0}, stream, indent=2, allow_nan=False
        )
        stream.write("\n")


class OpenCVServoFeedback:
    """Measure a bounded target without extrapolating hidden geometry.

    The skill's initial endpoint is immutable. LIFT/RETREAT endpoints and tool
    offsets are never recomputed from a moving TCP or a lifted object.
    """

    def __init__(
        self,
        reference: RGBDObservation,
        tracker: OpenCVTargetTracker,
        evidence: dict[str, Any],
        *,
        skill: str,
        initial_target: Pose,
        marker_family_id: str | None = None,
        max_age_s: float = 0.1,
        max_frame_delta_m: float = 0.01,
        max_correction_m: float = 0.05,
    ) -> None:
        if reference.source != "mujoco_camera":
            raise ValueError("visual servo currently requires the MuJoCo development source")
        if skill not in {"MOVE_ABOVE", "APPROACH", "LIFT", "MOVE_TO_REGION", "PLACE", "RETREAT"}:
            raise ValueError("unsupported visual servo skill")
        if any(not math.isfinite(v) or v <= 0 for v in (
            max_age_s, max_frame_delta_m, max_correction_m
        )):
            raise ValueError("servo bounds must be finite and positive")
        self.reference = reference
        self.tracker = tracker
        self.skill = skill
        self.initial_target = initial_target
        self.marker_family_id = marker_family_id
        self.max_age_s = max_age_s
        self.max_frame_delta_m = max_frame_delta_m
        self.max_correction_m = max_correction_m
        self.records: list[dict[str, Any]] = []
        self._last = reference
        self._last_target = np.array([initial_target.x, initial_target.y, initial_target.z])
        self._initial = self._last_target.copy()
        assert tracker.initial is not None and tracker.destination is not None
        self._target_center = np.asarray(tracker.initial["center"])
        self._region_center = np.asarray(tracker.destination["center"])
        self._grasp = np.array([evidence["resolved_top_grasp_tcp"][axis] for axis in "xyz"])
        self._seen: set[str] = set()
        self._validate(reference)
        self._marker_bound = False
        if marker_family_id is not None:
            # Bind the registered rigid marker to the model-selected initial
            # object before it can resolve later colour fragmentation.
            registered_grasp = self._marker_grasp(tracker._reference)
            if registered_grasp is None or np.linalg.norm(registered_grasp - self._grasp) > 0.01:
                raise ValueError("servo initial target/registered marker identity unavailable")
            self._marker_bound = True
        self._reference_grasp, _ = self._measure_target(reference)
        self._reference_region = self._region_center
        if skill in {"MOVE_TO_REGION", "PLACE"}:
            region, reason = measure_servo_region(reference, tracker)
            if region is None:
                raise ValueError("servo reference region geometry unavailable: " + str(reason))
            self._reference_region = np.asarray(region["center"])
        self._seen.add(reference.observation_id)

    @property
    def last_observation(self) -> RGBDObservation:
        return self._last

    def _validate(self, observation: RGBDObservation) -> None:
        identity = self.tracker._reference
        for field in ("episode_id", "scene_id", "source", "width", "height", "intrinsics"):
            if getattr(observation, field) != getattr(identity, field):
                raise ValueError(f"servo observation {field} changed")
        if not observation.episode_id or not observation.calibration_version:
            raise ValueError("servo camera/episode binding missing")
        matrix = np.array(observation.camera_to_world).reshape(4, 4)
        previous = np.array(self._last.camera_to_world).reshape(4, 4)
        moved = not np.array_equal(matrix, previous)
        changed = observation.calibration_version != self._last.calibration_version
        if moved != changed:
            raise ValueError("servo camera pose and calibration version disagree")
        if observation.observation_id in self._seen:
            raise ValueError("servo repeated frame")
        age = (datetime.now(UTC) - observation.captured_at).total_seconds()
        if not 0 <= age <= self.max_age_s:
            raise ValueError("servo frame not fresh")
        gap = observation.sim_time_s - self._last.sim_time_s
        if gap < 0 or gap > self.max_age_s or (self.records and gap <= 0):
            raise ValueError("servo frame time gap or nonmonotonic time")
        if observation.captured_at < self._last.captured_at:
            raise ValueError("servo capture time reversed")

    def _marker_grasp(self, observation: RGBDObservation) -> np.ndarray | None:
        if self.marker_family_id is None:
            return None
        family = marker_family(self.marker_family_id)
        estimate = detect_pose_marker(
            observation,
            PoseMarkerRegistration(
                marker_id=family.marker_id,
                dictionary=cast(Literal["DICT_4X4_50"], family.dictionary),
                marker_size_m=family.marker_size_m,
                marked_asset_sha256=family.asset_sha256,
            ),
            corner_refinement="SUBPIX",
        )
        if estimate.status != "OBSERVED":
            if estimate.reason not in {
                "known_marker_not_observed", "marker_boundary_clipped",
                "marker_resolution_insufficient",
            }:
                raise ValueError("servo registered marker rejected: " + estimate.reason)
            return None
        attachment = np.asarray(family.marker_to_object).reshape(4, 4)
        rotation = np.asarray(estimate.rotation_marker_to_world).reshape(3, 3)
        rotation = rotation @ attachment[:3, :3].T
        if rotation[2, 2] < 0.98:
            raise ValueError("servo registered object is not upright")
        center = np.asarray(estimate.marker_center_world_m) - rotation @ attachment[:3, 3]
        return cast(np.ndarray, center + rotation @ np.array([0, 0, 0.01]))

    def _measure_target(self, observation: RGBDObservation) -> tuple[np.ndarray, str]:
        if self._marker_bound:
            grasp = self._marker_grasp(observation)
            if grasp is None:
                raise ValueError("servo registered marker geometry unavailable")
            return grasp, "CURRENT_REGISTERED_MARKER_DEVELOPMENT_ESTIMATE"
        target, reason = self.tracker._geometry(observation, self.tracker.target_color, target=True)
        source = "CURRENT_OPENCV_RGBD"
        grasp = None
        if target is not None:
            grasp = np.asarray(target["center"]) + self._grasp - self._target_center
        if grasp is None:
            raise ValueError("servo target geometry unavailable: " + str(reason))
        return grasp, source

    def update_with_camera_views(
        self, capture: Callable[[int], RGBDObservation],
        set_view: Callable[[tuple[float, float, float], tuple[float, float, float], str], None],
        views: Sequence[CameraView],
    ) -> Pose:
        """Try at most two other views before any further robot physics step.

        The controller's original sample deadline includes every capture and
        camera change. Each accepted view must independently pass update();
        orientation, identity, invalid depth and calibration failures still stop.
        """
        ordered = list(views)
        alternatives = iter(ordered)
        rejected = []
        recoverable = {
            "servo registered marker geometry unavailable",
            "servo region geometry unavailable: region_current_corner_anchors_insufficient",
            "servo region geometry unavailable: region_missing_color_not_explained_by_foreground",
            "servo region geometry unavailable: region_color_boundary_depth_unresolved",
        }
        for attempt in range(3):
            observation = capture(attempt)
            try:
                target = self.update(observation)
            except ValueError as error:
                if str(error) not in recoverable or attempt == 2:
                    raise
                position = tuple(observation.camera_to_world[i] for i in (3, 7, 11))
                if attempt == 0:
                    # Preserve the framing proposal's preference order. Once a
                    # side view loses near-plane support, the oblique overview
                    # can be more informative than the opposite side. Never
                    # spend the remaining budget recapturing the initial view.
                    alternatives = iter([view for view in ordered
                                         if not np.allclose(view[0], position, atol=1e-9, rtol=0)])
                view = next((view for view in alternatives
                             if not np.allclose(view[0], position, atol=1e-9, rtol=0)), None)
                if view is None:
                    raise
                rejected.append({"observation_id": observation.observation_id,
                                 "reason": str(error), "camera_to_world":
                                 list(observation.camera_to_world)})
                set_view(view[0], view[1], str(error))
            else:
                if rejected and self.records:
                    self.records[-1]["camera_recovery"] = rejected
                return target
        raise AssertionError("camera view budget exhausted")

    def update(self, observation: RGBDObservation) -> Pose:
        observation = RGBDObservation.model_validate(observation.model_dump())
        self._validate(observation)
        grasp, source = self._measure_target(observation)
        endpoint = self._initial.copy()
        region_support = None
        if self.skill in {"MOVE_ABOVE", "APPROACH"}:
            endpoint += grasp - self._reference_grasp
        elif self.skill in {"MOVE_TO_REGION", "PLACE"}:
            region, region_reason = measure_servo_region(observation, self.tracker)
            if region is None:
                raise ValueError("servo region geometry unavailable: " + str(region_reason))
            endpoint += np.asarray(region["center"]) - self._reference_region
            region_support = {key: region[key] for key in (
                "source", "occluded_pixels", "observed_corner_anchors",
                "mixed_foreground_edge_pixels",
                "low_object_sidewall_pixels",
                "mixed_occluder_footprint_pixels",
            ) if key in region}
        if float(np.linalg.norm(endpoint - self._initial)) > self.max_correction_m:
            raise ValueError("servo target left initial correction envelope")
        if float(np.linalg.norm(endpoint - self._last_target)) > self.max_frame_delta_m:
            raise ValueError("servo target jumped between frames")
        if len(self.records) >= 2048:
            raise ValueError("servo frame budget exhausted")
        self.records.append({
            "observation_id": observation.observation_id,
            "checksum_sha256": observation.checksum_sha256,
            "sim_time_s": observation.sim_time_s,
            "captured_at": observation.captured_at.isoformat(),
            "calibration_version": observation.calibration_version,
            "camera_position_m": list(observation.camera_to_world[index] for index in (3, 7, 11)),
            "camera_to_world": list(observation.camera_to_world),
            "target_pose": dict(zip("xyz", map(float, endpoint), strict=True)),
            "target_source": source,
            "formal_geometry_qualification": "UNKNOWN",
            "ground_truth_used_for_control": False,
            **({"region_support": region_support} if region_support is not None else {}),
        })
        self._seen.add(observation.observation_id)
        self._last = observation
        self._last_target = endpoint
        return Pose(x=float(endpoint[0]), y=float(endpoint[1]), z=float(endpoint[2]))
