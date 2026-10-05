"""结构化数据模型，作为 API、测试和服务之间的稳定契约。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from cloud_edge_robot_arm.contracts import (
    AutoModeDecision,
    AutoModeStatus,
    AutoModeTransition,
    ControlMode,
    RiskSnapshot,
)


class AutoModePolicy(BaseModel):
    """AUTO 模式策略阈值，约束风险分层、停留时间和任务内切换次数。"""

    version: str = Field(min_length=1)
    low_risk_max: float = Field(default=25.0, ge=0.0, le=100.0)
    medium_risk_max: float = Field(default=60.0, ge=0.0, le=100.0)
    high_risk_max: float = Field(default=80.0, ge=0.0, le=100.0)
    min_dwell_seconds: int = Field(default=120, ge=0)
    switch_cooldown_seconds: int = Field(default=300, ge=0)
    confirmation_count: int = Field(default=2, ge=1)
    max_switches_per_task: int = Field(default=5, ge=1)


AutoModeState = AutoModeStatus


class AutoModeTransitionRequest(BaseModel):
    """模式切换准备请求，携带幂等键和期望版本以避免重复提交。"""

    task_id: str = Field(min_length=1)
    from_mode: ControlMode
    to_mode: ControlMode
    expected_mode_version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


AutoModeTransitionRecord = AutoModeTransition
AutoModeDecisionRecord = AutoModeDecision


class AutoModeDecisionContext(BaseModel):
    """AUTO 决策输入上下文，汇总风险、缓存、合同和监督可用性。"""

    current_state: AutoModeState
    risk_snapshot: RiskSnapshot
    cache_match_type: str
    cache_confidence: float
    active_contract_complete: bool
    checkpoint_persisted: bool
    event_autonomy_ready: bool
    supervision_available: bool
    atomic_step_active: bool
    mode_history: list[ControlMode] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
