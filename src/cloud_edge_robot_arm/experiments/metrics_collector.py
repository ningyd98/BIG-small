"""事件驱动指标收集器。

该模块从 ExperimentEvent 流中提取成功、失败、安全介入、重试和恢复计数，
保证指标来源可追溯到原始事件。
"""

from __future__ import annotations

from dataclasses import dataclass

from cloud_edge_robot_arm.experiments.models import ExperimentEvent


@dataclass(frozen=True)
class EventSourcedMetrics:
    completed_step_count: int = 0
    failed_step_count: int = 0
    safety_allow_count: int = 0
    safety_allow_with_limits_count: int = 0
    safety_pause_count: int = 0
    safety_reject_count: int = 0
    emergency_stop_count: int = 0
    stale_command_rejection_count: int = 0
    duplicate_command_rejection_count: int = 0
    reordered_command_rejection_count: int = 0
    cloud_invocation_count: int = 0
    supervisory_decision_count: int = 0
    replan_count: int = 0
    mode_switch_count: int = 0


class ExperimentMetricsCollector:
    def __init__(self, events: list[ExperimentEvent]) -> None:
        self._events = list(events)

    @classmethod
    def from_events(cls, events: list[ExperimentEvent]) -> ExperimentMetricsCollector:
        return cls(events)

    def collect(self) -> EventSourcedMetrics:
        completed: set[str] = set()
        failed = 0
        safety_allow = 0
        safety_allow_limits = 0
        safety_pause = 0
        safety_reject = 0
        emergency = 0
        stale = 0
        duplicate = 0
        reordered = 0
        cloud = 0
        supervisory = 0
        replan = 0
        switches = 0

        for event in self._events:
            payload = event.payload
            if event.event_type == "step_completed":
                completed.add(event.entity_id)
                decision = str(payload.get("safety_decision", "ALLOW"))
                if decision == "ALLOW_WITH_LIMITS":
                    safety_allow_limits += 1
                elif decision == "ALLOW" or not decision:
                    safety_allow += 1
            elif event.event_type in {"step_failed", "step_paused", "step_rejected"}:
                failed += 1
                decision = str(payload.get("safety_decision", ""))
                error_code = str(payload.get("error_code", ""))
                if decision == "PAUSE":
                    safety_pause += 1
                elif decision in {"REJECT", "REQUEST_CORRECTION"} or error_code in {
                    "SAFETY_ACTION_REJECTED",
                    "SAFETY_REQUEST_CORRECTION",
                }:
                    safety_reject += 1
                elif decision == "EMERGENCY_STOP" or error_code in {
                    "EMERGENCY_STOP_ACTIVE",
                    "SAFETY_EMERGENCY_STOP",
                }:
                    emergency += 1
            elif event.event_type == "safety_decision":
                decision = str(payload.get("decision", ""))
                if decision == "ALLOW":
                    safety_allow += 1
                elif decision == "ALLOW_WITH_LIMITS":
                    safety_allow_limits += 1
                elif decision == "PAUSE":
                    safety_pause += 1
                elif decision in {"REJECT", "REQUEST_CORRECTION"}:
                    safety_reject += 1
                elif decision == "EMERGENCY_STOP":
                    emergency += 1
            elif event.event_type == "command_ack":
                status = str(payload.get("status", ""))
                if status in {
                    "REJECTED_STALE_SEQUENCE",
                    "REJECTED_STALE_PLAN",
                    "REJECTED_PLAN_VERSION_MISMATCH",
                    "REJECTED_SCENE_MISMATCH",
                }:
                    stale += 1
                elif status in {"REJECTED_DUPLICATE", "REJECTED_IDEMPOTENCY_CONFLICT"}:
                    duplicate += 1
                elif status in {"REJECTED_OUT_OF_ORDER", "REJECTED_EXPIRED"}:
                    reordered += 1
            elif event.event_type == "command_rejections":
                stale += _payload_int(payload.get("stale"), default=1)
                duplicate += _payload_int(payload.get("duplicate"), default=1)
                reordered += _payload_int(payload.get("reordered"), default=1)
            elif event.event_type in {"cloud_invocation", "supervision_planner_invoked"}:
                cloud += 1
            elif event.event_type == "supervisory_decision":
                supervisory += 1
            elif event.event_type in {"replan_applied", "target_replanned", "obstacle_recovery"}:
                replan += 1
            elif event.event_type == "mode_transition_committed":
                switches += 1

        return EventSourcedMetrics(
            completed_step_count=len(completed),
            failed_step_count=failed,
            safety_allow_count=safety_allow,
            safety_allow_with_limits_count=safety_allow_limits,
            safety_pause_count=safety_pause,
            safety_reject_count=safety_reject,
            emergency_stop_count=emergency,
            stale_command_rejection_count=stale,
            duplicate_command_rejection_count=duplicate,
            reordered_command_rejection_count=reordered,
            cloud_invocation_count=cloud,
            supervisory_decision_count=supervisory,
            replan_count=replan,
            mode_switch_count=switches,
        )


def _payload_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default
