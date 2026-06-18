"""Detects execution-related events.

Detects GRASP_FAILED, PLACE_FAILED, VERIFY_FAILED, SKILL_EXECUTION_FAILED.
执行事件检测器。

将抓取、放置、验证和技能执行失败转换为 EdgeEvent，供本地恢复或云端重规划判断。

"""

from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts.models import (
    EdgeEvent,
    EdgeEventType,
    EventSeverity,
    SkillName,
)
from cloud_edge_robot_arm.edge.events.models import DetectionContext


class ExecutionEventDetector:
    """Detects skill execution failures.

    Maps specific SkillName failures to granular event types.
    Falls back to SKILL_EXECUTION_FAILED for unrecognized skills.
    """

    @property
    def detector_name(self) -> str:
        return "execution_event_detector"

    def detect(self, context: DetectionContext) -> EdgeEvent | None:
        result = context.step_result
        if result is None or result.success:
            return None

        step = context.step
        skill = step.skill if step else result.skill

        event_type = self._failure_event_for_skill(skill)

        now = datetime.now(UTC)
        return EdgeEvent(
            task_id=context.task_id,
            plan_version=context.plan_version,
            command_seq=context.command_seq,
            timestamp=now,
            event_id=f"evt-{now.strftime('%Y%m%d%H%M%S%f')}-{event_type.value.lower()}",
            event_type=event_type,
            step_id=step.step_id if step else None,
            severity=EventSeverity.ERROR,
            source="edge",
            robot_id=context.robot_id,
            detected_at=now,
            occurred_at=now,
            scene_version=context.scene_version,
            reason_code=event_type.value.lower(),
            reason_detail=(
                f"Skill {skill.value if hasattr(skill, 'value') else skill} execution failed"
            ),
            details={
                "attempt": getattr(result, "attempt", 0),
                "skill": skill.value if hasattr(skill, "value") else str(skill),
                "error": result.error.model_dump() if result.error else None,
                "duration_ms": result.duration_ms,
            },
        )

    @staticmethod
    def _failure_event_for_skill(skill: SkillName | str) -> EdgeEventType:
        skill_str = skill.value if isinstance(skill, SkillName) else str(skill)
        mapping: dict[str, EdgeEventType] = {
            "GRASP": EdgeEventType.GRASP_FAILED,
            "PLACE": EdgeEventType.PLACE_FAILED,
            "VERIFY_RESULT": EdgeEventType.VERIFY_FAILED,
        }
        return mapping.get(skill_str, EdgeEventType.SKILL_EXECUTION_FAILED)
