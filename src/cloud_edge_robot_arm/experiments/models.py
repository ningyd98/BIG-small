from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cloud_edge_robot_arm.contracts import ControlMode, RiskLevel, SafetyDecision


class ExperimentMode(StrEnum):
    PCSC = "PCSC"
    ETEAC = "ETEAC"
    AUTO = "AUTO"

    def to_control_mode(self) -> ControlMode:
        if self == ExperimentMode.PCSC:
            return ControlMode.PERIODIC_CLOUD_SUPERVISION
        if self == ExperimentMode.ETEAC:
            return ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY
        return ControlMode.AUTO


class NetworkProfileName(StrEnum):
    GOOD = "GOOD"
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"
    POOR = "POOR"
    SEVERE = "SEVERE"
    INTERMITTENT = "INTERMITTENT"


class CachePolicy(StrEnum):
    CACHE_ENABLED = "CACHE_ENABLED"
    NO_CACHE_REUSE = "NO_CACHE_REUSE"


class AblationType(StrEnum):
    A1_AUTO_WITHOUT_SKILL_CACHE_SIGNAL = "A1_AUTO_WITHOUT_SKILL_CACHE_SIGNAL"
    A2_AUTO_WITHOUT_NETWORK_SIGNAL = "A2_AUTO_WITHOUT_NETWORK_SIGNAL"
    A3_AUTO_WITHOUT_SCENE_DYNAMICS_SIGNAL = "A3_AUTO_WITHOUT_SCENE_DYNAMICS_SIGNAL"
    A4_NO_CACHE_REUSE = "A4_NO_CACHE_REUSE"
    A5_CACHE_ENABLED = "A5_CACHE_ENABLED"
    A6_FIXED_MODE_VS_AUTO = "A6_FIXED_MODE_VS_AUTO"
    A7_SAFETY_SHADOW_COUNTERFACTUAL = "A7_SAFETY_SHADOW_COUNTERFACTUAL"


class FaultType(StrEnum):
    TARGET_MOVED = "TARGET_MOVED"
    OBSTACLE_INSERTED = "OBSTACLE_INSERTED"
    GRASP_FAILURE = "GRASP_FAILURE"
    TARGET_LOST = "TARGET_LOST"
    PERCEPTION_DEGRADED = "PERCEPTION_DEGRADED"
    NETWORK_DEGRADED = "NETWORK_DEGRADED"
    NETWORK_OUTAGE = "NETWORK_OUTAGE"
    CLOUD_UNAVAILABLE = "CLOUD_UNAVAILABLE"
    STALE_DUPLICATE_REORDERED_COMMAND = "STALE_DUPLICATE_REORDERED_COMMAND"
    SKILL_CACHE_HIT = "SKILL_CACHE_HIT"
    SKILL_CACHE_QUARANTINE = "SKILL_CACHE_QUARANTINE"
    MODE_OSCILLATION_PRESSURE = "MODE_OSCILLATION_PRESSURE"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    SQLITE_RESTART = "SQLITE_RESTART"


class ResultStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    TIMEOUT = "TIMEOUT"
    NEEDS_OBSERVATION = "NEEDS_OBSERVATION"


class NetworkProfile(BaseModel):
    model_config = ConfigDict(validate_assignment=True, use_enum_values=False)

    name: NetworkProfileName
    base_latency_ms: int = Field(ge=0)
    jitter_ms: int = Field(ge=0)
    loss_rate: float = Field(ge=0.0, le=1.0)
    duplication_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    reorder_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    bandwidth_bytes_per_ms: int | None = Field(default=None, gt=0)
    outage_duration_ms: int = Field(default=0, ge=0)
    cloud_timeout_ms: int = Field(default=5_000, gt=0)
    cloud_available: bool = True


class FaultProfile(BaseModel):
    name: str = Field(min_length=1)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)


class TaskProfile(BaseModel):
    name: str = Field(min_length=1)
    object_class: str = "cube"
    step_count: int = Field(default=7, gt=0)


class FaultEvent(BaseModel):
    fault_id: str = Field(min_length=1)
    fault_type: FaultType
    trigger_time_ms: int = Field(ge=0)
    duration_ms: int = Field(default=0, ge=0)
    priority: int = 0
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)


