"""网络状态事件检测器。

该模块根据当前任务的网络连接状态和上一帧状态识别断连、恢复和退化事件，为
PCSC/ETEAC/AUTO 的云边协同策略切换提供审计输入。
"""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    EventSeverity,
)
from cloud_edge_robot_arm.edge.events.models import DetectionContext


class NetworkEventDetector:
    """Detects network state changes.

        Tracks previous network state per task to detect transitions.
    网络事件检测器。

    根据网络状态识别退化、断连和恢复事件，帮助 PCSC/ETEAC/AUTO 模式判断云边协同策略。

    """

    def __init__(self) -> None:
        self._previous_state: dict[str, bool] = {}

    @property
    def detector_name(self) -> str:
        return "network_event_detector"

    def detect(self, context: DetectionContext) -> EdgeEvent | None:
        now = datetime.now(UTC)
        step_id = context.step.step_id if context.step else None
        prev = self._previous_state.get(context.task_id, True)
        current = context.network_connected
        self._previous_state[context.task_id] = current

        # NETWORK_LOST — transition from connected to disconnected
        if prev and not current:
            return EdgeEvent(
                task_id=context.task_id,
                plan_version=context.plan_version,
                command_seq=context.command_seq,
                timestamp=now,
                event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-network-lost",
                event_type=EdgeEventType.NETWORK_LOST,
                step_id=step_id,
                severity=EventSeverity.WARNING,
                source="edge",
                robot_id=context.robot_id,
                detected_at=now,
                occurred_at=now,
                scene_version=context.scene_version,
                reason_code="NETWORK_LOST",
                reason_detail="Network connection lost",
            )

        # NETWORK_RECOVERED — transition from disconnected to connected
        if not prev and current:
            return EdgeEvent(
                task_id=context.task_id,
                plan_version=context.plan_version,
                command_seq=context.command_seq,
                timestamp=now,
                event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-network-recovered",
                event_type=EdgeEventType.NETWORK_RECOVERED,
                step_id=step_id,
                severity=EventSeverity.INFO,
                source="edge",
                robot_id=context.robot_id,
                detected_at=now,
                occurred_at=now,
                scene_version=context.scene_version,
                reason_code="NETWORK_RECOVERED",
                reason_detail="Network connection restored",
            )

        # NETWORK_DEGRADED — still connected but with issues
        if current and self._is_degraded(context):
            return EdgeEvent(
                task_id=context.task_id,
                plan_version=context.plan_version,
                command_seq=context.command_seq,
                timestamp=now,
                event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-network-degraded",
                event_type=EdgeEventType.NETWORK_DEGRADED,
                step_id=step_id,
                severity=EventSeverity.WARNING,
                source="edge",
                robot_id=context.robot_id,
                detected_at=now,
                occurred_at=now,
                scene_version=context.scene_version,
                reason_code="NETWORK_DEGRADED",
                reason_detail="Network performance degraded",
            )

        return None

    @staticmethod
    def _is_degraded(context: DetectionContext) -> bool:
        telemetry = context.telemetry
        if telemetry is None:
            return False
        net_state = getattr(telemetry, "network_state", None) or {}
        return bool(net_state.get("degraded", False))
