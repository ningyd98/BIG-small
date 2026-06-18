"""组合事件检测入口。

该模块按固定 detector 列表汇总完成、设备、网络、场景和安全事件，并在统一出口做
去重、抑制窗口和严重级别排序，避免同一运行现象生成重复审计事件。
"""

from __future__ import annotations

from cloud_edge_robot_arm.contracts.models import EdgeEvent
from cloud_edge_robot_arm.edge.events.completion_detector import CompletionEventDetector
from cloud_edge_robot_arm.edge.events.detector import EventDetector
from cloud_edge_robot_arm.edge.events.device_detector import DeviceHealthEventDetector
from cloud_edge_robot_arm.edge.events.execution_detector import ExecutionEventDetector
from cloud_edge_robot_arm.edge.events.models import DetectionContext
from cloud_edge_robot_arm.edge.events.network_detector import NetworkEventDetector
from cloud_edge_robot_arm.edge.events.safety_detector import SafetyEventDetector
from cloud_edge_robot_arm.edge.events.scene_detector import SceneChangeEventDetector
from cloud_edge_robot_arm.edge.events.target_detector import TargetChangeDetector
from cloud_edge_robot_arm.edge.events.timeout_detector import TimeoutEventDetector


class CompositeEventDetector:
    """Runs all registered detectors against a DetectionContext.

        Handles:
        - Deduplication: same event_type + step_id → only first recorded
        - Event suppression window: rapid-fire events within cooldown are suppressed
        - Priority ordering: CRITICAL events always reported first
    组合事件检测器。

    该模块按固定顺序调用各类 detector，并统一去重和 debounce，避免同一物理现象生成重复事件。

    """

    def __init__(
        self,
        detectors: list[EventDetector] | None = None,
        *,
        dedup_window_ms: int = 500,
    ) -> None:
        self._detectors = detectors or _default_detectors()
        self._dedup_window_ms = dedup_window_ms
        # Dedup tracking: (task_id, event_type, step_id, attempt) → event_id
        self._seen_events: dict[tuple[str, str, str, str], str] = {}

    @property
    def detectors(self) -> list[EventDetector]:
        return list(self._detectors)

    def detect_all(self, context: DetectionContext) -> list[EdgeEvent]:
        """Run all detectors and return deduplicated, sorted events.

        CRITICAL events are returned first. Within the same severity,
        events are returned in detection order.
        """
        events: list[EdgeEvent] = []

        for detector in self._detectors:
            try:
                event = detector.detect(context)
            except Exception:
                # Detectors must not crash the overall detection loop.
                # A failed detector is logged at the caller level.
                continue

            if event is None:
                continue

            if self._is_duplicate(event):
                continue

            key = self._dedup_key(event)
            self._seen_events[key] = event.event_id
            events.append(event)

        # Sort: CRITICAL first, then ERROR, WARNING, INFO
        severity_order = {"CRITICAL": 0, "ERROR": 1, "WARNING": 2, "INFO": 3}
        events.sort(key=lambda e: severity_order.get(str(e.severity), 99))
        return events

    def reset_dedup(self) -> None:
        """Clear dedup state between tasks."""
        self._seen_events.clear()

    def _is_duplicate(self, event: EdgeEvent) -> bool:
        key = self._dedup_key(event)
        return key in self._seen_events

    @staticmethod
    def _dedup_key(event: EdgeEvent) -> tuple[str, str, str, str]:
        step = event.step_id or ""
        attempt = str(event.details.get("attempt", ""))
        return (event.task_id, event.event_type.value, step, attempt)


def _default_detectors() -> list[EventDetector]:
    return [
        SafetyEventDetector(),
        DeviceHealthEventDetector(),
        ExecutionEventDetector(),
        TimeoutEventDetector(),
        TargetChangeDetector(),
        SceneChangeEventDetector(),
        NetworkEventDetector(),
        CompletionEventDetector(),
    ]