class ScenarioDefinition(BaseModel):
    scenario_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    initial_world_state: dict[str, int | float | str | bool] = Field(default_factory=dict)
    scheduled_faults: list[FaultEvent] = Field(default_factory=list)
    expected_invariants: list[str] = Field(default_factory=list)
    allowed_result_statuses: list[ResultStatus] = Field(default_factory=list)
    forbidden_result_statuses: list[ResultStatus] = Field(default_factory=list)
    maximum_virtual_duration_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_result_sets(self) -> ScenarioDefinition:
        overlap = set(self.allowed_result_statuses).intersection(self.forbidden_result_statuses)
        if overlap:
            raise ValueError(f"result statuses cannot be both allowed and forbidden: {overlap}")
        return self


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    experiment_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    mode: ExperimentMode
    seed: int = Field(ge=0, le=2**63 - 1)
    repetitions: int = Field(ge=1)
    network_profile: NetworkProfileName
    fault_profile: FaultProfile
    task_profile: TaskProfile
    cache_policy: CachePolicy
    risk_policy_version: str = Field(min_length=1)
    supervision_period_ms: int = Field(gt=0)
    timeout_ms: int = Field(gt=0)
    artifact_dir: Path
    config_schema_version: str = "phase8.v1"
    ablations: list[AblationType] = Field(default_factory=list)

    @field_validator("artifact_dir")
    @classmethod
    def normalize_artifact_dir(cls, value: Path) -> Path:
        return Path(value)


class ExperimentRun(BaseModel):
    run_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    mode: ExperimentMode
    seed: int = Field(ge=0)
    started_at: datetime
    completed_at: datetime | None = None
    result_status: ResultStatus | None = None
    git_commit: str = Field(default="")
    config_hash: str = Field(min_length=1)
    environment: dict[str, str] = Field(default_factory=dict)


class ExperimentResult(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    run_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    scenario_id: str = Field(min_length=1)
    mode: ExperimentMode
    seed: int = Field(ge=0)
    network_profile: NetworkProfileName
    result_status: ResultStatus
    task_success: bool
    task_completion_time_ms: int = Field(ge=0)
    completed_step_count: int = Field(ge=0)
    failed_step_count: int = Field(ge=0)
    first_attempt_success: bool
    retry_count: int = Field(ge=0)
    cloud_invocation_count: int = Field(ge=0)
    supervisory_decision_count: int = Field(ge=0)
    replan_count: int = Field(ge=0)
    command_count: int = Field(ge=0)
    telemetry_count: int = Field(ge=0)
    uploaded_bytes: int = Field(ge=0)
    downloaded_bytes: int = Field(ge=0)
    fault_detection_latency_ms: int | None = Field(default=None, ge=0)
    cloud_response_latency_ms: int | None = Field(default=None, ge=0)
    recovery_latency_ms: int | None = Field(default=None, ge=0)
    recovery_success: bool
    repeated_completed_step_count: int = Field(ge=0)
    safety_allow_count: int = Field(ge=0)
    safety_allow_with_limits_count: int = Field(ge=0)
    safety_pause_count: int = Field(ge=0)
    safety_reject_count: int = Field(ge=0)
    emergency_stop_count: int = Field(ge=0)
    stale_command_rejection_count: int = Field(ge=0)
    duplicate_command_rejection_count: int = Field(ge=0)
    reordered_command_rejection_count: int = Field(ge=0)
    simulated_collision_count: int = Field(ge=0)
    unsafe_counterfactual_count: int = Field(ge=0)
    initial_mode: ControlMode
    final_mode: ControlMode
    mode_switch_count: int = Field(ge=0)
    deferred_switch_count: int = Field(ge=0)
    aborted_transition_count: int = Field(ge=0)
    dwell_block_count: int = Field(ge=0)
    cooldown_block_count: int = Field(ge=0)
    switch_limit_block_count: int = Field(ge=0)
    time_in_pcsc_ms: int = Field(ge=0)
    time_in_eteac_ms: int = Field(ge=0)
    cache_hit_count: int = Field(ge=0)
    cache_miss_count: int = Field(ge=0)
    cache_promotion_count: int = Field(ge=0)
    cache_quarantine_count: int = Field(ge=0)
    cache_invalidation_count: int = Field(ge=0)
    trusted_template_execution_count: int = Field(ge=0)
    final_risk_level: RiskLevel
    terminal_reason: str
    invariant_violations: list[str] = Field(default_factory=list)
    event_count: int = Field(ge=0)
    config_hash: str = Field(min_length=1)
    git_sha: str = Field(default="")
    result_hash: str = Field(min_length=1)
    safety_decision_counts: dict[SafetyDecision, int] = Field(default_factory=dict)
    ablations: list[AblationType] = Field(default_factory=list)


class ExperimentEvent(BaseModel):
    virtual_time_ms: int = Field(ge=0)
    event_type: str = Field(min_length=1)
    entity_id: str = Field(default="")
    payload: dict[str, object] = Field(default_factory=dict)
    payload_hash: str = Field(min_length=1)


class MetricSummary(BaseModel):
    sample_count: int = Field(ge=0)
    mean: float | None = None
    standard_deviation: float | None = None
    median: float | None = None
    p95: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    success_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_interval_low: float | None = None
    confidence_interval_high: float | None = None
