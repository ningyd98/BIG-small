"""重规划上下文模型，汇总事件、合同、执行状态和恢复预算。

Replanning context passed to cloud adapters and validators.
"""

from __future__ import annotations

from dataclasses import dataclass

from cloud_edge_robot_arm.contracts.models import (
    ExecutionCheckpoint,
    FailureSummary,
    SkillName,
    TaskContract,
    TaskStep,
)


@dataclass(frozen=True)
class ReplanningContext:
    active_contract: TaskContract
    failed_step: TaskStep
    completed_steps: list[TaskStep]
    checkpoint: ExecutionCheckpoint | None = None
    failure_summary: FailureSummary | None = None
    allowed_skills: set[SkillName] | None = None
    safety_constraints: dict[str, object] | None = None
