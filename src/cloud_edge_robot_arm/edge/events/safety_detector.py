"""Detects safety-related events: SAFETY_REJECTED, SAFETY_PAUSED, EMERGENCY_STOP_TRIGGERED."""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    EventSeverity,
)
from cloud_edge_robot_arm.edge.events.models import DetectionContext


class SafetyEventDetector:
    """Detects safety shield events from safety_state in DetectionContext."""

    @property
    def detector_name(self) -> str:
        return "safety_event_detector"

    def detect(self, context: DetectionContext) -> EdgeEvent | None:
        safety = context.safety_state
        if not safety:
            return None

        now = datetime.now(UTC)
        step_id = context.step.step_id if context.step else None

        # EMERGENCY_STOP_TRIGGERED
        if safety.get("emergency_stop_triggered"):
            return self._build_event(
                context,
                now,
                step_id,
                EdgeEventType.EMERGENCY_STOP_TRIGGERED,
                EventSeverity.CRITICAL,
                "EMERGENCY_STOP_TRIGGERED",
                "Emergency stop was triggered",
            )

        # SAFETY_REJECTED
        decision = safety.get("safety_decision", "")
        if decision in ("REJECT", "EMERGENCY_STOP"):
            return self._build_event(
                context,
                now,
                step_id,
                EdgeEventType.SAFETY_REJECTED,
                EventSeverity.ERROR,
                "SAFETY_REJECTED",
                f"Safety shield rejected action with decision={decision}",
            )

        # SAFETY_PAUSED
        if decision == "PAUSE":
            return self._build_event(
                context,
                now,
                step_id,
                EdgeEventType.SAFETY_PAUSED,
                EventSeverity.WARNING,
                "SAFETY_PAUSED",
                "Safety shield requested pause",
            )

        return None

    def _build_event(
        self,
        context: DetectionContext,
        now: datetime,
        step_id: str | None,
        event_type: EdgeEventType,
        severity: EventSeverity,
        reason_code: str,
        reason_detail: str,
    ) -> EdgeEvent:
        return EdgeEvent(
            task_id=context.task_id,
            plan_version=context.plan_version,
            command_seq=context.command_seq,
            timestamp=now,
            event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-{event_type.value.lower()}",
            event_type=event_type,
            step_id=step_id,
            severity=severity,
            source="edge",
            robot_id=context.robot_id,
            detected_at=now,
            occurred_at=now,
            scene_version=context.scene_version,
            reason_code=reason_code,
            reason_detail=reason_detail,
            requires_immediate_stop=(severity == EventSeverity.CRITICAL),
        )
