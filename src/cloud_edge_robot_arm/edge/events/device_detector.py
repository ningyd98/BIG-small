"""Detects device health events: DEVICE_FAULT, TELEMETRY_STALE (from device side)."""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    EventSeverity,
)
from cloud_edge_robot_arm.edge.events.models import DetectionContext


class DeviceHealthEventDetector:
    """设备健康事件检测器。
    用于识别设备故障和设备侧遥测过期；UNKNOWN 或 stale 状态不能被当作健康。

    Detects device faults from the robot state and device health data.
    """

    @property
    def detector_name(self) -> str:
        return "device_health_detector"

    def detect(self, context: DetectionContext) -> EdgeEvent | None:
        now = datetime.now(UTC)
        step_id = context.step.step_id if context.step else None

        # Check robot state for fault indicators
        robot = context.robot_state
        if robot is not None:
            if robot.collision_detected:
                return EdgeEvent(
                    task_id=context.task_id,
                    plan_version=context.plan_version,
                    command_seq=context.command_seq,
                    timestamp=now,
                    event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-device-fault",
                    event_type=EdgeEventType.DEVICE_FAULT,
                    step_id=step_id,
                    severity=EventSeverity.CRITICAL,
                    source="edge",
                    robot_id=context.robot_id,
                    detected_at=now,
                    occurred_at=now,
                    scene_version=context.scene_version,
                    reason_code="DEVICE_COLLISION",
                    reason_detail="Robot collision detected",
                    requires_immediate_stop=True,
                )

            if robot.estop_engaged:
                return EdgeEvent(
                    task_id=context.task_id,
                    plan_version=context.plan_version,
                    command_seq=context.command_seq,
                    timestamp=now,
                    event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-device-fault-estop",
                    event_type=EdgeEventType.DEVICE_FAULT,
                    step_id=step_id,
                    severity=EventSeverity.CRITICAL,
                    source="edge",
                    robot_id=context.robot_id,
                    detected_at=now,
                    occurred_at=now,
                    scene_version=context.scene_version,
                    reason_code="DEVICE_ESTOP_ENGAGED",
                    reason_detail="Emergency stop is engaged",
                    requires_immediate_stop=True,
                )

            if not robot.connected:
                return EdgeEvent(
                    task_id=context.task_id,
                    plan_version=context.plan_version,
                    command_seq=context.command_seq,
                    timestamp=now,
                    event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-device-fault-disconnected",
                    event_type=EdgeEventType.DEVICE_FAULT,
                    step_id=step_id,
                    severity=EventSeverity.CRITICAL,
                    source="edge",
                    robot_id=context.robot_id,
                    detected_at=now,
                    occurred_at=now,
                    scene_version=context.scene_version,
                    reason_code="DEVICE_DISCONNECTED",
                    reason_detail="Robot is not connected",
                    requires_immediate_stop=True,
                )

        # Check device_health dict
        health = context.device_health
        if health and health.get("fault"):
            return EdgeEvent(
                task_id=context.task_id,
                plan_version=context.plan_version,
                command_seq=context.command_seq,
                timestamp=now,
                event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-device-fault-generic",
                event_type=EdgeEventType.DEVICE_FAULT,
                step_id=step_id,
                severity=EventSeverity.CRITICAL,
                source="edge",
                robot_id=context.robot_id,
                detected_at=now,
                occurred_at=now,
                scene_version=context.scene_version,
                reason_code=str(health.get("fault_code", "DEVICE_FAULT")),
                reason_detail=str(health.get("fault_message", "Device fault detected")),
                requires_immediate_stop=True,
            )

        return None
