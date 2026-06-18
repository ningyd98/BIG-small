"""云端规划 API 的 Pydantic 请求/响应模型。

这些 schema 是 HTTP 边界的结构化契约；字段校验应阻止任意 shell、路径或未授权
控制参数穿透到规划与执行层。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from cloud_edge_robot_arm.cloud.planning.models import (
    RobotCapabilities,
    SafetyPolicyReference,
    SceneSummary,
)
from cloud_edge_robot_arm.cloud.supervision.models import (
    EdgeStatusSnapshot,
    SupervisionConfig,
    SupervisoryDecision,
)
from cloud_edge_robot_arm.contracts import AutoModeDecision, AutoModeTransition, RiskSnapshot
from cloud_edge_robot_arm.risk.models import RiskSnapshotInput
from cloud_edge_robot_arm.skill_cache.models import (
    SkillCacheKey,
    SkillExecutionRecord,
    SkillStatistics,
    SkillTemplate,
)

# ── Health ───────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


# ── Capabilities ─────────────────────────────────────────────────────────────


class CapabilitiesResponse(BaseModel):
    supported_skills: list[str]
    supported_control_modes: list[str]
    planner_name: str
    model_name: str


# ── TaskContract Schema ──────────────────────────────────────────────────────


class TaskContractSchemaResponse(BaseModel):
    task_contract_schema: dict[str, Any]
    version: str


# ── Planning Request ─────────────────────────────────────────────────────────


class PlanningRequest(BaseModel):
    request_id: str = Field(min_length=1)
    user_instruction: str = Field(min_length=1)
    control_mode: str = Field(
        default="EVENT_TRIGGERED_EDGE_AUTONOMY",
        pattern=r"^(PERIODIC_CLOUD_SUPERVISION|EVENT_TRIGGERED_EDGE_AUTONOMY)$",
    )
    scene: SceneSummary
    capabilities: RobotCapabilities = Field(default_factory=lambda: RobotCapabilities())
    safety_policy: SafetyPolicyReference | None = None


# ── Planning Response ────────────────────────────────────────────────────────


class PlanningResponse(BaseModel):
    request_id: str
    outcome: str
    reason: str | None = None
    contract: dict[str, Any] | None = None
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    validation_warnings: list[dict[str, Any]] = Field(default_factory=list)
    attempt_count: int = 0
    created_at: str


# ── Dispatch ─────────────────────────────────────────────────────────────────


class DispatchRequest(BaseModel):
    """Empty dispatch command body."""


class DispatchResponse(BaseModel):
    request_id: str
    task_id: str
    dispatched: bool
    edge_accepted: bool | None = None
    edge_reason: str | None = None


# ── Supervision ──────────────────────────────────────────────────────────────


class SupervisionCapabilitiesResponse(BaseModel):
    supported_decisions: list[str]
    allowed_periods_ms: list[int]
    configured_period_ms: int
    command_ttl_ms: int


class RobotStatusIngestResponse(BaseModel):
    accepted: bool
    robot_id: str
    task_id: str
    scene_version: int


class SupervisionDecisionResponse(BaseModel):
    decision: SupervisoryDecision


class SupervisionDecisionListResponse(BaseModel):
    decisions: list[SupervisoryDecision] = Field(default_factory=list)


class SupervisionStatusResponse(BaseModel):
    task_id: str
    running: bool
    last_plan_version: int
    last_command_seq: int


class SupervisionUnavailableResponse(BaseModel):
    error: str = "supervision_unavailable"


class SupervisionStartRequest(BaseModel):
    config: SupervisionConfig | None = None


class EdgeStatusSnapshotRequest(EdgeStatusSnapshot):
    """Request body alias for persisted edge status snapshots."""


# ── Phase 6: Event-Triggered Edge Autonomy ──────────────────────────────────


class EventControlCapabilitiesResponse(BaseModel):
    mode: str = "EVENT_TRIGGERED_EDGE_AUTONOMY"
    supported_event_types: list[str] = Field(default_factory=list)
    supported_recovery_actions: list[str] = Field(default_factory=list)
    supported_replan_scopes: list[str] = Field(default_factory=list)
    max_local_retries: int = 3
    configured: bool = True


# ── Phase 7: Skill Cache, Risk, AUTO Mode ───────────────────────────────────


class AutoModeCapabilitiesResponse(BaseModel):
    configured: bool
    auto_mode_enabled: bool
    supported_control_modes: list[str] = Field(default_factory=list)
    supported_decisions: list[str] = Field(default_factory=list)
    policy_version: str = ""


class RiskEvaluateRequest(RiskSnapshotInput):
    """Request body for deterministic risk evaluation."""


class RiskSnapshotResponse(RiskSnapshot):
    """Response body for persisted risk snapshots."""


class AutoModeDecisionRequest(BaseModel):
    cache_key: SkillCacheKey | None = None
    active_contract_complete: bool
    checkpoint_persisted: bool
    event_autonomy_ready: bool
    supervision_available: bool
    atomic_step_active: bool = False


class AutoModeDecisionResponse(AutoModeDecision):
    """Response body for AUTO selector decisions."""


class ModeTransitionCreateRequest(BaseModel):
    from_mode: str = Field(min_length=1)
    to_mode: str = Field(min_length=1)
    expected_mode_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ModeTransitionResponse(AutoModeTransition):
    """Response body for mode transition lifecycle records."""


class SkillTemplateRequest(SkillTemplate):
    """Skill cache template creation body."""


class SkillTemplateResponse(SkillTemplate):
    """Skill cache template response body."""


class SkillTemplateListResponse(BaseModel):
    templates: list[SkillTemplateResponse] = Field(default_factory=list)


class SkillExecutionRecordRequest(SkillExecutionRecord):
    """Skill execution audit record body."""


class SkillStatisticsResponse(SkillStatistics):
    """Skill cache statistics response body."""


class EdgeEventRequest(BaseModel):
    event_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    severity: str = Field(default="ERROR", min_length=1)
    step_id: str | None = None
    reason_code: str = ""
    reason_detail: str = ""
    robot_id: str = ""
    plan_id: str = ""
    plan_version: int = Field(default=0, ge=0)
    command_seq: int = Field(default=0, ge=0)
    scene_version: int = Field(default=0, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


class EdgeEventResponse(BaseModel):
    event_id: str
    task_id: str
    event_type: str
    severity: str
    step_id: str | None = None
    reason_code: str = ""
    reason_detail: str = ""
    detected_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class EdgeEventListResponse(BaseModel):
    task_id: str
    events: list[EdgeEventResponse] = Field(default_factory=list)


class FailureSummaryRequest(BaseModel):
    summary_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    failure_event_id: str = Field(min_length=1)
    failed_step_id: str = Field(min_length=1)
    completed_step_ids: list[str] = Field(default_factory=list)
    failure_type: str = ""
    severity: str = "ERROR"
    reason: str = Field(min_length=1)
    recovery_hint: str = Field(default="request_cloud_replan", min_length=1)
    local_retry_count: int = Field(default=0, ge=0)
    retry_limit: int = Field(default=0, ge=0)
    requested_replan_scope: str = "FAILED_STEP_AND_REMAINING"
    plan_version: int = Field(default=0, ge=0)
    command_seq: int = Field(default=0, ge=0)


class FailureSummaryResponse(BaseModel):
    summary_id: str
    task_id: str
    failure_event_id: str
    failed_step_id: str
    completed_step_ids: list[str] = Field(default_factory=list)
    failure_type: str = ""
    severity: str = ""
    reason: str = ""
    recovery_hint: str = ""
    local_retry_count: int = 0
    requested_replan_scope: str = ""
    generated_at: datetime | None = None


class FailureSummaryListResponse(BaseModel):
    task_id: str
    summaries: list[FailureSummaryResponse] = Field(default_factory=list)


class ReplanRequest(BaseModel):
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
    current_scene_version: int = Field(ge=0)
    scene_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    idempotency_key: str = Field(default="")


class ReplanResponse(BaseModel):
    request_id: str
    outcome: str
    reason: str = ""
    new_plan_version: int = 0
    new_command_seq: int = 0
    new_steps: list[dict[str, Any]] = Field(default_factory=list)
    planner_name: str = ""
    prompt_version: str = ""
    created_at: datetime | None = None


class CompletionEvidenceRequest(BaseModel):
    task_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    plan_version: int = Field(ge=0)
    command_seq: int = Field(ge=1)
    completed_step_ids: list[str] = Field(default_factory=list)
    completion_criteria_results: dict[str, bool] = Field(default_factory=dict)
    final_robot_state: dict[str, Any] = Field(default_factory=dict)
    final_target_state: dict[str, Any] = Field(default_factory=dict)
    final_safety_decision: str = Field(min_length=1)
    scene_version: int = Field(ge=0)
    scene_timestamp: datetime
    correlation_id: str = Field(default="")
    local_retry_count: int = Field(default=0, ge=0)
    cloud_replan_count: int = Field(default=0, ge=0)


class CompletionReportResponse(BaseModel):
    summary_id: str
    task_id: str
    result: str
    total_duration_ms: int = 0
    local_retry_count: int = 0
    cloud_replan_count: int = 0
    completed_at: datetime | None = None
