"""Shared runtime decision vocabulary; events carry online verification only."""

from __future__ import annotations

# 类型仅供静态检查；risk、evidence 和 verification_router 复用本模块枚举。
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Protocol

from cloud_edge_robot_arm.contracts import ControlMode
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionStatus,
    ConditionVerdict,
    OnlineEvidenceSnapshot,
)

if TYPE_CHECKING:
    from cloud_edge_robot_arm.auto_mode.baseline_policies import LegacyRuleEvidence
    from cloud_edge_robot_arm.edge.evidence.models import EvidenceVerdict
    from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudgetState
    from cloud_edge_robot_arm.research.network import NetworkCostSnapshot
    from cloud_edge_robot_arm.vision.risk.models import RiskEstimate, RiskFeatures


class DecisionAction(StrEnum):
    CONTINUE = "CONTINUE"
    REOBSERVE = "REOBSERVE"
    LOCAL_RECOVER = "LOCAL_RECOVER"
    REQUEST_CLOUD = "REQUEST_CLOUD"
    STOP = "STOP"


class DecisionEventKind(StrEnum):
    SKILL_BOUNDARY = "SKILL_BOUNDARY"
    EVIDENCE_INVALIDATED = "EVIDENCE_INVALIDATED"
    ANOMALY = "ANOMALY"
    CLOUD_RETURN = "CLOUD_RETURN"
    SUPERVISION_TICK = "SUPERVISION_TICK"
    RESULT_VERIFIED = "RESULT_VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


@dataclass(frozen=True)
class DecisionEvent:
    event_id: str
    kind: DecisionEventKind
    occurred_at: datetime
    observation_id: str
    atomic_action_active: bool
    verification_status: ConditionStatus

    def __post_init__(self) -> None:
        if not self.event_id or not self.observation_id:
            raise ValueError("decision event requires event and observation identities")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include timezone")
        object.__setattr__(self, "kind", DecisionEventKind(self.kind))
        object.__setattr__(self, "verification_status", ConditionStatus(self.verification_status))


_FORBIDDEN_ONLINE_KEYS = frozenset(
    {
        "oracle",
        "ground_truth",
        "ground_truth_used_for_control",
        "fault_schedule",
        "future_fault",
        "future_faults",
        "true_target_coordinates",
        "true_target_position",
        "physical_outcome",
        "success_label",
        "recoverability_label",
    }
)
_FORBIDDEN_SOURCES = frozenset({"oracle", "ground_truth", "physical_evaluator", "offline_teacher"})


def _freeze_online(value: Any) -> Any:
    if isinstance(value, Mapping):
        frozen = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in _FORBIDDEN_ONLINE_KEYS:
                # A transport marker explicitly declaring no oracle use is allowed.
                if lowered != "ground_truth_used_for_control" or item is not False:
                    raise ValueError("online decision context cannot contain oracle/future labels")
            if lowered == "source" and isinstance(item, str) and item.lower() in _FORBIDDEN_SOURCES:
                raise ValueError("online decision context cannot contain offline sources")
            frozen[key] = _freeze_online(item)
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_online(item) for item in value)
    return value


@dataclass(frozen=True)
class DecisionContext:
    """统一运行中决策输入，绑定当前观测和版本并拒绝离线真值。"""

    task_id: str
    episode_id: str
    mode: ControlMode
    mode_version: int
    plan_version: int
    command_seq: int
    event: DecisionEvent
    online_evidence: OnlineEvidenceSnapshot
    evidence_verdict: EvidenceVerdict
    condition_verdicts: Sequence[ConditionVerdict]
    risk_features: RiskFeatures
    risk_estimate: RiskEstimate
    network_cost: NetworkCostSnapshot
    capabilities: set[DecisionAction]
    verification_budget: VerificationBudgetState
    legacy_rule_evidence: LegacyRuleEvidence | None = None

    def __post_init__(self) -> None:
        observation = self.online_evidence.observation
        if not self.task_id or not self.episode_id or observation.episode_id != self.episode_id:
            raise ValueError("decision identity requires the current task and episode")
        if (
            self.event.observation_id != observation.observation_id
            or self.risk_features.observation_id != observation.observation_id
        ):
            raise ValueError("decision observation identity mismatch")
        if any(
            type(value) is not int or value < 0
            for value in (self.mode_version, self.plan_version, self.command_seq)
        ):
            raise ValueError("decision versions must be nonnegative integers")
        if (
            self.online_evidence.plan_version != self.plan_version
            or self.online_evidence.command_seq != self.command_seq
            or not self.online_evidence.context_hash
        ):
            raise ValueError("decision online evidence version/context mismatch")
        if any(
            verdict.observation_id != observation.observation_id
            for verdict in self.condition_verdicts
        ):
            raise ValueError("condition observation identity mismatch")
        object.__setattr__(
            self,
            "risk_estimate",
            replace(
                self.risk_estimate,
                failure_probability_by_action=MappingProxyType(
                    dict(self.risk_estimate.failure_probability_by_action)
                ),
            ),
        )
        object.__setattr__(self, "mode", ControlMode(self.mode))
        object.__setattr__(
            self, "capabilities", frozenset(DecisionAction(v) for v in self.capabilities)
        )
        object.__setattr__(
            self,
            "condition_verdicts",
            tuple(
                replace(
                    verdict,
                    measured_values=_freeze_online(verdict.measured_values),
                    reasons=tuple(verdict.reasons),
                )
                for verdict in self.condition_verdicts
            ),
        )
        object.__setattr__(
            self,
            "online_evidence",
            replace(
                self.online_evidence,
                visual_facts=_freeze_online(self.online_evidence.visual_facts),
                robot_state=self.online_evidence.robot_state.model_copy(deep=True),
            ),
        )


class RuntimeDecisionPolicy(Protocol):
    """只输出现有动作枚举的共同策略接口，不包含执行器或dispatch。"""

    def decide(self, context: DecisionContext) -> DecisionAction:
        """根据同一在线上下文选择一个动作；真正执行仍需提交和安全验证。"""
        ...
