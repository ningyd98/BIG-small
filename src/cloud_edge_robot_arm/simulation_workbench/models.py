"""仿真工作台 API 模型。

这些模型是前端 OpenAPI 类型生成的权威来源，约束 backend、run type、状态、
manifest、metrics 和事件结构，避免前端构造低层机器人控制命令。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SimulationBackend(StrEnum):
    """仿真后端枚举，严格区分 Mock、MuJoCo、Isaac 和 MoveIt dry-run。"""

    MOCK = "MOCK"
    MUJOCO = "MUJOCO"
    ISAAC_SIM = "ISAAC_SIM"
    MOVEIT_DRY_RUN = "MOVEIT_DRY_RUN"


class SimulationRunType(StrEnum):
    """仿真运行类型，覆盖单次、批量、扫描、后端配对和模式对比。"""

    SINGLE = "SINGLE"
    BATCH = "BATCH"
    SWEEP = "SWEEP"
    PAIRED_BACKEND = "PAIRED_BACKEND"
    MODE_COMPARISON = "MODE_COMPARISON"


class SimulationRunStatus(StrEnum):
    """仿真任务状态机枚举，包含队列、执行、取消、超时和恢复状态。"""

    CREATED = "CREATED"
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    LEASED = "LEASED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLING = "CANCELLING"
    FINALIZING = "FINALIZING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"
    INTERRUPTED = "INTERRUPTED"
    RECOVERY_PENDING = "RECOVERY_PENDING"


class SimulationRunnerKind(StrEnum):
    """安全 runner allowlist，禁止前端提交任意脚本、shell 或可执行文件。"""

    MOCK_SCENARIO = "MOCK_SCENARIO"
    MUJOCO_SCENARIO = "MUJOCO_SCENARIO"
    PHASE8_BATCH = "PHASE8_BATCH"
    PHASE8_SWEEP = "PHASE8_SWEEP"
    PHASE9_MUJOCO_BENCHMARK = "PHASE9_MUJOCO_BENCHMARK"
    ISAAC_BENCHMARK = "ISAAC_BENCHMARK"
    CROSS_BACKEND_PAIRED = "CROSS_BACKEND_PAIRED"


class BackendReadiness(StrEnum):
    """后端可用性状态，区分 READY、降级、环境阻塞和未配置。"""

    READY = "READY"
    DEGRADED = "DEGRADED"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class ScenarioCategory(StrEnum):
    """场景分类枚举，用于前端筛选故障、网络、安全和恢复场景。"""

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
    """网络配置草稿，描述延迟、抖动、丢包和带宽上限。"""

    model_config = ConfigDict(extra="forbid")

    name: str = "NORMAL"
    base_latency_ms: int = Field(default=40, ge=0, le=60_000)
    jitter_ms: int = Field(default=5, ge=0, le=60_000)
    packet_loss: float = Field(default=0.0, ge=0.0, le=1.0)
    bandwidth_kbps: int = Field(default=10_000, gt=0)


class FaultProfileDraft(BaseModel):
    """故障注入配置草稿，只允许结构化参数，不允许任意执行字段。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="none", min_length=1, max_length=80)
    parameters: dict[str, int | float | str | bool] = Field(default_factory=dict)


