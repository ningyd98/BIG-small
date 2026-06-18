"""Detection context and shared types for event detectors."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cloud_edge_robot_arm.contracts.models import (
    RobotState,
    TaskContract,
    TaskStep,
)


@dataclass(frozen=True)
class DetectionContext:
    """Structured input for event detectors.

        All fields are read-only. Detectors must not mutate this context.
        No direct global variable access — all data flows through this struct.
    事件检测共享模型。

    DetectionContext 汇集任务合同、机器人状态、网络状态和安全状态，是 detector 的只读输入。

    """

    task_id: str
    plan_version: int
    command_seq: int
    robot_id: str = ""
    step: TaskStep | None = None
    step_result: Any | None = None
    robot_state: RobotState | None = None
    contract: TaskContract | None = None
    elapsed_action_ms: int = 0
    step_attempts: dict[str, int] = field(default_factory=dict)
    scene_version: int = 0
    scene_confidence: float = 1.0
    telemetry: object | None = None
    scene_state: object | None = None
    task_started_at: datetime | None = None
    network_connected: bool = True
    completed_step_ids: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    safety_state: dict[str, object] = field(default_factory=dict)
    device_health: dict[str, object] = field(default_factory=dict)
