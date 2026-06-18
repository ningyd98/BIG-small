"""结构化数据模型，作为 API、测试和服务之间的稳定契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from math import hypot, isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cloud_edge_robot_arm.errors import StructuredError


def utc_now() -> datetime:
    """返回 UTC 当前时间，作为契约模型默认时间源。"""
    return datetime.now(UTC)


class ControlMode(StrEnum):
    """云边协同控制模式枚举，区分周期监督、事件自治和自动选择。"""

    PERIODIC_CLOUD_SUPERVISION = "PERIODIC_CLOUD_SUPERVISION"
    EVENT_TRIGGERED_EDGE_AUTONOMY = "EVENT_TRIGGERED_EDGE_AUTONOMY"
    AUTO = "AUTO"


class CloudDecision(StrEnum):
    """云端监督决策枚举，描述保持、更新、暂停、观察或中止。"""

    KEEP = "KEEP"
    UPDATE = "UPDATE"
    PAUSE = "PAUSE"
    REQUEST_OBSERVATION = "REQUEST_OBSERVATION"
    ABORT = "ABORT"


class EventSeverity(StrEnum):
    """边缘事件严重级别，用于排序告警和触发安全处理。"""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EdgeEventType(StrEnum):
    """边缘运行事件类型，覆盖任务、场景、安全、网络和重规划信号。"""

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
    """本地恢复动作枚举，约束失败后允许的高层恢复策略。"""

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
    """重规划范围枚举，描述从当前步骤到整条计划的重规划粒度。"""

    CURRENT_STEP = "CURRENT_STEP"
    FAILED_STEP_AND_REMAINING = "FAILED_STEP_AND_REMAINING"
    REMAINING_STEPS = "REMAINING_STEPS"
    FULL_PLAN_REQUIRED = "FULL_PLAN_REQUIRED"
    MORE_OBSERVATION_REQUIRED = "MORE_OBSERVATION_REQUIRED"
    NO_REPLAN_SAFETY_STOP = "NO_REPLAN_SAFETY_STOP"


class MessageStatus(StrEnum):
    """待发送消息状态，用于 outbox 重试和死信跟踪。"""

    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    RETRY_WAIT = "RETRY_WAIT"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class CompletionResult(StrEnum):
    """任务完成结果枚举，区分成功、恢复后成功、失败和安全停止。"""

    SUCCESS = "SUCCESS"
    SUCCESS_WITH_RECOVERY = "SUCCESS_WITH_RECOVERY"
    FAILED = "FAILED"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    CANCELLED = "CANCELLED"


class TaskState(StrEnum):
    """任务运行状态枚举，描述从创建到执行、恢复和终态的生命周期。"""

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
    """SafetyShield 决策枚举，表示允许、限速、暂停、拒绝或急停。"""

    ALLOW = "ALLOW"
    ALLOW_WITH_LIMITS = "ALLOW_WITH_LIMITS"
    PAUSE = "PAUSE"
    REQUEST_CORRECTION = "REQUEST_CORRECTION"
    REJECT = "REJECT"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class SkillName(StrEnum):
    """高层技能名称 allowlist，不包含任意 shell、轨迹或低层电机命令。"""

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
    """可追踪消息基类，统一任务 ID、计划版本、命令序号和时间戳。"""

    model_config = ConfigDict(use_enum_values=False)

    task_id: str = Field(min_length=1)
    plan_version: int = Field(ge=0)
    command_seq: int = Field(ge=1)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        """强制消息时间戳带时区，避免跨节点排序歧义。"""
        if value.tzinfo is None:
            raise ValueError("timestamp must include timezone information")
        return value


class Pose(BaseModel):
    """简化 TCP 位姿坐标，只记录有限三维位置。"""

    x: float
    y: float
    z: float

    @field_validator("x", "y", "z")
    @classmethod
    def coordinates_must_be_finite(cls, value: float) -> float:
        """拒绝 NaN 或无穷坐标，避免污染安全和距离计算。"""
        if not isfinite(value):
            raise ValueError("pose coordinates must be finite")
        return value

    def distance_xy_to(self, other: Pose) -> float:
        """计算与另一位姿在 XY 平面上的欧氏距离。"""
        return hypot(self.x - other.x, self.y - other.y)


class RobotState(BaseModel):
    """机器人状态快照，供仿真、测试和安全判断传递高层状态。"""

    tcp_pose: Pose = Field(default_factory=lambda: Pose(x=0.0, y=0.0, z=0.18))
    gripper_open: bool = True
    holding_object_id: str | None = None
    connected: bool = False
    stopped: bool = False
    estop_engaged: bool = False
    collision_detected: bool = False


class TaskTarget(BaseModel):
    """任务目标描述，绑定对象 ID、对象类别和目标区域。"""

    object_id: str = Field(min_length=1)
    object_class: str = Field(min_length=1)
    target_region_id: str = Field(min_length=1)


class TaskStep(BaseModel):
    """任务步骤契约，描述高层技能、参数模板、时限和成功条件。"""

    step_id: str = Field(min_length=1)
    skill: SkillName
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_duration_ms: int = Field(gt=0)
    timeout_ms: int = Field(gt=0)
    retry_limit: int = Field(ge=0)
    preconditions: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)


class SafetyConstraints(BaseModel):
    """任务级安全约束，限定速度、高度、工作区和碰撞检查要求。"""

    max_joint_velocity: float = Field(gt=0)
    max_tcp_velocity: float = Field(gt=0)
    minimum_safe_height: float = Field(ge=0)
    workspace_id: str = Field(min_length=1)
    collision_check_required: bool = True


class FailurePolicy(BaseModel):
    """失败处理策略，定义超时、安全拒绝和断网时的高层处置。"""

    local_retry_limit: int = Field(ge=0)
    on_timeout: str = Field(min_length=1)
    on_safety_rejection: str = Field(min_length=1)
    on_network_loss: str = Field(min_length=1)


class TaskContract(TraceableMessage):
    """云端下发给边缘的任务契约，封装步骤、安全约束和完成条件。"""

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
        """强制契约有效期时间带时区，保证 TTL 判断一致。"""
        if value.tzinfo is None:
            raise ValueError("contract datetimes must include timezone information")
        return value

    @model_validator(mode="after")
    def validate_contract_consistency(self) -> TaskContract:
        """校验契约内部一致性：有效期、步骤 ID 唯一性和当前步骤引用。"""
        if self.valid_until <= self.issued_at:
            raise ValueError("valid_until must be later than issued_at")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("step_id values must be unique")
        if self.current_step_id is not None and self.current_step_id not in set(step_ids):
            raise ValueError("current_step_id must reference a declared step")
        return self


class Telemetry(TraceableMessage):
    """边缘遥测消息，报告任务状态、场景版本、机器人和网络诊断。"""

    control_mode: ControlMode
    task_state: TaskState
    scene_version: int = Field(ge=0)
    current_step_id: str | None
    completed_step_ids: list[str] = Field(default_factory=list)
    robot_state: dict[str, Any] = Field(default_factory=dict)
    network_state: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class CloudCommand(TraceableMessage):
    """云端监督命令，可能携带任务契约更新和命令有效期。"""

    decision: CloudDecision
    command_ttl_ms: int = Field(gt=0)
    valid_until: datetime
    reason: str = Field(min_length=1)
    contract_update: TaskContract | None = None

    @field_validator("valid_until")
    @classmethod
    def valid_until_must_be_timezone_aware(cls, value: datetime) -> datetime:
        """强制云端命令有效期带时区，避免过期判断错误。"""
        if value.tzinfo is None:
            raise ValueError("valid_until must include timezone information")
        return value


class CommandAckStatus(StrEnum):
    """命令接收确认状态，细分过期、重复、乱序和语义拒绝原因。"""

    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_LIMITS = "ACCEPTED_WITH_LIMITS"
    REJECTED_EXPIRED = "REJECTED_EXPIRED"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
    REJECTED_OUT_OF_ORDER = "REJECTED_OUT_OF_ORDER"
    REJECTED_PLAN_VERSION_MISMATCH = "REJECTED_PLAN_VERSION_MISMATCH"
    REJECTED_CHECKPOINT_MISMATCH = "REJECTED_CHECKPOINT_MISMATCH"
    REJECTED_SCENE_MISMATCH = "REJECTED_SCENE_MISMATCH"
    REJECTED_TASK_MISMATCH = "REJECTED_TASK_MISMATCH"
    REJECTED_ROBOT_MISMATCH = "REJECTED_ROBOT_MISMATCH"
    REJECTED_COMPLETED_STEP_MODIFIED = "REJECTED_COMPLETED_STEP_MODIFIED"
    REJECTED_SCHEMA_INVALID = "REJECTED_SCHEMA_INVALID"
    REJECTED_SEMANTIC_INVALID = "REJECTED_SEMANTIC_INVALID"
    REJECTED_SAFETY_CONFLICT = "REJECTED_SAFETY_CONFLICT"


class ActiveContractStatus(StrEnum):
    """活动契约状态，描述契约是否仍有效、被替换、完成或安全停止。"""

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    COMPLETED = "COMPLETED"
    SAFETY_STOPPED = "SAFETY_STOPPED"


class CheckpointExecutionState(StrEnum):
    """执行检查点状态，记录步骤执行、重试、重规划和恢复阶段。"""

    STARTED = "STARTED"
    STEP_STARTED = "STEP_STARTED"
    STEP_SUCCEEDED = "STEP_SUCCEEDED"
    STEP_FAILED = "STEP_FAILED"
    LOCAL_RETRY_STARTED = "LOCAL_RETRY_STARTED"
    LOCAL_RETRY_FAILED = "LOCAL_RETRY_FAILED"
    WAITING_CLOUD_REPLAN = "WAITING_CLOUD_REPLAN"
    REPLAN_RECEIVED = "REPLAN_RECEIVED"
    READY_TO_RESUME = "READY_TO_RESUME"
    RESUMING = "RESUMING"
    COMPLETED = "COMPLETED"
    SAFETY_STOPPED = "SAFETY_STOPPED"


class ReplanApplyStatus(StrEnum):
    """重规划应用状态，描述应用、拒绝、等待观察、安全停止或版本冲突。"""

    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    WAITING_FOR_NEW_OBSERVATION = "WAITING_FOR_NEW_OBSERVATION"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    VERSION_CONFLICT = "VERSION_CONFLICT"


class RiskLevel(StrEnum):
    """风险等级枚举，包含证据不足这一非数值终态。"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AutoModeDecisionType(StrEnum):
    """AUTO 模式决策动作，约束保持、切换、暂停、安全停止或请求观察。"""

    KEEP_CURRENT_MODE = "KEEP_CURRENT_MODE"
    SWITCH_TO_PERIODIC_CLOUD_SUPERVISION = "SWITCH_TO_PERIODIC_CLOUD_SUPERVISION"
    SWITCH_TO_EVENT_TRIGGERED_EDGE_AUTONOMY = "SWITCH_TO_EVENT_TRIGGERED_EDGE_AUTONOMY"
    PAUSE_TASK = "PAUSE_TASK"
    SAFE_STOP = "SAFE_STOP"
    REQUEST_MORE_OBSERVATION = "REQUEST_MORE_OBSERVATION"


