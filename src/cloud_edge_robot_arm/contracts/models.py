from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from math import hypot, isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cloud_edge_robot_arm.errors import StructuredError


def utc_now() -> datetime:
    return datetime.now(UTC)


class ControlMode(StrEnum):
    PERIODIC_CLOUD_SUPERVISION = "PERIODIC_CLOUD_SUPERVISION"
    EVENT_TRIGGERED_EDGE_AUTONOMY = "EVENT_TRIGGERED_EDGE_AUTONOMY"
    AUTO = "AUTO"


class CloudDecision(StrEnum):
    KEEP = "KEEP"
    UPDATE = "UPDATE"
    PAUSE = "PAUSE"
    REQUEST_OBSERVATION = "REQUEST_OBSERVATION"
    ABORT = "ABORT"


class EdgeEventType(StrEnum):
    TASK_COMPLETED = "TASK_COMPLETED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_TIMEOUT = "STEP_TIMEOUT"
    TASK_TIMEOUT = "TASK_TIMEOUT"
    GRASP_FAILED = "GRASP_FAILED"
    TARGET_MOVED = "TARGET_MOVED"
    TARGET_LOST = "TARGET_LOST"
    PATH_BLOCKED = "PATH_BLOCKED"
    SAFETY_REJECTED = "SAFETY_REJECTED"
    LOCAL_RETRY_EXHAUSTED = "LOCAL_RETRY_EXHAUSTED"
    NETWORK_RECOVERED = "NETWORK_RECOVERED"
    MANUAL_INTERRUPT = "MANUAL_INTERRUPT"


