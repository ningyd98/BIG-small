"""Phase 12 最终评估模型。

这些模型记录研究问题、实验矩阵、运行结果、聚合统计和安全边界。所有硬件字段都保持
显式 false/empty，避免把仿真证据误表述为真实机械臂证据。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# 中文说明：actual_run_count 是历史兼容字段，当前语义等同 runtime_invocation_count；
# runtime_completion_count 才表示真正完成的运行数量。
ACTUAL_RUN_COUNT_SEMANTICS = "runtime_invocation_compatibility_alias"


class Phase12Profile(StrEnum):
    """Phase 12 实验规模 profile；只有 full 可用于最终论文统计结论。"""

    SMOKE = "smoke"
    VALIDATION = "validation"
    FULL = "full"


class Phase12Backend(StrEnum):
    """Phase 12 后端枚举；REAL_HARDWARE 不存在，防止误注册真实设备。"""

    MOCK = "MOCK"
    MUJOCO = "MUJOCO"
    ISAAC_SIM = "ISAAC_SIM"
    MOVEIT_DRY_RUN = "MOVEIT_DRY_RUN"
    SYNTHETIC_DRY_RUN = "SYNTHETIC_DRY_RUN"
    PLANNER_DRY_RUN = "PLANNER_DRY_RUN"


class Phase12RunStatus(StrEnum):
    """Phase 12 单次运行状态，保留失败和环境阻塞样本。"""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SAFETY_STOPPED = "SAFETY_STOPPED"
    TIMEOUT = "TIMEOUT"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"


class ExecutionSource(StrEnum):
    """Phase 12 结果来源，区分管线样本和真实软件/仿真 runner。"""

    SYNTHETIC_PIPELINE_SAMPLE = "SYNTHETIC_PIPELINE_SAMPLE"
    PHASE8_ACTUAL_RUN = "PHASE8_ACTUAL_RUN"
    PHASE9_MUJOCO_ACTUAL_RUN = "PHASE9_MUJOCO_ACTUAL_RUN"
    PHASE9_2_ISAAC_ENVIRONMENT_CHECK = "PHASE9_2_ISAAC_ENVIRONMENT_CHECK"
    PHASE9_2_ISAAC_ACTUAL_RUN = "PHASE9_2_ISAAC_ACTUAL_RUN"
    PHASE10_SYNTHETIC_DRY_RUN_ACTUAL = "PHASE10_SYNTHETIC_DRY_RUN_ACTUAL"
    PHASE10_MOVEIT_ENVIRONMENT_CHECK = "PHASE10_MOVEIT_ENVIRONMENT_CHECK"
    PHASE10_MOVEIT_RUNTIME_ACTUAL = "PHASE10_MOVEIT_RUNTIME_ACTUAL"
    PHASE11_RUNTIME_ACTUAL = "PHASE11_RUNTIME_ACTUAL"
    PHASE11_2_PLANNER_ACTUAL = "PHASE11_2_PLANNER_ACTUAL"


class EnvironmentStatus(StrEnum):
    """runner 环境状态，BLOCKED_BY_ENV 必须单独统计。"""

    READY = "READY"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"


class BlockerStage(StrEnum):
    """运行阻塞发生阶段；环境阻塞不能算 runtime execution。"""

    NONE = ""
    ENVIRONMENT_CHECK = "ENVIRONMENT_CHECK"
    RUNTIME = "RUNTIME"
    FINALIZATION = "FINALIZATION"


class MetricSource(StrEnum):
    """指标来源分级，论文统计默认只使用 measured/event-derived。"""

    MEASURED = "MEASURED"
    EVENT_DERIVED = "EVENT_DERIVED"
    ADAPTER_DERIVED = "ADAPTER_DERIVED"
    CONSTANT_PLACEHOLDER = "CONSTANT_PLACEHOLDER"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class MetricProvenance(BaseModel):
    """单个指标的来源、字段、artifact 和单位。"""

    source: MetricSource
    source_field: str = ""
    source_artifact: str = ""
    unit: str = ""


class Phase12SamplePolicy(BaseModel):
    """分类型样本策略，避免 full profile 误用统一 seed_count。"""

    seed_count: int = Field(ge=1)
    repetitions: int = Field(ge=1)
    task_count: int = Field(ge=1)
    pairing_required: bool = False
    required_actual_backend: bool = True
    minimum_successful_samples: int = Field(ge=0)


class HardwareClaims(BaseModel):
    """最终评估的硬件声明，必须始终保持未接触、未运动、无写操作。"""

    real_controller_contacted: bool = False
    hardware_motion_observed: bool = False
    hardware_write_operations: list[str] = Field(default_factory=list)
    highest_real_hardware_acceptance_level: str = "NONE"
    real_robot_validation: str = "NOT_STARTED"


class Phase12ExperimentDefinition(BaseModel):
    """固定实验定义，描述 RQ、场景、变量、backend 和安全声明。"""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    title: str
    research_question: str
    scenario_ids: list[str]
    backends: list[Phase12Backend]
    control_modes: list[str]
    independent_variables: list[str]
    dependent_metrics: list[str]
    seeds_smoke: list[int]
    validation_seed_count: int
    full_seed_count: int
    repetitions: int
    runner_kind: str
    sample_policy: Phase12SamplePolicy
    status_if_unavailable: str = "BLOCKED_BY_ENV"
    pairing_key: str | None = None
    hardware_claim: str = "software_or_simulation_only"


class Phase12ExperimentPlan(BaseModel):
    """展开后的实验计划，供 runner 和 verifier 判断样本量与安全边界。"""

    profile: Phase12Profile
    experiments: list[Phase12ExperimentDefinition]
    run_count: int
    seed_count: int
    baseline_seed_count: int
    repetitions: int
    runner_mapping: dict[str, str] = Field(default_factory=dict)
    hardware_claims: HardwareClaims


class Phase12RunManifest(BaseModel):
    """单次 Phase 12 run manifest，记录复现所需的非敏感信息。"""

    run_id: str
    experiment_id: str
    research_question: str
    profile: Phase12Profile
    backend: Phase12Backend
    scenario_id: str
    control_mode: str
    seed: int
    repetition: int
    source_commit: str
    source_tree_hash: str
    worktree_clean: bool
    config_hash: str
    environment_hash: str
    planner_provider: str
    model_name: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    execution_source: ExecutionSource = ExecutionSource.SYNTHETIC_PIPELINE_SAMPLE
    # 中文说明：兼容 Phase 12.1 旧 artifact；真实 runtime 语义以
    # runtime_invoked/runtime_completed 为准，不能再用本字段单独证明真实运行。
    actual_runner_invoked: bool = False
    adapter_attempted: bool = False
    environment_check_completed: bool = False
    runtime_invoked: bool = False
    runtime_completed: bool = False
    authoritative_for_thesis: bool = False
    blocker_stage: BlockerStage = BlockerStage.NONE
    source_artifact_path: str = ""
    source_artifact_hash: str = ""
    source_verifier: str = ""
    environment_status: EnvironmentStatus = EnvironmentStatus.READY
    hardware_claims: HardwareClaims = Field(default_factory=HardwareClaims)


class Phase12Result(BaseModel):
    """Phase 12 单次结果行，统一承载任务、协同、安全、恢复和规划指标。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    experiment_id: str
    research_question: str
    profile: Phase12Profile
    backend: Phase12Backend
    scenario_id: str
    control_mode: str
    seed: int
    repetition: int
    status: Phase12RunStatus
    task_success: bool
    failure_type: str = ""
    task_completion_rate: float = Field(ge=0.0, le=1.0)
    total_completion_time_ms: float = Field(ge=0.0)
    cloud_planning_time_ms: float = Field(ge=0.0)
    edge_execution_time_ms: float = Field(ge=0.0)
    local_recovery_time_ms: float = Field(ge=0.0)
    replanning_time_ms: float = Field(ge=0.0)
    communication_wait_time_ms: float = Field(ge=0.0)
    cloud_invocation_count: int = Field(ge=0)
    communication_count: int = Field(ge=0)
    uploaded_bytes: int = Field(ge=0)
    downloaded_bytes: int = Field(ge=0)
    supervision_count: int = Field(ge=0)
    mode_switch_count: int = Field(ge=0)
    local_retry_count: int = Field(ge=0)
    local_recovery_success_count: int = Field(ge=0)
    replan_count: int = Field(ge=0)
    cloud_fallback_count: int = Field(ge=0)
    completed_without_cloud_after_start: bool
    safety_intervention_count: int = Field(ge=0)
    rejected_action_count: int = Field(ge=0)
    stale_telemetry_rejection: int = Field(ge=0)
    workspace_rejection: int = Field(ge=0)
    collision_rejection: int = Field(ge=0)
    emergency_stop_event: int = Field(ge=0)
    unsafe_command_execution_count: int = 0
    restart_recovery_success: bool = True
    duplicate_execution_count: int = 0
    lease_recovery_count: int = 0
    artifact_consistency: bool = True
    event_loss_count: int = 0
    paired_success_agreement: bool | None = None
    completion_time_delta: float | None = None
    planner_success: bool = True
    valid_contract_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    repair_count: int = Field(default=0, ge=0)
    refusal_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    response_latency_ms: float = Field(default=0.0, ge=0.0)
    token_usage: int | None = None
    estimated_cost: float | None = None
    result_hash: str
    artifact_hash: str
    execution_source: ExecutionSource = ExecutionSource.SYNTHETIC_PIPELINE_SAMPLE
    # 中文说明：兼容 Phase 12.1 旧 artifact；统计和 verifier 必须使用
    # runtime_invoked/runtime_completed 区分环境检查、运行失败和运行完成。
    actual_runner_invoked: bool = False
    adapter_attempted: bool = False
    environment_check_completed: bool = False
    runtime_invoked: bool = False
    runtime_completed: bool = False
    authoritative_for_thesis: bool = False
    blocker_stage: BlockerStage = BlockerStage.NONE
    source_artifact_path: str = ""
    source_artifact_hash: str = ""
    source_verifier: str = ""
    environment_status: EnvironmentStatus = EnvironmentStatus.READY
    metric_provenance: dict[str, MetricProvenance] = Field(default_factory=dict)
    planner_provider: str = ""
    model_name: str = ""
    hardware_claims: HardwareClaims = Field(default_factory=HardwareClaims)