class AutoModeTransitionStatus(StrEnum):
    """AUTO 模式切换事务状态，用于 prepare/commit/abort 审计。"""

    PREPARED = "PREPARED"
    COMMITTED = "COMMITTED"
    ABORTED = "ABORTED"
    ROLLED_BACK = "ROLLED_BACK"


class AutoModeStatus(BaseModel):
    """任务当前 AUTO 模式状态，记录版本、切换次数和最近决策。"""

    task_id: str = Field(min_length=1)
    current_mode: ControlMode
    mode_version: int = Field(ge=0)
    switch_count: int = Field(default=0, ge=0)
    last_switch_at: datetime | None = None
    last_decision_id: str = Field(default="")
    policy_version: str = Field(default="")
    updated_at: datetime = Field(default_factory=utc_now)


class RiskComponentScores(BaseModel):
    """风险分项分数，分别记录任务、场景、感知、网络、执行和安全风险。"""

    task_risk: float = Field(ge=0.0, le=100.0)
    scene_dynamics_risk: float = Field(ge=0.0, le=100.0)
    perception_risk: float = Field(ge=0.0, le=100.0)
    network_risk: float = Field(ge=0.0, le=100.0)
    execution_risk: float = Field(ge=0.0, le=100.0)
    safety_risk: float = Field(ge=0.0, le=100.0)


