"""仅大模型基线的数据模型。

模型字段显式区分 fake provider、真实云模型、本地模型和环境阻塞，避免把管线测试写成
真实大模型性能证据。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMOnlyProfile(StrEnum):
    """仅大模型基线实验规模。"""

    SMOKE = "smoke"
    VALIDATION = "validation"


class LLMOnlyProvider(StrEnum):
    """仅大模型基线 provider 类型。"""

    FAKE = "fake"
    OPENAI_COMPATIBLE = "openai-compatible"
    OLLAMA = "ollama"


class ModelRuntimeType(StrEnum):
    """模型运行证据等级。"""

    REAL_LLM_RUNTIME = "REAL_LLM_RUNTIME"
    LOCAL_LLM_RUNTIME = "LOCAL_LLM_RUNTIME"
    FAKE_PROVIDER_PIPELINE_TEST = "FAKE_PROVIDER_PIPELINE_TEST"
    RULE_BASED_BASELINE = "RULE_BASED_BASELINE"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"


class LLMOnlyRunRecord(BaseModel):
    """单条 LLM-only 对照样本。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    baseline_id: str
    profile: LLMOnlyProfile
    provider: LLMOnlyProvider
    model_runtime_type: ModelRuntimeType
    scenario_id: str
    seed: int
    repetition: int
    backend: str = "MOCK"
    status: str
    task_success: bool
    model_request_count: int = Field(ge=0)
    valid_contract_rate: float = Field(ge=0.0, le=1.0)
    schema_validation_failure_count: int = Field(ge=0)
    semantic_validation_failure_count: int = Field(ge=0)
    repair_count: int = Field(ge=0)
    refusal_rate: float = Field(ge=0.0, le=1.0)
    unsafe_proposed_action_count: int = Field(ge=0)
    unsafe_command_execution_count: int = Field(default=0, ge=0)
    safety_shield_checked: bool = True
    hardware_gate_checked: bool = True
    hardware_execution: bool = False
    dispatch: bool = False
    real_controller_contacted: bool = False
    hardware_motion_observed: bool = False
    hardware_write_operations: list[str] = Field(default_factory=list)
    prompt_hash: str
    response_hash: str
    source_artifact_path: str
    source_artifact_hash: str
    token_usage: str | int = "NOT_AVAILABLE"
    estimated_cost: str | float = "NOT_AVAILABLE"
    notes: str = ""


class LLMOnlySummary(BaseModel):
    """LLM-only 基线汇总。"""

    model_config = ConfigDict(extra="forbid")

    status: str
    runtime_status: str
    profile: LLMOnlyProfile
    provider: LLMOnlyProvider
    model_runtime_type: ModelRuntimeType
    run_count: int
    runtime_completed_count: int
    model_request_count: int
    model_runtime_accepted: bool
    authoritative_for_model_performance: bool
    contains_secret: bool = False
    unsafe_command_execution_count: int = 0
    real_controller_contacted: bool = False
    hardware_motion_observed: bool = False
    hardware_write_operations: list[str] = Field(default_factory=list)
    source_artifact_hash_verified: bool = True
    blockers: list[str] = Field(default_factory=list)
    notes: str = ""


def summary_to_json(summary: LLMOnlySummary) -> dict[str, Any]:
    """将 Pydantic summary 转为 JSON 友好的 dict。"""

    return summary.model_dump(mode="json")
