from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import yaml

from cloud_edge_robot_arm.contracts import SafetyDecision
from cloud_edge_robot_arm.edge.safety.context_builder import SafetyContextBuilder
from cloud_edge_robot_arm.edge.safety.errors import SAFETY_BYPASS_REJECTED, safety_error
from cloud_edge_robot_arm.edge.safety.models import (
    HardSafetyLimits,
    SafetyContext,
    SafetyEvaluationResult,
)
from cloud_edge_robot_arm.edge.safety.policy import (
    MergedSafetyConstraints,
    OperationalSafetyPolicy,
    merge_constraints,
)
from cloud_edge_robot_arm.edge.safety.rule_registry import RuleRegistry, resolve_decision
from cloud_edge_robot_arm.edge.safety.rules import ALL_RULES


@dataclass(frozen=True)
class SafetyConfig:
    hard_limits: HardSafetyLimits
    operational_policy: OperationalSafetyPolicy
    merged: MergedSafetyConstraints
    policy_version: str
    policy_hash: str


def _policy_hash(policy: OperationalSafetyPolicy, hard: HardSafetyLimits) -> str:
    canonical = json.dumps(
        {"hard": hard.model_dump(), "policy": policy.model_dump()},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def load_safety_config(path: str | None = None) -> SafetyConfig:
    if path is None:
        hard = HardSafetyLimits()
        policy = OperationalSafetyPolicy()
    else:
        with open(path) as f:
            raw = yaml.safe_load(f)
        raw = raw or {}
        hard_raw = raw.get("hard_limits", {})
        policy_raw = raw.get("operational_policy", {})
        hard = HardSafetyLimits(**hard_raw) if hard_raw else HardSafetyLimits()
        lhes_raw = policy_raw.pop("low_height_exception_skills", None)
        policy = OperationalSafetyPolicy(**policy_raw)
        if lhes_raw is not None:
            object.__setattr__(policy, "low_height_exception_skills", frozenset(lhes_raw))

    merged = merge_constraints(hard, policy)
    ph = _policy_hash(policy, hard)
    return SafetyConfig(
        hard_limits=hard,
        operational_policy=policy,
        merged=merged,
        policy_version=policy.policy_version,
        policy_hash=ph,
    )


class SafetyShield:
    def __init__(self, config: SafetyConfig | None = None) -> None:
        self._config = config or load_safety_config()
        self._registry = RuleRegistry()
        for rule_cls in ALL_RULES:
            self._registry.register(rule_cls())

    @property
    def config(self) -> SafetyConfig:
        return self._config

    @property
    def rule_count(self) -> int:
        return self._registry.rule_count

    @property
    def context_builder(self) -> SafetyContextBuilder:
        return SafetyContextBuilder(
            merged=self._config.merged,
            hard_limits=self._config.hard_limits,
        )

    def pre_check(self, context: SafetyContext) -> SafetyEvaluationResult:
        self._reject_bypass_fields(context)
        results = self._registry.evaluate_all(context)
        decision = resolve_decision(results)
        limiting = max(results, key=lambda r: _DECISION_PRIORITY.get(r.decision, 0))
        allowed = decision in {SafetyDecision.ALLOW, SafetyDecision.ALLOW_WITH_LIMITS}
        limited_params: dict[str, object] | None = None
        original_params: dict[str, object] | None = None
        if decision == SafetyDecision.ALLOW_WITH_LIMITS:
            original_params = dict(context.parameters)
            merged_limits = dict(context.parameters)
            for result in results:
                if (
                    result.decision == SafetyDecision.ALLOW_WITH_LIMITS
                    and result.limited_parameters
                ):
                    merged_limits.update(result.limited_parameters)
            limited_params = merged_limits
        return SafetyEvaluationResult(
            allowed=allowed,
            decision=decision,
            evaluated_rules=results,
            limiting_rule=limiting if not allowed else None,
            limited_parameters=limited_params,
            original_parameters=original_params,
        )

    def post_check(self, context: SafetyContext) -> SafetyEvaluationResult:
        return self.pre_check(context)

    def _reject_bypass_fields(self, context: SafetyContext) -> None:
        bypass_keys = {"disable_safety", "bypass_safety", "ignore_collision", "force_execute"}
        for key in bypass_keys:
            if key in context.parameters:
                raise ValueError(
                    safety_error(
                        SAFETY_BYPASS_REJECTED,
                        f"parameter {key!r} is not allowed",
                        details={"rejected_key": key},
                    ).model_dump_json()
                )


_DECISION_PRIORITY: dict[SafetyDecision, int] = {
    SafetyDecision.EMERGENCY_STOP: 6,
    SafetyDecision.REJECT: 5,
    SafetyDecision.PAUSE: 4,
    SafetyDecision.REQUEST_CORRECTION: 3,
    SafetyDecision.ALLOW_WITH_LIMITS: 2,
    SafetyDecision.ALLOW: 1,
}
