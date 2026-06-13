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


class EventSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EdgeEventType(StrEnum):
    TASK_COMPLETED = "TASK_COMPLETED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_TIMEOUT = "STEP_TIMEOUT"
    TASK_TIMEOUT = "TASK_TIMEOUT"
    SKILL_EXECUTION_FAILED = "SKILL_EXECUTION_FAILED"
    GRASP_FAILED = "GRASP_FAILED"
    PLACE_FAILED = "PLACE_FAILED"
    VERIFY_FAILED = "VERIFY_FAILED"
    TARGET_MOVED = "TARGET_MOVED"
    TARGET_LOST = "TARGET_LOST"
    PATH_BLOCKED = "PATH_BLOCKED"
    SCENE_CHANGED = "SCENE_CHANGED"
    SCENE_CONFIDENCE_LOW = "SCENE_CONFIDENCE_LOW"
    SAFETY_REJECTED = "SAFETY_REJECTED"
    SAFETY_PAUSED = "SAFETY_PAUSED"
    EMERGENCY_STOP_TRIGGERED = "EMERGENCY_STOP_TRIGGERED"
    LOCAL_RETRY_STARTED = "LOCAL_RETRY_STARTED"
    LOCAL_RETRY_SUCCEEDED = "LOCAL_RETRY_SUCCEEDED"
    LOCAL_RETRY_FAILED = "LOCAL_RETRY_FAILED"
    LOCAL_RETRY_EXHAUSTED = "LOCAL_RETRY_EXHAUSTED"
    DEVICE_FAULT = "DEVICE_FAULT"
    TELEMETRY_STALE = "TELEMETRY_STALE"
    NETWORK_DEGRADED = "NETWORK_DEGRADED"
    NETWORK_LOST = "NETWORK_LOST"
    NETWORK_RECOVERED = "NETWORK_RECOVERED"
    PLAN_INVALIDATED = "PLAN_INVALIDATED"
    CLOUD_REPLAN_REQUESTED = "CLOUD_REPLAN_REQUESTED"
    CLOUD_REPLAN_RECEIVED = "CLOUD_REPLAN_RECEIVED"
    CLOUD_REPLAN_REJECTED = "CLOUD_REPLAN_REJECTED"
    TASK_FAILED = "TASK_FAILED"
    MANUAL_INTERRUPT = "MANUAL_INTERRUPT"


class RecoveryAction(StrEnum):
    RETRY_SAME_SKILL = "RETRY_SAME_SKILL"
    RETRY_WITH_LIMITS = "RETRY_WITH_LIMITS"
    REQUEST_NEW_OBSERVATION = "REQUEST_NEW_OBSERVATION"
    REPOSITION_AND_RETRY = "REPOSITION_AND_RETRY"
    SKIP_FORBIDDEN = "SKIP_FORBIDDEN"
    PAUSE_AND_REPORT = "PAUSE_AND_REPORT"
    STOP_AND_REPORT = "STOP_AND_REPORT"
    REQUEST_CLOUD_REPLAN = "REQUEST_CLOUD_REPLAN"
    MARK_TASK_FAILED = "MARK_TASK_FAILED"


class ReplanScope(StrEnum):
    CURRENT_STEP = "CURRENT_STEP"
    FAILED_STEP_AND_REMAINING = "FAILED_STEP_AND_REMAINING"
    REMAINING_STEPS = "REMAINING_STEPS"
    FULL_PLAN_REQUIRED = "FULL_PLAN_REQUIRED"
    MORE_OBSERVATION_REQUIRED = "MORE_OBSERVATION_REQUIRED"
    NO_REPLAN_SAFETY_STOP = "NO_REPLAN_SAFETY_STOP"


