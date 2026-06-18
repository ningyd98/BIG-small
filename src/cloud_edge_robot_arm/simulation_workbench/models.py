from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SimulationBackend(StrEnum):
    MOCK = "MOCK"
    MUJOCO = "MUJOCO"
    ISAAC_SIM = "ISAAC_SIM"
    MOVEIT_DRY_RUN = "MOVEIT_DRY_RUN"


class SimulationRunType(StrEnum):
    SINGLE = "SINGLE"
    BATCH = "BATCH"
    SWEEP = "SWEEP"
    PAIRED_BACKEND = "PAIRED_BACKEND"
    MODE_COMPARISON = "MODE_COMPARISON"


class SimulationRunStatus(StrEnum):
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    FINALIZING = "FINALIZING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"


class SimulationRunnerKind(StrEnum):
    MOCK_SCENARIO = "MOCK_SCENARIO"
    MUJOCO_SCENARIO = "MUJOCO_SCENARIO"
    PHASE8_BATCH = "PHASE8_BATCH"
    PHASE8_SWEEP = "PHASE8_SWEEP"
    PHASE9_MUJOCO_BENCHMARK = "PHASE9_MUJOCO_BENCHMARK"
    ISAAC_BENCHMARK = "ISAAC_BENCHMARK"
    CROSS_BACKEND_PAIRED = "CROSS_BACKEND_PAIRED"


class BackendReadiness(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class ScenarioCategory(StrEnum):
    NORMAL = "NORMAL"
    SCENE_CHANGE = "SCENE_CHANGE"
    PERCEPTION = "PERCEPTION"
    NETWORK = "NETWORK"
    CLOUD = "CLOUD"
    COMMAND = "COMMAND"
    CACHE = "CACHE"
    MODE = "MODE"
    SAFETY = "SAFETY"
    RECOVERY = "RECOVERY"


class NetworkDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "NORMAL"
    base_latency_ms: int = Field(default=40, ge=0, le=60_000)
    jitter_ms: int = Field(default=5, ge=0, le=60_000)
    packet_loss: float = Field(default=0.0, ge=0.0, le=1.0)
    bandwidth_kbps: int = Field(default=10_000, gt=0)


class FaultProfileDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="none", min_length=1, max_length=80)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)


class DomainRandomizationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    level: str = "NONE"


class ExperimentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: SimulationBackend
    run_type: SimulationRunType = SimulationRunType.SINGLE
    scenarios: list[str] = Field(min_length=1, max_length=15)
    control_modes: list[str] = Field(min_length=1, max_length=3)
    seeds: list[int] = Field(min_length=1, max_length=100)
    repetitions: int = Field(default=1, ge=1, le=100)
    network_profiles: list[NetworkDraft] = Field(default_factory=lambda: [NetworkDraft()])
    fault_profiles: list[FaultProfileDraft] = Field(default_factory=lambda: [FaultProfileDraft()])
    parameter_overrides: dict[str, int | float | str | bool] = Field(default_factory=dict)
    domain_randomization: DomainRandomizationDraft = Field(default_factory=DomainRandomizationDraft)
    tags: list[str] = Field(default_factory=list, max_length=20)
    description: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def reject_forbidden_parameters(self) -> ExperimentDraft:
        forbidden = {
            "shell",
            "command",
            "cmd",
            "script",
            "path",
            "module",
            "environment",
            "env",
            "executable",
            "runner",
            "runner_name",
            "pythonpath",
        }
        present = forbidden.intersection(self.parameter_overrides)
        if present:
            raise ValueError(f"forbidden simulation parameter: {sorted(present)[0]}")
        invalid_modes = sorted(set(self.control_modes).difference({"PCSC", "ETEAC", "AUTO"}))
        if invalid_modes:
            raise ValueError(f"unsupported control mode: {invalid_modes[0]}")
        return self


class ExperimentManifest(BaseModel):
    manifest_id: str
    schema_version: str = "phase11.simulation.v1"
    normalized_config: dict[str, Any]
    source_commit: str
    source_tree_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_count: int = Field(ge=0)
    reproducibility_hash: str


