"""Detects scene-related events: SCENE_CHANGED, SCENE_CONFIDENCE_LOW, PATH_BLOCKED."""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    EventSeverity,
)
from cloud_edge_robot_arm.edge.events.models import DetectionContext


class SceneChangeEventDetector:
    """Detects scene changes, low confidence, and path blockage.

    Configuration:
    - min_scene_confidence: below this threshold → SCENE_CONFIDENCE_LOW
    - scene_version_check: if scene_version changes → SCENE_CHANGED
    """

    def __init__(
        self,
        *,
        min_scene_confidence: float = 0.5,
    ) -> None:
        self._min_confidence = min_scene_confidence

    @property
    def detector_name(self) -> str:
        return "scene_change_detector"

    def detect(self, context: DetectionContext) -> EdgeEvent | None:
        now = datetime.now(UTC)
        step_id = context.step.step_id if context.step else None

        # PATH_BLOCKED — check if scene indicates blocked path
        scene = context.scene_state
        if scene is not None:
            path_blocked = getattr(scene, "path_blocked", None)
            if path_blocked:
                return EdgeEvent(
                    task_id=context.task_id,
                    plan_version=context.plan_version,
                    command_seq=context.command_seq,
                    timestamp=now,
                    event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-path-blocked",
                    event_type=EdgeEventType.PATH_BLOCKED,
                    step_id=step_id,
                    severity=EventSeverity.ERROR,
                    source="edge",
                    robot_id=context.robot_id,
                    detected_at=now,
                    occurred_at=now,
                    scene_version=context.scene_version,
                    reason_code="PATH_BLOCKED",
                    reason_detail="Path blocked by new obstacle",
                    requires_cloud_replan=True,
                )

        # SCENE_CONFIDENCE_LOW
        if context.scene_confidence < self._min_confidence:
            return EdgeEvent(
                task_id=context.task_id,
                plan_version=context.plan_version,
                command_seq=context.command_seq,
                timestamp=now,
                event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-scene-confidence-low",
                event_type=EdgeEventType.SCENE_CONFIDENCE_LOW,
                step_id=step_id,
                severity=EventSeverity.WARNING,
                source="edge",
                robot_id=context.robot_id,
                detected_at=now,
                occurred_at=now,
                scene_version=context.scene_version,
                reason_code="SCENE_CONFIDENCE_LOW",
                reason_detail=(
                    f"Scene confidence {context.scene_confidence} "
                    f"below minimum {self._min_confidence}"
                ),
                details={
                    "scene_confidence": context.scene_confidence,
                    "min_confidence": self._min_confidence,
                },
            )

        # SCENE_CHANGED — detect if scene version differs from contract
        if (
            context.contract is not None
            and context.scene_version > context.contract.expected_scene_version
        ):
            return EdgeEvent(
                task_id=context.task_id,
                plan_version=context.plan_version,
                command_seq=context.command_seq,
                timestamp=now,
                event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-scene-changed",
                event_type=EdgeEventType.SCENE_CHANGED,
                step_id=step_id,
                severity=EventSeverity.WARNING,
                source="edge",
                robot_id=context.robot_id,
                detected_at=now,
                occurred_at=now,
                scene_version=context.scene_version,
                reason_code="SCENE_CHANGED",
                reason_detail=(
                    f"Scene version {context.scene_version} "
                    f"> expected {context.contract.expected_scene_version}"
                ),
                details={
                    "scene_version": context.scene_version,
                    "expected_scene_version": context.contract.expected_scene_version,
                },
            )

        return None
