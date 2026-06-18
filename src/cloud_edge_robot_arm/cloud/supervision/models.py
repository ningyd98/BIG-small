"""结构化数据模型，作为 API、测试和服务之间的稳定契约。

Phase 5 supervision data models.

Periodic Cloud Supervisory Control (PCSC):
- SupervisoryDecision — the structured output of each supervision cycle
- EdgeStatusSnapshot — state received from the edge each cycle
- CommandAckStatus — extended ack states for command versioning/TTL
- SupervisionConfig — configurable supervision parameters
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from cloud_edge_robot_arm.contracts import TaskStep

# ── Reason codes ─────────────────────────────────────────────────────────────


class SupervisionReasonCode(StrEnum):
    SCENE_STABLE = "SCENE_STABLE"
    TARGET_MOVED_CURRENT_STEP = "TARGET_MOVED_CURRENT_STEP"
    TARGET_MOVED_REMAINING_PLAN = "TARGET_MOVED_REMAINING_PLAN"
    OBSTACLE_BLOCKS_CURRENT_PATH = "OBSTACLE_BLOCKS_CURRENT_PATH"
    OBSTACLE_BLOCKS_REMAINING_PATH = "OBSTACLE_BLOCKS_REMAINING_PATH"
    EDGE_STATE_STALE = "EDGE_STATE_STALE"
    SCENE_CONFIDENCE_LOW = "SCENE_CONFIDENCE_LOW"
    ROBOT_STATE_INVALID = "ROBOT_STATE_INVALID"
    NETWORK_DEGRADED = "NETWORK_DEGRADED"
    SAFETY_RISK_INCREASED = "SAFETY_RISK_INCREASED"
    PLAN_ALREADY_COMPLETED = "PLAN_ALREADY_COMPLETED"
    PLAN_VERSION_MISMATCH = "PLAN_VERSION_MISMATCH"
    UNSUPPORTED_STATE_TRANSITION = "UNSUPPORTED_STATE_TRANSITION"
    SUPERVISOR_INTERNAL_ERROR = "SUPERVISOR_INTERNAL_ERROR"
    COLLISION_RISK_DETECTED = "COLLISION_RISK_DETECTED"
    PATH_CHANGED = "PATH_CHANGED"


# ── Supervisory decision ─────────────────────────────────────────────────────


class SupervisoryDecisionType(StrEnum):
    KEEP_CURRENT_PLAN = "KEEP_CURRENT_PLAN"
    UPDATE_CURRENT_STEP = "UPDATE_CURRENT_STEP"
    REPLACE_REMAINING_STEPS = "REPLACE_REMAINING_STEPS"
    PAUSE_TASK = "PAUSE_TASK"
    REQUEST_MORE_OBSERVATION = "REQUEST_MORE_OBSERVATION"
    ABORT_TASK = "ABORT_TASK"


# ── Extended CommandAck statuses ─────────────────────────────────────────────


class CommandAckStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_LIMITS = "ACCEPTED_WITH_LIMITS"
    REJECTED_EXPIRED = "REJECTED_EXPIRED"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
    REJECTED_OUT_OF_ORDER = "REJECTED_OUT_OF_ORDER"
    REJECTED_PLAN_VERSION_MISMATCH = "REJECTED_PLAN_VERSION_MISMATCH"
    REJECTED_SCENE_MISMATCH = "REJECTED_SCENE_MISMATCH"
    REJECTED_TASK_MISMATCH = "REJECTED_TASK_MISMATCH"
    REJECTED_ROBOT_MISMATCH = "REJECTED_ROBOT_MISMATCH"
    REJECTED_SCHEMA_INVALID = "REJECTED_SCHEMA_INVALID"
    REJECTED_SEMANTIC_INVALID = "REJECTED_SEMANTIC_INVALID"
    REJECTED_SAFETY_CONFLICT = "REJECTED_SAFETY_CONFLICT"


# ── Edge status snapshot ─────────────────────────────────────────────────────


class EdgeStatusSnapshot(BaseModel):
    """Structured state received from the edge each supervision cycle."""

    robot_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    plan_version: int = Field(ge=0)
    command_seq: int = Field(ge=0)
    scene_version: int = Field(ge=0)
    timestamp: datetime
    current_step_id: str | None = None
    completed_step_ids: list[str] = Field(default_factory=list)
    current_skill: str | None = None
    execution_status: str = "EXECUTING"
    robot_state: dict[str, Any] = Field(default_factory=dict)
    target_state: dict[str, Any] = Field(default_factory=dict)
    obstacle_state: dict[str, Any] = Field(default_factory=dict)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    safety_state: dict[str, Any] = Field(default_factory=dict)
    network_state: dict[str, Any] = Field(default_factory=dict)
    scene_confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    last_command_ack: CommandAckStatus | None = None


# ── SupervisoryDecision output ───────────────────────────────────────────────


class SupervisoryDecision(BaseModel):
    """The structured output of one supervision cycle."""

    decision_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    based_on_plan_version: int = Field(ge=0)
    resulting_plan_version: int = Field(ge=0)
    command_seq: int = Field(ge=0)
    previous_command_seq: int = Field(ge=0)
    decision: SupervisoryDecisionType
    reason_code: SupervisionReasonCode
    reason_detail: str = Field(default="")
    edge_state_timestamp: datetime
    cloud_decision_timestamp: datetime
    scene_version: int = Field(ge=0)
    valid_until: datetime
    command_ttl_ms: int = Field(gt=0)
    updated_steps: list[TaskStep] = Field(default_factory=list)
    planner_invoked: bool = False
    planner_adapter: str | None = None
    prompt_version: str | None = None
    policy_version: str = "1.0"
    policy_hash: str = ""
    correlation_id: str = Field(min_length=1)
    idempotency_key: str = ""

    # Computed fields
    input_state_hash: str = ""
    output_decision_hash: str = ""
    cycle_latency_ms: int = 0

    def is_update(self) -> bool:
        return self.decision in {
            SupervisoryDecisionType.UPDATE_CURRENT_STEP,
            SupervisoryDecisionType.REPLACE_REMAINING_STEPS,
        }


# ── Supervision config ───────────────────────────────────────────────────────


class SupervisionConfig(BaseModel):
    """Configurable parameters for the periodic supervision loop."""

    supervision_period_ms: int = Field(ge=500, le=10_000, default=1_000)
    command_ttl_ms: int = Field(gt=0, default=2_500)
    supervision_timeout_ms: int = Field(gt=0, default=5_000)
    max_missed_supervision_cycles: int = Field(ge=1, default=3)
    stale_state_threshold_ms: int = Field(ge=0, default=5_000)
    target_displacement_threshold_m: float = Field(ge=0.001, default=0.02)
    min_scene_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    allow_finish_current_atomic_skill: bool = True
    pause_on_unknown_risk: bool = True
    planner_timeout_ms: int = Field(gt=0, default=30_000)
    planner_max_retries: int = Field(ge=0, default=2)

    # Accepted supervision periods
    @staticmethod
    def allowed_periods() -> list[int]:
        return [500, 1_000, 2_000, 5_000]