class BatchProgress(BaseModel):
    total: int = Field(ge=0)
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    blocked: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    progress_ratio: float = Field(ge=0.0, le=1.0)


class SimulationMetric(BaseModel):
    name: str
    value: int | float | str | bool
    unit: str = ""
    aggregation: str = "single"
    source: str
    sample_count: int = Field(default=1, ge=0)
    backend: SimulationBackend
    scenario: str
    seed: int
    control_mode: str


class TimelineEvent(BaseModel):
    sequence: int
    event_type: str
    source: str
    severity: str = "info"
    virtual_time_ms: int = 0
    wall_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)


class ScenarioDefinitionView(BaseModel):
    scenario_id: str
    description: str
    category: ScenarioCategory
    fault_types: list[str]
    initial_world_state: dict[str, Any]
    scheduled_faults: list[dict[str, Any]]
    expected_invariants: list[str]
    allowed_result_statuses: list[str]
    forbidden_result_statuses: list[str]
    maximum_virtual_duration_ms: int
    backend_support: dict[str, BackendReadiness]


class BackendCapability(BaseModel):
    backend: SimulationBackend
    readiness: BackendReadiness
    supported_modes: list[str]
    supported_run_types: list[SimulationRunType]
    supported_experiment_types: list[str]
    runner_allowlist: list[SimulationRunnerKind]
    export_formats: list[str]
    batch_limits: dict[str, int]
    blockers: list[str] = Field(default_factory=list)


class SimulationCapabilitiesResponse(BaseModel):
    schema_version: str = "phase11.simulation.v1"
    backends: list[BackendCapability]
    supported_modes: list[str]
    supported_run_types: list[SimulationRunType]
    runner_allowlist: list[SimulationRunnerKind]
    export_formats: list[str]
    max_batch_runs: int
    hardware_write_operations: list[str] = Field(default_factory=list)
    real_controller_contacted: bool = False
    hardware_motion_observed: bool = False


class ScenarioListResponse(BaseModel):
    scenarios: list[ScenarioDefinitionView]


class ParameterSchemaResponse(BaseModel):
    schema_version: str = "phase11.simulation.v1"
    authoritative_models: list[str]
    enums: dict[str, list[str]]
    numeric_limits: dict[str, dict[str, int | float]]
    forbidden_fields: list[str]


class ValidationResponse(BaseModel):
    valid: bool
    manifest: ExperimentManifest
    run_count: int
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SimulationRunRecord(BaseModel):
    run_id: str
    backend: SimulationBackend
    run_type: SimulationRunType
    status: SimulationRunStatus
    scenario_id: str
    control_mode: str
    seed: int
    manifest: ExperimentManifest
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    blockers: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    hardware_claim: str = "SIMULATION_ONLY"
    real_controller_contacted: bool = False
    hardware_motion_observed: bool = False
    hardware_write_operations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class SimulationRunListResponse(BaseModel):
    runs: list[SimulationRunRecord]


class SimulationEventsResponse(BaseModel):
    events: list[TimelineEvent]


class SimulationMetricsResponse(BaseModel):
    metrics: list[SimulationMetric]


class SimulationArtifactsResponse(BaseModel):
    artifacts: dict[str, str]


class ReproductionResponse(BaseModel):
    draft: ExperimentDraft
    environment_match: bool
    warnings: list[str] = Field(default_factory=list)
    reproducibility_hash: str


class BatchRecord(BaseModel):
    batch_id: str
    manifest: ExperimentManifest
    progress: BatchProgress
    run_ids: list[str]
    status: SimulationRunStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    hardware_write_operations: list[str] = Field(default_factory=list)


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparison_type: str
    run_ids: list[str] = Field(min_length=1, max_length=200)
    paired_key: dict[str, int | str | float | bool] = Field(default_factory=dict)


class ComparisonResponse(BaseModel):
    comparison_id: str
    comparison_type: str
    statistics: dict[str, Any]
    metrics: list[SimulationMetric]
    warnings: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_type: str
    run_ids: list[str] = Field(default_factory=list, max_length=200)
    batch_id: str = ""
    comparison_id: str = ""


class ExportResponse(BaseModel):
    export_id: str
    format: str
    relative_path: str
    redacted: bool
    content_preview: str
