"""结构化数据模型，作为 API、测试和服务之间的稳定契约。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cloud_edge_robot_arm.contracts import SafetyDecision, SkillName


class SkillTemplateStatus(StrEnum):
    """技能模板生命周期状态，区分候选、可信、隔离、失效和过期。"""

    CANDIDATE = "CANDIDATE"
    TRUSTED = "TRUSTED"
    QUARANTINED = "QUARANTINED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class SkillCacheKey(BaseModel):
    """技能缓存匹配键，绑定机器人能力、场景意图和安全策略版本。"""

    model_config = ConfigDict(frozen=True, use_enum_values=False)

    skill_name: SkillName
    robot_model: str = Field(min_length=1)
    end_effector_type: str = Field(min_length=1)
    object_class: str = Field(min_length=1)
    task_intent: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    parameter_schema_version: str = Field(min_length=1)
    robot_capability_hash: str = Field(min_length=1)
    safety_policy_hash: str = Field(min_length=1)
    calibration_version: str = Field(min_length=1)

    def stable_hash(self) -> str:
        """生成稳定哈希，用于跨进程匹配和 SQLite 索引。"""
        return stable_payload_hash(self)


class SkillTemplate(BaseModel):
    """可复用高层技能模板，只保存参数模板和前后置条件，不保存低层控制命令。"""

    model_config = ConfigDict(use_enum_values=False)

    template_id: str = Field(min_length=1)
    cache_key: SkillCacheKey
    skill_name: SkillName
    parameter_template: dict[str, Any] = Field(default_factory=dict)
    required_preconditions: list[str] = Field(default_factory=list)
    expected_success_conditions: list[str] = Field(default_factory=list)
    expected_duration_ms: int = Field(gt=0)
    timeout_ms: int = Field(gt=0)
    source_contract_id: str = Field(min_length=1)
    source_plan_version: int = Field(ge=0)
    status: SkillTemplateStatus = SkillTemplateStatus.CANDIDATE
    template_version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime

    @field_validator("created_at", "updated_at", "expires_at")
    @classmethod
    def datetimes_must_have_tz(cls, value: datetime) -> datetime:
        """要求模板时间带时区，避免 TTL 和过期判断出现本地时间歧义。"""
        if value.tzinfo is None:
            raise ValueError("skill cache datetimes must include timezone information")
        return value

    @field_validator("parameter_template")
    @classmethod
    def reject_low_level_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        """拒绝关节、轨迹、PWM 和绕过安全等低层字段进入技能缓存。"""
        low_level = {
            "joint_angles",
            "joint_positions",
            "trajectory",
            "trajectory_points",
            "pwm",
            "motor_current",
            "servo_pulse",
            "disable_safety",
            "bypass_safety",
            "ignore_collision",
            "force_execute",
        }.intersection(value)
        if low_level:
            raise ValueError(f"skill cache cannot store low-level fields: {sorted(low_level)}")
        return value


class SkillExecutionRecord(BaseModel):
    """技能模板执行记录，用于统计成功率、安全拒绝和晋级条件。"""

    model_config = ConfigDict(use_enum_values=False)

    execution_id: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    success: bool
    safety_decision: SafetyDecision
    failure_reason: str = ""
    duration_ms: int = Field(ge=0)
    local_retry_count: int = Field(ge=0)
    cloud_replan_count: int = Field(ge=0)
    scene_confidence: float = Field(ge=0.0, le=1.0)
    network_quality: float = Field(ge=0.0, le=1.0)
    executed_at: datetime
    evidence_hash: str = Field(min_length=1)

    @field_validator("executed_at")
    @classmethod
    def executed_at_must_have_tz(cls, value: datetime) -> datetime:
        """要求执行时间带时区，保证统计排序和审计时间一致。"""
        if value.tzinfo is None:
            raise ValueError("executed_at must include timezone information")
        return value


class SkillStatistics(BaseModel):
    """技能模板聚合统计，供晋级、隔离和 AUTO 模式风险判断使用。"""

    total_executions: int = Field(default=0, ge=0)
    successful_executions: int = Field(default=0, ge=0)
    failed_executions: int = Field(default=0, ge=0)
    safety_rejection_count: int = Field(default=0, ge=0)
    timeout_count: int = Field(default=0, ge=0)
    average_duration_ms: float = Field(default=0.0, ge=0.0)
    recent_success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    consecutive_failures: int = Field(default=0, ge=0)
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None


class SkillCachePromotionPolicy(BaseModel):
    """技能模板晋级策略，定义可信模板所需成功次数和失败隔离阈值。"""

    min_successes: int = Field(default=3, ge=1)
    min_recent_success_rate: float = Field(default=0.9, ge=0.0, le=1.0)
    quarantine_failures: int = Field(default=2, ge=1)
    timeout_anomaly_factor: float = Field(default=2.0, gt=1.0)


class SkillCacheLookupResult(BaseModel):
    """技能缓存查询结果，说明命中类型、候选模板和不命中原因。"""

    match_type: str
    templates: list[SkillTemplate] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


def stable_payload_hash(value: Any) -> str:
    """对 Pydantic 或普通 payload 生成排序后的 SHA-256 稳定哈希。"""
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