class DomainRandomizationDraft(BaseModel):
    """域随机化配置草稿，控制仿真扰动是否启用及其等级。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    level: str = "NONE"


class ExperimentDraft(BaseModel):
    """前端提交的高层实验草稿，不包含机器人低层控制命令。"""

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
        """拒绝 shell、路径、模块、环境变量和非 allowlist 控制模式。"""
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
    """规范化实验 manifest，记录来源 commit、tree hash 和复现哈希。"""

    manifest_id: str
    schema_version: str = "phase11.simulation.v1"
    normalized_config: dict[str, Any]
    source_commit: str
    source_tree_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    run_count: int = Field(ge=0)
    reproducibility_hash: str


class BatchProgress(BaseModel):
    """批量任务进度统计，记录各状态计数和整体进度比例。"""

    total: int = Field(ge=0)
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    blocked: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    timed_out: int = Field(default=0, ge=0)
    interrupted: int = Field(default=0, ge=0)
    progress_ratio: float = Field(ge=0.0, le=1.0)


class SimulationMetric(BaseModel):
    """仿真指标记录，绑定后端、场景、seed、控制模式和聚合方式。"""

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
    """运行时间线事件，记录序列、来源、严重级别和虚拟时间。"""

    sequence: int
    event_type: str
    source: str
    severity: str = "info"
    virtual_time_ms: int = 0
    wall_time: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)


class ScenarioDefinitionView(BaseModel):
    """面向前端的场景定义视图，暴露故障、预期不变量和后端支持。"""

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
    """单个后端能力描述，包含 readiness、支持模式、runner 和限制。"""

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
    """仿真工作台能力响应，包含全部后端和硬件安全声明。"""

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
    """场景列表响应，返回 scenario_registry 派生的场景视图。"""

    scenarios: list[ScenarioDefinitionView]


class ParameterSchemaResponse(BaseModel):
    """参数 schema 响应，声明权威模型、枚举、数值边界和禁用字段。"""

    schema_version: str = "phase11.simulation.v1"
    authoritative_models: list[str]
    enums: dict[str, list[str]]
    numeric_limits: dict[str, dict[str, int | float]]
    forbidden_fields: list[str]


class ValidationResponse(BaseModel):
    """实验草稿校验结果，返回 manifest、run 数、blocker 和 warning。"""

    valid: bool
    manifest: ExperimentManifest
    run_count: int
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SimulationRunRecord(BaseModel):
    """仿真运行记录，统一运行状态、队列信息、artifact 和硬件声明。"""

    run_id: str
    job_id: str = ""
    queue_position: int = 0
    backend: SimulationBackend
    run_type: SimulationRunType
    status: SimulationRunStatus
    scenario_id: str
    control_mode: str
    seed: int
    manifest: ExperimentManifest
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    accepted_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempt: int = 0
    max_attempts: int = 1
    timeout_seconds: int = 300
    cancel_requested: bool = False
    worker_id: str = ""
    lease_id: str = ""
    runtime_reason: str = ""
    blockers: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    hardware_claim: str = "SIMULATION_ONLY"
    real_controller_contacted: bool = False
    hardware_motion_observed: bool = False
    hardware_write_operations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class SimulationRunListResponse(BaseModel):
    """仿真运行列表响应。"""

    runs: list[SimulationRunRecord]


class SimulationEventsResponse(BaseModel):
    """仿真事件列表响应。"""

    events: list[TimelineEvent]


class SimulationMetricsResponse(BaseModel):
    """仿真指标列表响应。"""

    metrics: list[SimulationMetric]


class SimulationArtifactsResponse(BaseModel):
    """仿真 artifact 路径响应，只返回相对路径。"""

    artifacts: dict[str, str]


class ReproductionResponse(BaseModel):
    """复现实验响应，携带复现草稿、环境匹配状态和 warning。"""

    draft: ExperimentDraft
    environment_match: bool
    warnings: list[str] = Field(default_factory=list)
    reproducibility_hash: str


class BatchRecord(BaseModel):
    """批量实验记录，保存 manifest、进度、run IDs 和安全声明。"""

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
    """对比请求，指定对比类型、run IDs 和可选 paired key。"""

    model_config = ConfigDict(extra="forbid")

    comparison_type: str
    run_ids: list[str] = Field(min_length=1, max_length=200)
    paired_key: dict[str, int | str | float | bool] = Field(default_factory=dict)


class ComparisonResponse(BaseModel):
    """对比响应，返回统计结果、参与指标和 warning。"""

    comparison_id: str
    comparison_type: str
    statistics: dict[str, Any]
    metrics: list[SimulationMetric]
    warnings: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    """导出请求，指定导出类型、runs、batch 或 comparison。"""

    model_config = ConfigDict(extra="forbid")

    export_type: str
    run_ids: list[str] = Field(default_factory=list, max_length=200)
    batch_id: str = ""
    comparison_id: str = ""


class ExportResponse(BaseModel):
    """导出响应，返回相对路径、格式、脱敏标记和预览文本。"""

    export_id: str
    format: str
    relative_path: str
    redacted: bool
    content_preview: str
