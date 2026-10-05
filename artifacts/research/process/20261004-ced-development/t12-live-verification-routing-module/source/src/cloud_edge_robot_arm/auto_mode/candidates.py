"""先按在线证据和能力筛选有限动作，候选集合不含执行入口。"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, TypeGuard

from pydantic import BaseModel

from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction, DecisionContext
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionStatus
from cloud_edge_robot_arm.edge.evidence.models import ActionEvidenceContract
from cloud_edge_robot_arm.edge.evidence.validator import validate_evidence


def canonical_value(value: Any) -> Any:
    """将冻结的契约字段规范化为可hash的JSON，不丢弃版本或条件参数。"""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (set, frozenset)):
        return sorted(canonical_value(item) for item in value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): canonical_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [canonical_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: canonical_value(getattr(value, field.name)) for field in fields(value)}
    return value


def content_hash(value: Any) -> str:
    """计算严格有限JSON的内容hash。"""
    return hashlib.sha256(
        json.dumps(
            canonical_value(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ActionCandidate:
    """动作候选保留不可用原因和完整动作证据，选择不代表执行。"""

    candidate_id: str
    action: DecisionAction
    executable: bool
    unavailable_reasons: Sequence[str]
    evidence_contract: ActionEvidenceContract | None

    def __post_init__(self) -> None:
        if not self.candidate_id or type(self.executable) is not bool:
            raise ValueError("candidate requires a nonempty identity and boolean availability")
        object.__setattr__(self, "action", DecisionAction(self.action))
        object.__setattr__(self, "unavailable_reasons", tuple(self.unavailable_reasons))
        if self.evidence_contract is not None:
            object.__setattr__(self, "evidence_contract", replace(self.evidence_contract))
        if not self.executable and not self.unavailable_reasons:
            raise ValueError("unavailable candidate requires reasons")


@dataclass(frozen=True)
class CandidateSet:
    """不可变候选集合绑定动作、可用性、条件及证据的内容hash。"""

    candidates: Sequence[ActionCandidate]
    content_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(self.candidates))
        self.validate()
        if not self.content_hash:
            object.__setattr__(self, "content_hash", self.digest())

    def digest(self) -> str:
        """按候选ID规范排序，输入排列不改变集合hash。"""
        return content_hash(sorted(self.candidates, key=lambda row: row.candidate_id))

    def validate(self) -> None:
        """拒绝重复ID/动作、缺少停止路径以及内容被换绑。"""
        ids = [row.candidate_id for row in self.candidates]
        actions = [row.action for row in self.candidates]
        if len(set(ids)) != len(ids) or len(set(actions)) != len(actions):
            raise ValueError("duplicate candidate identity or action")
        if not any(row.action == DecisionAction.STOP and row.executable for row in self.candidates):
            raise ValueError("STOP must remain an executable candidate")
        if self.content_hash and self.content_hash != self.digest():
            raise ValueError("candidate content hash mismatch")


def _number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _contract_current(context: DecisionContext, contract: ActionEvidenceContract) -> bool:
    observation = context.online_evidence.observation
    evidence = contract.evidence
    return (
        evidence.observation_id == observation.observation_id
        and evidence.captured_at == observation.captured_at
        and evidence.calibration_version == observation.calibration_version
        and contract.plan_version == context.plan_version
        and contract.command_seq == context.command_seq
        and contract.context_hash == context.online_evidence.context_hash
    )


def fresh_cloud_input(
    context: DecisionContext,
    contracts: Mapping[DecisionAction, ActionEvidenceContract],
    now: datetime,
) -> bool:
    """云观测请求需要当前帧的真实TTL，但不授予任何物理动作权限。"""
    if now.tzinfo is None or now.utcoffset() is None:
        return False
    for contract in contracts.values():
        e = contract.evidence
        if (
            e.captured_at.tzinfo is None
            or e.captured_at.utcoffset() is None
            or not e.calibration_version
            or e.identity_status != "CONFIRMED"
            or e.sensor_status != "VALID"
            or not set(contract.sensor_requirements).issubset(e.available_sensors)
        ):
            continue
        if (
            not _contract_current(context, contract)
            or not _number(contract.ordinary_ttl_s)
            or contract.ordinary_ttl_s <= 0
        ):
            continue
        age = (now - context.online_evidence.observation.captured_at).total_seconds()
        if 0 <= age <= contract.ordinary_ttl_s:
            return True
    return False


def build_candidates(
    context: DecisionContext,
    *,
    action_contracts: Mapping[DecisionAction, ActionEvidenceContract] | None = None,
) -> CandidateSet:
    """按真实当前契约、证据、能力、预算和原子边界生成五个有限候选。"""
    contracts = MappingProxyType(
        {DecisionAction(key): value for key, value in (action_contracts or {}).items()}
    )
    now = context.event.occurred_at
    state = context.online_evidence.robot_state
    budget = context.verification_budget
    hard = (
        state.estop_engaged
        or state.collision_detected
        or not state.connected
        or budget.exhausted_reason is not None
        or now >= budget.deadline_at
        or budget.consecutive_no_progress >= budget.limits.max_no_progress
        or any(
            row.measured_values.get("hard_safety_fault") is True
            for row in context.condition_verdicts
        )
    )
    identity = content_hash(
        {
            "task": context.task_id,
            "episode": context.episode_id,
            "observation": context.event.observation_id,
            "plan": context.plan_version,
            "command": context.command_seq,
            "mode": context.mode_version,
            "context": context.online_evidence.context_hash,
        }
    )
    result = []
    for action in DecisionAction:
        reasons = []
        contract = contracts.get(action)
        if action != DecisionAction.STOP:
            if hard:
                reasons.append("hard_stop_or_budget_exhausted")
            if action not in context.capabilities:
                reasons.append("capability_unavailable")
            if context.event.atomic_action_active:
                reasons.append("ordinary_decision_deferred_atomic")
        if action == DecisionAction.LOCAL_RECOVER:
            reasons.append("recovery_not_accepted_t13")
        elif action == DecisionAction.REOBSERVE and budget.remaining_reobservations <= 0:
            reasons.append("reobservation_budget_exhausted")
        elif action == DecisionAction.REQUEST_CLOUD:
            if not fresh_cloud_input(context, contracts, now):
                reasons.append("cloud_input_ttl_missing_or_expired")
            if (
                any(row.status == ConditionStatus.FAIL for row in context.condition_verdicts)
                or context.event.verification_status == ConditionStatus.FAIL
                or context.evidence_verdict.status == "INVALID"
            ) and budget.remaining_retries <= 0:
                reasons.append("recovery_retry_budget_exhausted")
        elif action == DecisionAction.CONTINUE:
            estimate = context.risk_estimate
            probability = estimate.failure_probability_by_action.get(action.value)
            if (
                estimate.status != "VALID"
                or not _number(probability)
                or probability is None
                or not 0 <= probability <= 1
            ):
                reasons.append("calibrated_action_risk_unavailable")
            if (
                not _number(estimate.geometric_error_bound_m)
                or not _number(estimate.motion_bound_m_s)
                or estimate.geometric_error_bound_m is None
                or estimate.motion_bound_m_s is None
                or min(estimate.geometric_error_bound_m, estimate.motion_bound_m_s) < 0
            ):
                reasons.append("physical_bounds_unknown")
            if (
                context.evidence_verdict.status != "VALID"
                or context.event.verification_status != ConditionStatus.PASS
                or not context.condition_verdicts
                or any(row.status != ConditionStatus.PASS for row in context.condition_verdicts)
            ):
                reasons.append("current_online_evidence_not_valid")
            if contract is None:
                reasons.append("current_action_contract_missing")
            elif not _contract_current(context, contract):
                reasons.append("current_action_contract_identity_mismatch")
            else:
                verdict = validate_evidence(
                    contract,
                    now,
                    context.online_evidence.context_hash,
                    context.online_evidence.observation.calibration_version or "",
                    online_evidence=context.online_evidence,
                )
                if verdict.status != "VALID":
                    reasons.extend(verdict.reasons)
                e = contract.evidence
                if (
                    estimate.geometric_error_bound_m is not None
                    and (
                        not _number(e.geometric_error_bound_m)
                        or e.geometric_error_bound_m < estimate.geometric_error_bound_m
                    )
                    or estimate.motion_bound_m_s is not None
                    and (
                        not _number(e.motion_bound_m_s)
                        or e.motion_bound_m_s < estimate.motion_bound_m_s
                    )
                ):
                    reasons.append("contract_understates_calibrated_bounds")
        result.append(
            ActionCandidate(
                f"{action.value.lower()}-{identity[:24]}",
                action,
                not reasons,
                tuple(reasons),
                contract,
            )
        )
    return CandidateSet(tuple(result), "")