class RiskSnapshot(BaseModel):
    """风险评估快照，包含总分、等级、freshness、缺失输入和原因码。"""

    snapshot_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    component_scores: RiskComponentScores
    total_score: float = Field(ge=0.0, le=100.0)
    risk_level: RiskLevel
    data_freshness: dict[str, int] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    policy_version: str = Field(min_length=1)
    created_at: datetime
    expires_at: datetime
    input_hash: str = Field(min_length=1)


class AutoModeDecision(BaseModel):
    """AUTO 模式单次决策记录，绑定风险输入哈希和策略版本。"""

    decision_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    current_mode: ControlMode
    selected_mode: ControlMode | None = None
    action: AutoModeDecisionType
    risk_score: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)
    decision_version: int = Field(default=1, ge=1)
    created_at: datetime
    valid_until: datetime
    input_snapshot_hash: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)


class AutoModeTransition(BaseModel):
    """AUTO 模式切换记录，保存幂等键、版本变更和事务时间。"""

    transition_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    from_mode: ControlMode
    to_mode: ControlMode
    status: AutoModeTransitionStatus
    expected_mode_version: int = Field(ge=0)
    new_mode_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1)
    decision_id: str = Field(default="")
    prepared_at: datetime
    committed_at: datetime | None = None
    aborted_at: datetime | None = None
    reason: str = Field(default="")
    payload_hash: str = Field(default="")


