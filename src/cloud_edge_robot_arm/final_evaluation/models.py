"""Phase 12 最终评估模型。

这些模型记录研究问题、实验矩阵、运行结果、聚合统计和安全边界。所有硬件字段都保持
显式 false/empty，避免把仿真证据误表述为真实机械臂证据。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    hardware_claims: HardwareClaims = Field(default_factory=HardwareClaims)


class Phase12Aggregate(BaseModel):
    """Phase 12 聚合结果，用于生成论文表格和图表。"""

    profile: Phase12Profile
    run_count: int
    success_count: int
    failed_count: int
    blocked_by_env_count: int
    unsafe_command_execution_count: int
    by_mode: dict[str, dict[str, Any]]
    by_experiment: dict[str, dict[str, Any]]
    by_backend: dict[str, dict[str, Any]]
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
