"""Detects target-related events: TARGET_MOVED, TARGET_LOST.

Distinguishes TARGET_JITTER (no event), TARGET_MOVED, and TARGET_LOST.
Uses position threshold, consecutive observation count, and debounce.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    EventSeverity,
    Pose,
)
from cloud_edge_robot_arm.edge.events.models import DetectionContext


class TargetChangeDetector:
    """Detects target movement and loss events.

    Configuration:
    - position_threshold_m: minimum displacement to classify as MOVED (not JITTER)
    - orientation_threshold_deg: minimum rotation change
    - consecutive_lost_threshold: frames needed to declare TARGET_LOST
    - consecutive_jitter_threshold: frames before JITTER becomes MOVED
    - occlusion_timeout_frames: how many frames before TEMPORARILY_OCCLUDED → LOST
    """

    def __init__(
        self,
        *,
        position_threshold_m: float = 0.02,
        orientation_threshold_deg: float = 5.0,
        consecutive_lost_threshold: int = 3,
        consecutive_jitter_threshold: int = 1,
        occlusion_timeout_frames: int = 10,
    ) -> None:
        self._pos_threshold = position_threshold_m
        self._orient_threshold = orientation_threshold_deg
        self._lost_threshold = consecutive_lost_threshold
        self._jitter_threshold = consecutive_jitter_threshold
        self._occlusion_timeout = occlusion_timeout_frames
        # Track consecutive observations per task
        self._lost_frame_counts: dict[str, int] = {}
        self._jitter_frame_counts: dict[str, int] = {}
        self._last_known_poses: dict[str, Pose] = {}

    @property
    def detector_name(self) -> str:
        return "target_change_detector"

    def detect(self, context: DetectionContext) -> EdgeEvent | None:
        now = datetime.now(UTC)
        step_id = context.step.step_id if context.step else None

        # Check if target is present in scene
        target_pose = self._extract_target_pose(context)
        if target_pose is None:
            return self._handle_target_missing(context, now, step_id)

        # Target is present — check for movement
        self._lost_frame_counts[context.task_id] = 0
        self._jitter_frame_counts.setdefault(context.task_id, 0)

        last_pose = self._last_known_poses.get(context.task_id)
        self._last_known_poses[context.task_id] = target_pose

        if last_pose is None:
            return None  # First observation, no baseline

        displacement_m = self._compute_displacement(last_pose, target_pose)
        if displacement_m < self._pos_threshold:
            self._jitter_frame_counts[context.task_id] = 0
            return None  # TARGET_JITTER — no event emitted

        # Track consecutive jitter
        jitter_count = self._jitter_frame_counts[context.task_id] + 1
        self._jitter_frame_counts[context.task_id] = jitter_count

        if jitter_count < self._jitter_threshold:
            return None  # Still within jitter window

        return EdgeEvent(
            task_id=context.task_id,
            plan_version=context.plan_version,
            command_seq=context.command_seq,
            timestamp=now,
            event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-target-moved",
            event_type=EdgeEventType.TARGET_MOVED,
            step_id=step_id,
            severity=EventSeverity.WARNING,
            source="edge",
            robot_id=context.robot_id,
            detected_at=now,
            occurred_at=now,
            scene_version=context.scene_version,
            reason_code="TARGET_MOVED",
            reason_detail=(
                f"Target displaced {displacement_m:.4f}m (threshold={self._pos_threshold}m), "
                f"consecutive frames={jitter_count}"
            ),
            details={
                "displacement_m": round(displacement_m, 4),
                "threshold_m": self._pos_threshold,
                "consecutive_frames": jitter_count,
                "last_pose": last_pose.model_dump(),
                "current_pose": target_pose.model_dump(),
            },
        )

    def _handle_target_missing(
        self, context: DetectionContext, now: datetime, step_id: str | None
    ) -> EdgeEvent | None:
        lost_count = self._lost_frame_counts.get(context.task_id, 0) + 1
        self._lost_frame_counts[context.task_id] = lost_count

        if lost_count < self._lost_threshold:
            return None  # TEMPORARILY_OCCLUDED — suppress

        return EdgeEvent(
            task_id=context.task_id,
            plan_version=context.plan_version,
            command_seq=context.command_seq,
            timestamp=now,
            event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-target-lost",
            event_type=EdgeEventType.TARGET_LOST,
            step_id=step_id,
            severity=EventSeverity.ERROR,
            source="edge",
            robot_id=context.robot_id,
            detected_at=now,
            occurred_at=now,
            scene_version=context.scene_version,
            reason_code="TARGET_LOST",
            reason_detail=(
                f"Target missing for {lost_count} consecutive "
                f"observations (threshold={self._lost_threshold})"
            ),
            details={
                "consecutive_lost_frames": lost_count,
                "threshold": self._lost_threshold,
            },
        )

    @staticmethod
    def _extract_target_pose(context: DetectionContext) -> Pose | None:
        scene = context.scene_state
        if scene is None:
            return None
        objects = getattr(scene, "objects", None) or []
        if context.contract is not None:
            target_id = context.contract.task_target.object_id
            for obj in objects:
                obj_id = getattr(obj, "object_id", None)
                if obj_id == target_id:
                    pose_raw = getattr(obj, "pose", None)
                if pose_raw is not None:
                    return pose_raw  # type: ignore[no-any-return]
        for obj in objects:
            pose = getattr(obj, "pose", None)
            if pose is not None:
                return pose  # type: ignore[no-any-return]
        return None

    @staticmethod
    def _compute_displacement(a: Pose, b: Pose) -> float:
        return math.hypot(math.hypot(a.x - b.x, a.y - b.y), a.z - b.z)
