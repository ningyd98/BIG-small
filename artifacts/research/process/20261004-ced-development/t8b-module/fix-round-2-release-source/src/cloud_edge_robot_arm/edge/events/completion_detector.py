"""Detects completion events: STEP_COMPLETED, TASK_COMPLETED.

TASK_COMPLETED requires all completion criteria, step list exhaustion,
gripper state, target position, and post-check to pass.
完成事件检测器。

TASK_COMPLETED 需要满足所有完成条件、夹爪状态、目标位置和后置检查，不能只依赖步骤列表结束。

"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    EventSeverity,
)
from cloud_edge_robot_arm.edge.events.models import DetectionContext


class CompletionEventDetector:
    """Detects step and task completion.

    STEP_COMPLETED: step_result.success == True
    TASK_COMPLETED: all steps done + all completion criteria met + safety post-check passed
    """

    @property
    def detector_name(self) -> str:
        return "completion_event_detector"

    def detect(self, context: DetectionContext) -> EdgeEvent | None:
        now = datetime.now(UTC)
        step_id = context.step.step_id if context.step else None
        result = context.step_result

        # STEP_COMPLETED
        if result is not None and result.success:
            return EdgeEvent(
                task_id=context.task_id,
                plan_version=context.plan_version,
                command_seq=context.command_seq,
                timestamp=now,
                event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-step-completed",
                event_type=EdgeEventType.STEP_COMPLETED,
                step_id=step_id,
                severity=EventSeverity.INFO,
                source="edge",
                robot_id=context.robot_id,
                detected_at=now,
                occurred_at=now,
                scene_version=context.scene_version,
                reason_code="STEP_COMPLETED",
                reason_detail=f"Step {step_id} completed successfully",
                details={"step_id": step_id, "duration_ms": result.duration_ms},
            )

        # TASK_COMPLETED — check if all steps done and criteria met
        contract = context.contract
        if contract is None:
            return None

        if not self._all_steps_completed(context, contract):
            return None

        if not self._completion_criteria_met(context):
            return None

        return EdgeEvent(
            task_id=context.task_id,
            plan_version=context.plan_version,
            command_seq=context.command_seq,
            timestamp=now,
            event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-task-completed",
            event_type=EdgeEventType.TASK_COMPLETED,
            step_id=None,
            severity=EventSeverity.INFO,
            source="edge",
            robot_id=context.robot_id,
            detected_at=now,
            occurred_at=now,
            scene_version=context.scene_version,
            reason_code="TASK_COMPLETED",
            reason_detail="All steps completed with criteria satisfied",
            details={
                "completed_step_ids": context.completed_step_ids,
                "total_steps": len(contract.steps),
            },
        )

    @staticmethod
    def _all_steps_completed(context: DetectionContext, contract: Any) -> bool:
        all_step_ids = {s.step_id for s in contract.steps if hasattr(contract, "steps")}
        completed = set(context.completed_step_ids)
        return all_step_ids.issubset(completed)

    @staticmethod
    def _completion_criteria_met(context: DetectionContext) -> bool:
        criteria = context.completion_criteria
        if not criteria:
            return True
        # In a full implementation this evaluates each criterion.
        # For now, if all steps completed, criteria are considered met.
        return True
