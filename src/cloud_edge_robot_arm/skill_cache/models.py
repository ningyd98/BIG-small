from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cloud_edge_robot_arm.contracts import SafetyDecision, SkillName


class SkillTemplateStatus(StrEnum):
    CANDIDATE = "CANDIDATE"
    TRUSTED = "TRUSTED"
    QUARANTINED = "QUARANTINED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"


class SkillCacheKey(BaseModel):
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
        return stable_payload_hash(self)


class SkillTemplate(BaseModel):
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
        if value.tzinfo is None:
            raise ValueError("skill cache datetimes must include timezone information")
        return value

    @field_validator("parameter_template")
    @classmethod
    def reject_low_level_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
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
        if value.tzinfo is None:
            raise ValueError("executed_at must include timezone information")
        return value


class SkillStatistics(BaseModel):
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
    min_successes: int = Field(default=3, ge=1)
    min_recent_success_rate: float = Field(default=0.9, ge=0.0, le=1.0)
    quarantine_failures: int = Field(default=2, ge=1)
    timeout_anomaly_factor: float = Field(default=2.0, gt=1.0)


class SkillCacheLookupResult(BaseModel):
    match_type: str
    templates: list[SkillTemplate] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)


def stable_payload_hash(value: Any) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
