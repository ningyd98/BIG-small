"""安全领域模型。

定义 SafetyContext、规则结果、障碍物、工作空间和硬限制，是 SafetyShield 的结构化契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.contracts import SafetyDecision, TaskContract
from cloud_edge_robot_arm.errors import StructuredError


class HardSafetyLimits(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_tcp_velocity: float = Field(gt=0, default=1.0)
    max_joint_velocity: float = Field(gt=0, default=2.0)
    max_acceleration: float = Field(gt=0, default=5.0)
    minimum_safe_height: float = Field(ge=0, default=0.08)
    workspace_x_min: float = -0.5
    workspace_x_max: float = 0.5
    workspace_y_min: float = -0.5
    workspace_y_max: float = 0.5
    workspace_z_min: float = 0.0
    workspace_z_max: float = 0.6
    max_reach_m: float = Field(gt=0, default=0.65)
    obstacle_safety_distance: float = Field(ge=0, default=0.05)
    carry_safety_margin: float = Field(ge=0, default=0.02)
    step_timeout_safety_margin_ms: int = Field(ge=0, default=200)
    task_deadline_safety_margin_ms: int = Field(ge=0, default=500)
    scene_staleness_ms: int = Field(ge=0, default=5_000)
    telemetry_staleness_ms: int = Field(ge=0, default=5_000)
    command_ttl_ms: int = Field(gt=0, default=10_000)
    watchdog_timeout_ms: int = Field(gt=0, default=30_000)
    low_height_exception_skills: frozenset[str] = frozenset(
        {"APPROACH", "GRASP", "PLACE", "RELEASE"}
    )

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        d["low_height_exception_skills"] = list(self.low_height_exception_skills)
        return d


class Obstacle(BaseModel):
    model_config = ConfigDict(frozen=True)

    obstacle_id: str
    x: float
    y: float
    z: float
    radius_m: float = Field(ge=0, default=0.05)


class WorkspaceDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    workspace_id: str = Field(min_length=1)
    x_min: float = -0.5
    x_max: float = 0.5
    y_min: float = -0.5
    y_max: float = 0.5
    z_min: float = 0.0
    z_max: float = 0.6


class SafetyContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str
    plan_version: int
    command_seq: int
    step_id: str
    skill: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    contract: TaskContract
    robot_connected: bool = False
    robot_stopped: bool = False
    robot_estop_engaged: bool = False
    robot_collision_detected: bool = False
    tcp_x: float = 0.0
    tcp_y: float = 0.0
    tcp_z: float = 0.18
    tcp_velocity: float = 0.0
    requested_acceleration: float = 0.0
    joint_velocities: list[float] = Field(default_factory=list)
    scene_version: int = 0
    scene_updated_at: datetime | None = None
    telemetry_timestamp: datetime | None = None
    command_issued_at: datetime | None = None
    command_valid_until: datetime | None = None
    obstacles: list[Obstacle] = Field(default_factory=list)
    forbidden_zones: list[WorkspaceDefinition] = Field(default_factory=list)
    holding_object: bool = False
    step_started_at: float | None = None
    task_started_at_mono: float | None = None
    monotonic_now: float | None = None
    task_deadline_utc: datetime | None = None
    wall_clock_now: datetime | None = None
    merged_max_tcp_velocity: float | None = None
    merged_max_joint_velocity: float | None = None
    merged_max_acceleration: float | None = None
    merged_minimum_safe_height: float | None = None
    merged_max_reach_m: float | None = None
    merged_obstacle_safety_distance: float | None = None
    merged_carry_safety_margin: float | None = None
    merged_scene_staleness_ms: int | None = None
    merged_telemetry_staleness_ms: int | None = None
    merged_watchdog_timeout_ms: int | None = None
    absolute_max_tcp_velocity: float | None = None
    absolute_max_joint_velocity: float | None = None
    absolute_max_acceleration: float | None = None


@dataclass(frozen=True)
class SafetyRuleResult:
    rule_id: str
    decision: SafetyDecision
    reason_code: str
    message: str
    measured_value: float | None = None
    limit_value: float | None = None
    limited_parameters: dict[str, Any] | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SafetyEvaluationResult:
    allowed: bool
    decision: SafetyDecision
    evaluated_rules: list[SafetyRuleResult]
    limiting_rule: SafetyRuleResult | None = None
    limited_parameters: dict[str, Any] | None = None
    original_parameters: dict[str, Any] | None = None
    error: StructuredError | None = None

    @property
    def is_reject(self) -> bool:
        return self.decision in {
            SafetyDecision.REJECT,
            SafetyDecision.EMERGENCY_STOP,
            SafetyDecision.PAUSE,
            SafetyDecision.REQUEST_CORRECTION,
        }


@dataclass(frozen=True)
class StopExecutionResult:
    success: bool
    method_used: str | None = None
    stop_action_result: Any | None = None
    estop_action_result: Any | None = None
    verified_stopped: bool = False
    verified_estop: bool = False
    error: StructuredError | None = None


@dataclass(frozen=True)
class SafetyAuditEvent:
    event_type: str
    task_id: str
    plan_version: int
    command_seq: int
    step_id: str
    rule_id: str
    decision: str
    reason_code: str
    policy_version: str
    policy_hash: str
    measured_value: float | None = None
    limit_value: float | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    details: dict[str, object] = field(default_factory=dict)