class TaskState(StrEnum):
    CREATED = "CREATED"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    VALIDATING = "VALIDATING"
    READY = "READY"
    EXECUTING = "EXECUTING"
    WAITING_CLOUD_UPDATE = "WAITING_CLOUD_UPDATE"
    LOCAL_RECOVERY = "LOCAL_RECOVERY"
    PAUSED = "PAUSED"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class SafetyDecision(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_WITH_LIMITS = "ALLOW_WITH_LIMITS"
    PAUSE = "PAUSE"
    REQUEST_CORRECTION = "REQUEST_CORRECTION"
    REJECT = "REJECT"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class SkillName(StrEnum):
    HOME = "HOME"
    OBSERVE = "OBSERVE"
    LOCATE_OBJECT = "LOCATE_OBJECT"
    MOVE_ABOVE = "MOVE_ABOVE"
    APPROACH = "APPROACH"
    GRASP = "GRASP"
    LIFT = "LIFT"
    MOVE_TO_REGION = "MOVE_TO_REGION"
    PLACE = "PLACE"
    RELEASE = "RELEASE"
    RETREAT = "RETREAT"
    VERIFY_RESULT = "VERIFY_RESULT"
    SAFE_STOP = "SAFE_STOP"


class TraceableMessage(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    task_id: str = Field(min_length=1)
    plan_version: int = Field(ge=0)
    command_seq: int = Field(ge=1)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include timezone information")
        return value


class Pose(BaseModel):
    x: float
    y: float
    z: float

    @field_validator("x", "y", "z")
    @classmethod
    def coordinates_must_be_finite(cls, value: float) -> float:
        if not isfinite(value):
            raise ValueError("pose coordinates must be finite")
        return value

    def distance_xy_to(self, other: Pose) -> float:
        return hypot(self.x - other.x, self.y - other.y)


class RobotState(BaseModel):
    tcp_pose: Pose = Field(default_factory=lambda: Pose(x=0.0, y=0.0, z=0.18))
    gripper_open: bool = True
    holding_object_id: str | None = None
    connected: bool = False
    stopped: bool = False
    estop_engaged: bool = False
    collision_detected: bool = False


class TaskTarget(BaseModel):
    object_id: str = Field(min_length=1)
    object_class: str = Field(min_length=1)
    target_region_id: str = Field(min_length=1)


class TaskStep(BaseModel):
    step_id: str = Field(min_length=1)
    skill: SkillName
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_duration_ms: int = Field(gt=0)
    timeout_ms: int = Field(gt=0)
    retry_limit: int = Field(ge=0)
    preconditions: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)


class SafetyConstraints(BaseModel):
    max_joint_velocity: float = Field(gt=0)
    max_tcp_velocity: float = Field(gt=0)
    minimum_safe_height: float = Field(ge=0)
    workspace_id: str = Field(min_length=1)
    collision_check_required: bool = True


class FailurePolicy(BaseModel):
    local_retry_limit: int = Field(ge=0)
    on_timeout: str = Field(min_length=1)
    on_safety_rejection: str = Field(min_length=1)
    on_network_loss: str = Field(min_length=1)


class TaskContract(TraceableMessage):
    control_mode: ControlMode
    issued_at: datetime
    valid_until: datetime
    user_instruction: str = Field(min_length=1)
    scene_version: int = Field(ge=0)
    expected_scene_version: int = Field(ge=0)
    task_target: TaskTarget
    current_step_id: str | None = None
    steps: list[TaskStep] = Field(min_length=1)
    safety_constraints: SafetyConstraints
    failure_policy: FailurePolicy
    completion_criteria: list[str] = Field(min_length=1)
    supervision_period_ms: int | None = Field(default=None, gt=0)
    command_ttl_ms: int | None = Field(default=None, gt=0)
    previous_command_seq: int | None = Field(default=None, ge=0)

    @field_validator("issued_at", "valid_until")
    @classmethod
    def datetimes_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("contract datetimes must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_contract_consistency(self) -> TaskContract:
        if self.valid_until <= self.issued_at:
            raise ValueError("valid_until must be later than issued_at")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("step_id values must be unique")
        if self.current_step_id is not None and self.current_step_id not in set(step_ids):
            raise ValueError("current_step_id must reference a declared step")
        return self


class Telemetry(TraceableMessage):
    control_mode: ControlMode
    task_state: TaskState
    scene_version: int = Field(ge=0)
    current_step_id: str | None
    completed_step_ids: list[str] = Field(default_factory=list)
    robot_state: dict[str, Any] = Field(default_factory=dict)
    network_state: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class CloudCommand(TraceableMessage):
    decision: CloudDecision
    command_ttl_ms: int = Field(gt=0)
    valid_until: datetime
    reason: str = Field(min_length=1)
    contract_update: TaskContract | None = None

    @field_validator("valid_until")
    @classmethod
    def valid_until_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("valid_until must include timezone information")
        return value


class CommandAck(TraceableMessage):
    accepted: bool
    status: str = Field(min_length=1)
    error: StructuredError | None = None


class EdgeEvent(TraceableMessage):
    event_id: str = Field(min_length=1)
    event_type: EdgeEventType
    step_id: str | None = None
    severity: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class FailureSummary(TraceableMessage):
    failure_event_id: str = Field(min_length=1)
    failed_step_id: str = Field(min_length=1)
    completed_step_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    local_retry_count: int = Field(ge=0)
    current_scene_version: int = Field(ge=0)
    recovery_hint: str = Field(min_length=1)


class SkillTemplate(BaseModel):
    skill: SkillName
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    default_parameters: dict[str, Any] = Field(default_factory=dict)
    safety_notes: list[str] = Field(default_factory=list)
    version: str = "1.0"


class ActionResult(BaseModel):
    success: bool
    action_id: str
    action_type: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int = Field(ge=0)
    error_code: str | None = None
    error_message: str | None = None
    state_before: dict[str, Any] = Field(default_factory=dict)
    state_after: dict[str, Any] = Field(default_factory=dict)
    error: StructuredError | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def skill(self) -> str:
        return self.action_type

    @property
    def timestamp(self) -> datetime:
        return self.finished_at


class SkillExecutionResult(TraceableMessage):
    step_id: str
    skill: SkillName
    scene_version: int = Field(ge=0)
    success: bool
    error: StructuredError | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = Field(ge=0)