class CommandAck(TraceableMessage):
    """边缘对云端命令的确认消息，记录接受状态和拒绝细节。"""

    accepted: bool
    status: str = Field(min_length=1)
    error: StructuredError | None = None
    request_id: str = Field(default="")
    checkpoint_id: str = Field(default="")
    correlation_id: str = Field(default="")
    policy_version: str = Field(default="")
    policy_hash: str = Field(default="")
    details: dict[str, Any] = Field(default_factory=dict)


class ActiveTaskContractRecord(BaseModel):
    """活动任务契约持久化记录，绑定计划、机器人、版本和契约哈希。"""

    task_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    plan_version: int = Field(ge=0)
    command_seq: int = Field(ge=1)
    scene_version: int = Field(ge=0)
    contract: TaskContract
    status: str = Field(default=ActiveContractStatus.ACTIVE.value)
    based_on_plan_version: int | None = Field(default=None, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    activated_at: datetime = Field(default_factory=utc_now)
    superseded_at: datetime | None = None
    correlation_id: str = Field(default="")
    contract_hash: str = Field(default="")


class RetryBudgetSnapshot(BaseModel):
    """重试预算快照，记录任务、步骤、技能和事件维度的剩余次数。"""

    task_retry_count: int = Field(default=0, ge=0)
    step_retry_counts: dict[str, int] = Field(default_factory=dict)
    skill_retry_counts: dict[str, int] = Field(default_factory=dict)
    event_retry_counts: dict[str, int] = Field(default_factory=dict)
    remaining_retries: int = Field(default=0, ge=0)


class ExecutionCheckpoint(BaseModel):
    """执行检查点，保存可恢复任务状态、步骤进度、机器人状态和重试预算。"""

    checkpoint_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    plan_version: int = Field(ge=0)
    command_seq: int = Field(ge=1)
    robot_id: str = Field(min_length=1)
    current_step_id: str = Field(default="")
    current_step_index: int = Field(default=0, ge=0)
    failed_step_id: str = Field(default="")
    last_successful_step_id: str = Field(default="")
    completed_step_ids: list[str] = Field(default_factory=list)
    pending_step_ids: list[str] = Field(default_factory=list)
    step_attempts: dict[str, int] = Field(default_factory=dict)
    retry_budget_snapshot: RetryBudgetSnapshot = Field(default_factory=RetryBudgetSnapshot)
    robot_state: dict[str, Any] = Field(default_factory=dict)
    target_state: dict[str, Any] = Field(default_factory=dict)
    scene_version: int = Field(default=0, ge=0)
    scene_timestamp: datetime | None = None
    safety_state: dict[str, Any] = Field(default_factory=dict)
    execution_state: str = Field(default=CheckpointExecutionState.STARTED.value)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    correlation_id: str = Field(default="")
    checkpoint_hash: str = Field(default="")


class ReplanApplyRecord(BaseModel):
    """重规划应用记录，保存旧新版本、应用步骤和确认状态。"""

    apply_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    previous_plan_version: int = Field(ge=0)
    previous_command_seq: int = Field(ge=1)
    new_plan_version: int = Field(ge=0)
    new_command_seq: int = Field(ge=1)
    checkpoint_id: str = Field(default="")
    status: str = Field(default=ReplanApplyStatus.APPLIED.value)
    reason: str = Field(default="")
    completed_step_ids: list[str] = Field(default_factory=list)
    applied_step_ids: list[str] = Field(default_factory=list)
    ack_status: str = Field(default="")
    created_at: datetime = Field(default_factory=utc_now)
    correlation_id: str = Field(default="")
    apply_hash: str = Field(default="")


class EdgeEvent(TraceableMessage):
    """边缘事件契约，携带故障、恢复、安全和重规划触发所需上下文。"""

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
        """强制事件时间带时区，保证事件流和 replay 顺序稳定。"""
        if value is not None and value.tzinfo is None:
            raise ValueError("event datetimes must include timezone information")
        return value


class FailureSummary(TraceableMessage):
    """失败摘要，向云端重规划提供已完成步骤、失败原因和安全恢复上下文。"""

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
        """强制失败摘要生成时间带时区。"""
        if value.tzinfo is None:
            raise ValueError("generated_at must include timezone information")
        return value


class CompletionSummary(TraceableMessage):
    """任务完成摘要，记录完成步骤、最终状态、重试次数和结果哈希。"""

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
    """本地恢复决策，描述允许的恢复动作、预算变化和安全复检要求。"""

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
    """本地恢复执行结果，记录成功、错误、预算余量和耗时。"""

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
    """恢复预算模型，限制任务、步骤、技能和事件级重试次数。"""

    budget_id: str = Field(default="")
    task_id: str = Field(min_length=1)
    per_step_retry_limit: int = Field(default=3, ge=0)
    per_skill_retry_limit: int = Field(default=5, ge=0)
    task_total_retry_limit: int = Field(default=10, ge=0)
    retry_count_used: int = Field(default=0, ge=0)
    task_retry_count: int = Field(default=0, ge=0)
    step_retry_counts: dict[str, int] = Field(default_factory=dict)
    skill_retry_counts: dict[str, int] = Field(default_factory=dict)
    event_retry_counts: dict[str, int] = Field(default_factory=dict)
    retry_cooldown_ms: int = Field(default=500, ge=0)
    retry_deadline: datetime | None = None
    retry_backoff_policy: str = Field(default="exponential")
    effective_retry_limit: int = Field(default=3, ge=0)
    remaining_retries: int = Field(default=3, ge=0)
    scene_version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class LocalReplanningRequest(BaseModel):
    """本地向云端发起的重规划请求，携带失败上下文和安全恢复状态。"""

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
    """云端重规划响应，返回新步骤、版本、校验错误和响应哈希。"""

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
    """Outbox 待发送消息，支持幂等键、重试次数和下一次重试时间。"""

    message_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    event_id: str | None = None
    summary_id: str | None = None
    request_id: str | None = None
    idempotency_key: str = Field(default="")
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
    """契约层技能模板定义，只描述高层参数 schema 和安全说明。"""

    skill: SkillName
    parameter_schema: dict[str, Any] = Field(default_factory=dict)
    default_parameters: dict[str, Any] = Field(default_factory=dict)
    safety_notes: list[str] = Field(default_factory=list)
    version: str = "1.0"


class ActionResult(BaseModel):
    """单个动作执行结果，记录时间、状态变化、错误和结构化细节。"""

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
        """兼容旧调用方，将 action_type 暴露为 skill 字段。"""
        return self.action_type

    @property
    def timestamp(self) -> datetime:
        """兼容旧调用方，将 finished_at 暴露为 timestamp。"""
        return self.finished_at


class SkillExecutionResult(TraceableMessage):
    """技能步骤执行结果，绑定步骤、技能、场景版本和错误详情。"""

    step_id: str
    skill: SkillName
    scene_version: int = Field(ge=0)
    success: bool
    error: StructuredError | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = Field(ge=0)