class Phase12Aggregate(BaseModel):
    """Phase 12 聚合结果，用于生成论文表格和图表。"""

    profile: Phase12Profile
    run_count: int
    success_count: int
    failed_count: int
    blocked_by_env_count: int
    unsafe_command_execution_count: int
    synthetic_sample_count: int = 0
    actual_run_count_semantics: str = ACTUAL_RUN_COUNT_SEMANTICS
    actual_run_count: int = 0
    adapter_attempt_count: int = 0
    runtime_invocation_count: int = 0
    runtime_completion_count: int = 0
    blocked_before_runtime_count: int = 0
    authoritative_thesis_run_count: int = 0
    by_mode: dict[str, dict[str, Any]]
    by_experiment: dict[str, dict[str, Any]]
    by_backend: dict[str, dict[str, Any]]
    authoritative_by_mode: dict[str, dict[str, Any]] = Field(default_factory=dict)
    authoritative_by_experiment: dict[str, dict[str, Any]] = Field(default_factory=dict)
    authoritative_by_backend: dict[str, dict[str, Any]] = Field(default_factory=dict)
    hardware_claims: HardwareClaims = Field(default_factory=HardwareClaims)


class Phase12StatisticalResult(BaseModel):
    """统计分析输出，包含组统计、配对差异、缺失样本和环境阻塞计数。"""

    profile: Phase12Profile
    group_statistics: dict[str, dict[str, Any]]
    paired_results: dict[str, Any]
    missing_data_reasons: dict[str, int]
    blocked_by_env_count: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Phase12PairedResult(BaseModel):
    """MuJoCo/Isaac 或模式配对差异行。"""

    pairing_key: str
    left_label: str
    right_label: str
    left_status: Phase12RunStatus
    right_status: Phase12RunStatus
    left_value: float
    right_value: float
    delta: float | None
