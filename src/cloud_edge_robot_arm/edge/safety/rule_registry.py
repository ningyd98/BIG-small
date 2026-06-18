"""安全规则注册表。

注册表按优先级汇总规则结果，急停/拒绝优先于允许，保证最保守决策。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from cloud_edge_robot_arm.contracts import SafetyDecision
from cloud_edge_robot_arm.edge.safety.models import SafetyRuleResult

DECISION_PRIORITY: dict[SafetyDecision, int] = {
    SafetyDecision.EMERGENCY_STOP: 6,
    SafetyDecision.REJECT: 5,
    SafetyDecision.PAUSE: 4,
    SafetyDecision.REQUEST_CORRECTION: 3,
    SafetyDecision.ALLOW_WITH_LIMITS: 2,
    SafetyDecision.ALLOW: 1,
}


@dataclass
class RuleRegistry:
    _rules: list[SafetyRuleEvaluator] = field(default_factory=list)

    def register(self, rule: SafetyRuleEvaluator) -> None:
        self._rules.append(rule)

    def evaluate_all(self, context: object) -> list[SafetyRuleResult]:
        results: list[SafetyRuleResult] = []
        for rule in self._rules:
            result = rule.evaluate(context)
            results.append(result)
        return results

    @property
    def rule_count(self) -> int:
        return len(self._rules)


class SafetyRuleEvaluator(Protocol):
    rule_id: str = "BASE_RULE"

    def evaluate(self, context: object) -> SafetyRuleResult: ...


def resolve_decision(results: list[SafetyRuleResult]) -> SafetyDecision:
    if not results:
        return SafetyDecision.ALLOW
    best = max(results, key=lambda r: DECISION_PRIORITY.get(r.decision, 0))
    return best.decision