class MessageStatus(StrEnum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class CompletionResult(StrEnum):
    SUCCESS = "SUCCESS"
    SUCCESS_WITH_RECOVERY = "SUCCESS_WITH_RECOVERY"
    FAILED = "FAILED"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    CANCELLED = "CANCELLED"


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
    source: str = "edge"
    robot_id: str = Field(default="", min_length=0)
    plan_id: str = Field(default="", min_length=0)
    detected_at: datetime = Field(default_factory=utc_now)
    occurred_at: datetime = Field(default_factory=utc_now)
    edge_state_timestamp: datetime | None = None
    scene_version: int = Field(default=0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    retry_limit: int = Field(default=0, ge=0)
    local_recovery_allowed: bool = False
    requires_cloud_replan: bool = False
    requires_immediate_stop: bool = False
    reason_code: str = Field(default="")
    reason_detail: str = Field(default="")
    correlation_id: str = Field(default="")
    telemetry_snapshot: dict[str, Any] = Field(default_factory=dict)
    scene_snapshot_ref: str = Field(default="")
    safety_decision_ref: str = Field(default="")
    execution_result_ref: str = Field(default="")
    event_hash: str = Field(default="")

    @field_validator("detected_at", "occurred_at", "edge_state_timestamp")
    @classmethod
    def event_datetimes_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("event datetimes must include timezone information")
        return value


class FailureSummary(TraceableMessage):
    failure_event_id: str = Field(min_length=1)
    failed_step_id: str = Field(min_length=1)
    completed_step_ids: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    local_retry_count: int = Field(ge=0)
    current_scene_version: int = Field(default=0, ge=0)
    recovery_hint: str = Field(min_length=1)
    summary_id: str = Field(default="")
    robot_id: str = Field(default="")
    plan_id: str = Field(default="")
    failed_skill: SkillName | None = None
    last_successful_step_id: str = Field(default="")
    pending_step_ids: list[str] = Field(default_factory=list)
    failure_type: str = Field(default="")
    severity: str = Field(default="ERROR")
    confirmed_facts: dict[str, Any] = Field(default_factory=dict)
    diagnostic_findings: dict[str, Any] = Field(default_factory=dict)
    suspected_causes: list[str] = Field(default_factory=list)
    retry_history: list[dict[str, Any]] = Field(default_factory=list)
    retry_limit: int = Field(default=0, ge=0)
    execution_timeline: list[dict[str, Any]] = Field(default_factory=list)
    robot_state: dict[str, Any] = Field(default_factory=dict)
    target_state: dict[str, Any] = Field(default_factory=dict)
    obstacle_state: dict[str, Any] = Field(default_factory=dict)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    safety_decision: str = Field(default="")
    scene_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    network_state: dict[str, Any] = Field(default_factory=dict)
    requested_replan_scope: str = Field(default="FAILED_STEP_AND_REMAINING")
    safe_resume_state: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=utc_now)
    generator_version: str = Field(default="1.0")
    summary_hash: str = Field(default="")
    correlation_id: str = Field(default="")

    @field_validator("generated_at")
    @classmethod
    def generated_at_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generated_at must include timezone information")
        return value


class CompletionSummary(TraceableMessage):
    summary_id: str = Field(default="")
    task_id: str = Field(min_length=1)
    plan_id: str = Field(default="")
    final_plan_version: int = Field(ge=0)
    robot_id: str = Field(default="")
    completed_step_ids: list[str] = Field(default_factory=list)
    completion_criteria_results: dict[str, bool] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)
    total_duration_ms: int = Field(default=0)
    local_retry_count: int = Field(default=0, ge=0)
    cloud_replan_count: int = Field(default=0, ge=0)
    final_robot_state: dict[str, Any] = Field(default_factory=dict)
    final_target_state: dict[str, Any] = Field(default_factory=dict)
    final_safety_decision: str = Field(default="ALLOW")
    result: str = Field(default="SUCCESS")
    correlation_id: str = Field(default="")
    summary_hash: str = Field(default="")


class LocalRecoveryDecision(BaseModel):
    decision_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    action: RecoveryAction
    allowed: bool = False
    reason_code: str = Field(default="")
    retry_count_before: int = Field(default=0, ge=0)
    retry_count_after: int = Field(default=0, ge=0)
    retry_limit: int = Field(default=0, ge=0)
    delay_ms: int = Field(default=0, ge=0)
    parameter_adjustments: dict[str, Any] = Field(default_factory=dict)
    requires_safety_recheck: bool = True
    requires_new_observation: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    policy_version: str = Field(default="1.0")
    policy_hash: str = Field(default="")


class LocalRecoveryResult(BaseModel):
    result_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    success: bool = False
    error_code: str = Field(default="")
    budget_after: int = Field(default=0, ge=0)
    safety_decision: str = Field(default="")
    details: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)
    elapsed_ms: int = Field(default=0, ge=0)


class RecoveryBudget(BaseModel):
    budget_id: str = Field(default="")
    task_id: str = Field(min_length=1)
    per_step_retry_limit: int = Field(default=3, ge=0)
    per_skill_retry_limit: int = Field(default=5, ge=0)
    task_total_retry_limit: int = Field(default=10, ge=0)
    retry_count_used: int = Field(default=0, ge=0)
    retry_cooldown_ms: int = Field(default=500, ge=0)
    retry_deadline: datetime | None = None
    retry_backoff_policy: str = Field(default="exponential")
    effective_retry_limit: int = Field(default=3, ge=0)
    remaining_retries: int = Field(default=3, ge=0)
    scene_version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class LocalReplanningRequest(BaseModel):
    request_id: str = Field(min_length=1)
    trigger_event_id: str = Field(min_length=1)
    failure_summary_id: str = Field(default="")
    robot_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    plan_id: str = Field(default="")
    current_plan_version: int = Field(ge=0)
    current_command_seq: int = Field(ge=1)
    requested_replan_scope: str = Field(default="FAILED_STEP_AND_REMAINING")
    completed_step_ids: list[str] = Field(default_factory=list)
    failed_step_id: str = Field(default="")
    last_successful_step_id: str = Field(default="")
    current_robot_state: dict[str, Any] = Field(default_factory=dict)
    current_target_state: dict[str, Any] = Field(default_factory=dict)
    current_obstacle_state: dict[str, Any] = Field(default_factory=dict)
    current_scene_version: int = Field(default=0, ge=0)
    scene_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    safe_resume_state: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime = Field(default_factory=utc_now)
    correlation_id: str = Field(default="")
    idempotency_key: str = Field(default="")


class LocalReplanningResponse(BaseModel):
    request_id: str = Field(min_length=1)
    outcome: str = Field(default="REPLANNED")
    reason: str = Field(default="")
    new_steps: list[TaskStep] = Field(default_factory=list)
    new_plan_version: int = Field(ge=0)
    new_command_seq: int = Field(ge=1)
    validation_errors: list[str] = Field(default_factory=list)
    planner_name: str = Field(default="")
    prompt_version: str = Field(default="")
    created_at: datetime = Field(default_factory=utc_now)
    correlation_id: str = Field(default="")
    response_hash: str = Field(default="")


class PendingMessage(BaseModel):
    message_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    event_id: str | None = None
    summary_id: str | None = None
    request_id: str | None = None
    message_type: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: MessageStatus = MessageStatus.PENDING
    created_at: datetime = Field(default_factory=utc_now)
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=5, ge=0)
    last_error: str | None = None
    next_retry_at: datetime | None = None
    backoff_base_ms: int = Field(default=1000, ge=0)


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
