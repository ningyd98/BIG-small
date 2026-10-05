"""Detects timeout-related events: STEP_TIMEOUT, TASK_TIMEOUT, TELEMETRY_STALE.

Uses injected Clock — never wall-clock or sleep.
超时事件检测器。

使用注入的 Clock 判断步骤、任务和遥测超时，避免测试或仿真中依赖真实 sleep。

"""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.cloud.supervision.core import Clock
from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    EventSeverity,
)
from cloud_edge_robot_arm.edge.events.models import DetectionContext


class TimeoutEventDetector:
    """Detects timeout events using an injected Clock.

    Detects:
    - STEP_TIMEOUT: step execution exceeds its timeout_ms
    - TASK_TIMEOUT: total task duration exceeds task deadline
    - TELEMETRY_STALE: telemetry data exceeds staleness threshold
    """

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        telemetry_staleness_ms: int = 5000,
    ) -> None:
        self._clock = clock
        self._telemetry_staleness_ms = telemetry_staleness_ms

    @property
    def detector_name(self) -> str:
        return "timeout_event_detector"

    def detect(self, context: DetectionContext) -> EdgeEvent | None:
        now = self._now()

        # STEP_TIMEOUT
        step_event = self._check_step_timeout(context, now)
        if step_event is not None:
            return step_event

        # TASK_TIMEOUT
        task_event = self._check_task_timeout(context, now)
        if task_event is not None:
            return task_event

        # TELEMETRY_STALE
        stale_event = self._check_telemetry_stale(context, now)
        if stale_event is not None:
            return stale_event

        return None

    def _check_step_timeout(self, context: DetectionContext, now: datetime) -> EdgeEvent | None:
        step = context.step
        if step is None:
            return None
        if context.elapsed_action_ms <= step.timeout_ms:
            return None

        overrun_ms = context.elapsed_action_ms - step.timeout_ms
        return EdgeEvent(
            task_id=context.task_id,
            plan_version=context.plan_version,
            command_seq=context.command_seq,
            timestamp=now,
            event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-step-timeout",
            event_type=EdgeEventType.STEP_TIMEOUT,
            step_id=step.step_id,
            severity=EventSeverity.ERROR,
            source="edge",
            robot_id=context.robot_id,
            detected_at=now,
            occurred_at=now,
            scene_version=context.scene_version,
            reason_code="STEP_TIMEOUT",
            reason_detail=(
                f"Step {step.step_id} elapsed {context.elapsed_action_ms}ms, "
                f"timeout={step.timeout_ms}ms, overrun={overrun_ms}ms"
            ),
            details={
                "step_id": step.step_id,
                "elapsed_ms": context.elapsed_action_ms,
                "timeout_ms": step.timeout_ms,
                "overrun_ms": overrun_ms,
            },
        )

    def _check_task_timeout(self, context: DetectionContext, now: datetime) -> EdgeEvent | None:
        if context.task_started_at is None or context.contract is None:
            return None
        deadline_ms = context.contract.command_ttl_ms
        if deadline_ms is None:
            return None

        elapsed = (now - context.task_started_at).total_seconds() * 1000.0
        if elapsed <= deadline_ms:
            return None

        overrun_ms = int(elapsed - deadline_ms)
        return EdgeEvent(
            task_id=context.task_id,
            plan_version=context.plan_version,
            command_seq=context.command_seq,
            timestamp=now,
            event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-task-timeout",
            event_type=EdgeEventType.TASK_TIMEOUT,
            step_id=None,
            severity=EventSeverity.ERROR,
            source="edge",
            robot_id=context.robot_id,
            detected_at=now,
            occurred_at=now,
            scene_version=context.scene_version,
            reason_code="TASK_TIMEOUT",
            reason_detail=(
                f"Task elapsed {int(elapsed)}ms, deadline={deadline_ms}ms, overrun={overrun_ms}ms"
            ),
            details={
                "elapsed_ms": int(elapsed),
                "deadline_ms": deadline_ms,
                "overrun_ms": overrun_ms,
            },
        )

    def _check_telemetry_stale(self, context: DetectionContext, now: datetime) -> EdgeEvent | None:
        telemetry = context.telemetry
        if telemetry is None:
            return None
        tel_ts = getattr(telemetry, "timestamp", None)
        if tel_ts is None:
            return None
        age_ms = (now - tel_ts).total_seconds() * 1000.0
        if age_ms <= self._telemetry_staleness_ms:
            return None

        return EdgeEvent(
            task_id=context.task_id,
            plan_version=context.plan_version,
            command_seq=context.command_seq,
            timestamp=now,
            event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-telemetry-stale",
            event_type=EdgeEventType.TELEMETRY_STALE,
            step_id=context.step.step_id if context.step else None,
            severity=EventSeverity.WARNING,
            source="edge",
            robot_id=context.robot_id,
            detected_at=now,
            occurred_at=now,
            scene_version=context.scene_version,
            reason_code="TELEMETRY_STALE",
            reason_detail=(
                f"Telemetry age {int(age_ms)}ms "
                f"exceeds staleness threshold {self._telemetry_staleness_ms}ms"
            ),
            details={
                "telemetry_age_ms": int(age_ms),
                "staleness_threshold_ms": self._telemetry_staleness_ms,
            },
        )

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        return datetime.now(UTC)
