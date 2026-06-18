"""Dashboard API 读模型。

这些模型描述前端展示的项目状态、证据、事件、验收等级和运行时信息；模型中不得
携带 token、credential、真实 IP 或本机绝对路径。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DashboardEnvironment(StrEnum):
    MOCK = "MOCK"
    MUJOCO = "MUJOCO"
    ISAAC_SIM = "ISAAC_SIM"
    ROS2_MOVEIT = "ROS2_MOVEIT"
    MOVEIT_DRY_RUN = "MOVEIT_DRY_RUN"
    REAL_ROBOT_READ_ONLY = "REAL_ROBOT_READ_ONLY"
    REAL_ROBOT_LOW_SPEED = "REAL_ROBOT_LOW_SPEED"
    REAL_ROBOT_OPERATIONAL = "REAL_ROBOT_OPERATIONAL"


class HardwareClaim(StrEnum):
    NONE = "NONE"
    SIMULATION_ONLY = "SIMULATION_ONLY"
    PLANNING_ONLY = "PLANNING_ONLY"
    HARDWARE_READ_ONLY = "HARDWARE_READ_ONLY"
    HARDWARE_MOTION = "HARDWARE_MOTION"


class ServiceStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class ExperimentJobStatus(StrEnum):
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"


class EvidenceStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DEVELOPMENT_EVIDENCE = "DEVELOPMENT_EVIDENCE"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"
    UNKNOWN = "UNKNOWN"


class FreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class DataSourceKind(StrEnum):
    AUTHORITATIVE = "authoritative"
    DERIVED = "derived"
    CONFIGURED_DEFAULT = "configured_default"
    UNAVAILABLE = "unavailable"


class ExperimentKind(StrEnum):
    MOCK_SOFTWARE = "MOCK_SOFTWARE"
    MUJOCO_SMOKE = "MUJOCO_SMOKE"
    SYNTHETIC_DRY_RUN = "SYNTHETIC_DRY_RUN"
    MOVEIT_RUNTIME_DRY_RUN = "MOVEIT_RUNTIME_DRY_RUN"


class UserRole(StrEnum):
    VIEWER = "VIEWER"
    EXPERIMENT_OPERATOR = "EXPERIMENT_OPERATOR"
    SAFETY_REVIEWER = "SAFETY_REVIEWER"


class ServiceHealth(BaseModel):
    name: str
    status: ServiceStatus = ServiceStatus.UNKNOWN
    detail: str = ""
    source: DataSourceKind = DataSourceKind.UNAVAILABLE


class SafetyGateSnapshot(BaseModel):
    execution_mode: str = "DRY_RUN"
    controller_connected: bool | None = None
    emergency_stop_state: str = "UNKNOWN"
    safety_shield_state: ServiceStatus = ServiceStatus.UNKNOWN
    telemetry_freshness: FreshnessStatus = FreshnessStatus.UNKNOWN
    requested_velocity_scale: float = 0.0
    requested_acceleration_scale: float = 0.0
    operator_confirmation_state: str = "NOT_REQUIRED_FOR_READINESS_VIEW"
    current_acceptance_level: str = "NONE"
    required_acceptance_level: str = "LEVEL_0"
    allowed: bool = False
    hardware_motion_authorized: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    decided_at: datetime


class SafetyReviewNoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=1000)
    related_evidence_id: str = ""


class SafetyReviewNoteResponse(BaseModel):
    note_id: str
    role: UserRole
    note: str
    related_evidence_id: str = ""
    hardware_motion_authorized: bool = False
    created_at: datetime


class AcceptanceLevelItem(BaseModel):
    level: str
    definition: str
    locked: bool = True
    prerequisite_complete: bool = False
    evidence_complete: bool = False
    hardware_motion_allowed: bool = False
    blockers: list[str] = Field(default_factory=list)


class Level0ReadOnlySnapshot(BaseModel):
    mode_label: str = "REAL HARDWARE - READ ONLY"
    controller_state: str = "UNAVAILABLE"
    emergency_stop_state: str = "UNKNOWN"
    fault_state: str = "UNKNOWN"
    operation_mode: str = "UNKNOWN"
    joint_state_freshness: str = "UNAVAILABLE"
    tcp_pose_freshness: str = "UNAVAILABLE"
    robot_identity_hash: str = ""
    config_hash: str = ""
    site_session_id: str = ""
    checks: dict[str, bool] = Field(default_factory=dict)
    evidence_complete: bool = False
    controller_contacted: bool = False
    hardware_state_sampled: bool = False
    write_operation_count: int = 0
    hardware_motion_observed: bool = False
    blocker: str = ""
    blockers: list[str] = Field(default_factory=list)


class AcceptanceLevelSnapshot(BaseModel):
    current_level: str = "NONE"
    next_level: str = "LEVEL_0"
    level_definition: str = "Level 0 read-only status and e-stop observation."
    prerequisite_complete: bool = False
    evidence_complete: bool = False
    robot_identity_hash: str = ""
    config_hash: str = ""
    blocked_reasons: list[str] = Field(default_factory=list)
    hardware_motion_allowed: bool = False
    validation_claimed: bool = False
    level0_read_only: Level0ReadOnlySnapshot = Field(default_factory=Level0ReadOnlySnapshot)
    levels: list[AcceptanceLevelItem] = Field(default_factory=list)


class EvidenceIndexRecord(BaseModel):
    evidence_id: str
    phase: str = "unknown"
    evidence_type: str = "artifact"
    status: EvidenceStatus = EvidenceStatus.UNKNOWN
    backend: str = ""
    hardware_claim: HardwareClaim = HardwareClaim.NONE
    generated_at: str = ""
    generated_from_commit: str = ""
    source_tree_hash: str = ""
    worktree_clean: bool | None = None
    config_hash: str = ""
    environment_hash: str = ""
    relative_path: str
    summary: str = ""
    blockers: list[str] = Field(default_factory=list)


class DashboardSummary(BaseModel):
    generated_at: datetime
    software_commit: str = ""
    source_tree_hash: str = ""
    worktree_clean: bool | None = None
    runtime_profile: str = "local"
    current_environment: DashboardEnvironment = DashboardEnvironment.MOVEIT_DRY_RUN
    current_project_status: str = "UNKNOWN"
    current_project_status_source: DataSourceKind = DataSourceKind.UNAVAILABLE
    hardware_claim: HardwareClaim = HardwareClaim.NONE
    real_robot_validation: str = "NOT_STARTED"
    highest_acceptance_level: str = "NONE"
    services: list[ServiceHealth] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    safety_summary: SafetyGateSnapshot
    latest_evidence: list[EvidenceIndexRecord] = Field(default_factory=list)
    active_experiments: list[ExperimentJobRecord] = Field(default_factory=list)


class DashboardEvent(BaseModel):
    event_id: str
    sequence: int
    event_type: str
    source: str
    timestamp: datetime
    task_id: str = ""
    experiment_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class ExperimentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: ExperimentKind
    scenario_id: str = Field(min_length=1)
    seed: int = Field(ge=0)
    control_mode: str = Field(pattern="^(PCSC|ETEAC|AUTO)$")
    network_profile: str = "NORMAL"
    fault_profile: str = "none"
    repetitions: int = Field(default=1, ge=1, le=100)


class ExperimentJobRecord(BaseModel):
    experiment_id: str
    kind: ExperimentKind
    status: ExperimentJobStatus
    scenario_id: str
    seed: int
    control_mode: str
    hardware_claim: HardwareClaim
    created_at: datetime
    updated_at: datetime
    evidence_id: str = ""
    evidence_path: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    blockers: list[str] = Field(default_factory=list)


class CapabilitiesResponse(BaseModel):
    pages: list[str]
    backends: list[str]
    experiments: list[str]
    allowed_write_operations: list[str]
    hardware_write_operations: list[str]
    websocket: bool
    api_schema_version: str = "phase10.2b.v1"


class RuntimeSnapshot(BaseModel):
    runtime_profile: str
    commit: str
    source_tree_hash: str
    worktree_clean: bool | None
    backend_readiness: list[ServiceHealth]
    service_health: list[ServiceHealth]
    environment_blockers: list[str]


class EvidenceListResponse(BaseModel):
    records: list[EvidenceIndexRecord]


class EvidenceDetailResponse(BaseModel):
    record: EvidenceIndexRecord
    content: dict[str, Any] | list[Any] | str


class EvidenceIndexErrorRecord(BaseModel):
    path: str
    error: str


class ExperimentListResponse(BaseModel):
    jobs: list[ExperimentJobRecord]


class ComparisonResponse(BaseModel):
    metrics: list[dict[str, Any]]
    source: DataSourceKind = DataSourceKind.UNAVAILABLE


class AuditEventResponse(BaseModel):
    events: list[DashboardEvent]


class EvidenceParseErrorResponse(BaseModel):
    errors: list[EvidenceIndexErrorRecord]
