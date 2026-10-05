"""预注册配对非劣功效设计；不使用先导效应方向选择样本量。"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Any

FORMAL_NS = (600, 1200, 1800, 2400)
FAMILY_SIZE = 5
PILOT_N = 120


@dataclass(frozen=True)
class PowerDecision:
    """条件代入功效和散列绑定先导之外的统计不确定性分别报告。"""

    selected_n: int | None
    power_by_n: Mapping[int, Mapping[str, float]]
    reason: str
    discordance_rate: Mapping[str, float] = field(default_factory=dict)
    discordance_upper_bound: Mapping[str, float] = field(default_factory=dict)
    family_alpha: float = 0.01
    assumed_effect: float = 0.0
    estimate_kind: str = "CONDITIONAL_PLUGIN_ZERO_EFFECT"
    source_accepted: bool = False


def _discordance(values: Sequence[tuple[bool, bool]]) -> tuple[int, float]:
    if len(values) != PILOT_N:
        raise ValueError("power pilot requires exactly 120 paired outcomes")
    if any(len(row) != 2 or any(type(value) is not bool for value in row) for row in values):
        raise ValueError("power pilot must contain complete boolean pairs")
    count = sum(left != right for left, right in values)
    return count, count / PILOT_N


def _discordance_upper(count: int, *, alpha: float = 0.05) -> float:
    # Exact one-sided Clopper-Pearson bound: P_p(X <= observed) = alpha.
    # This is uncertainty reporting only, never an unregistered design rule.
    if count == PILOT_N:
        return 1.0
    lo, hi = count / PILOT_N, 1.0
    for _ in range(80):
        probability = (lo + hi) / 2
        cdf = sum(
            math.comb(PILOT_N, k) * probability**k * (1 - probability) ** (PILOT_N - k)
            for k in range(count + 1)
        )
        if cdf > alpha:
            lo = probability
        else:
            hi = probability
    return (lo + hi) / 2


def _conditional_power(n: int, q: float, margin: float, family_alpha: float) -> float:
    if q == 0:
        # At the NI null boundary, a nonzero mean difference of margin requires
        # at least margin discordance. All-concordant probability is maximized
        # by q=margin: (1-margin)**N. Under the explicitly assumed q=0,
        # zero-effect alternative all pairs agree, so conditional power is 0/1.
        return float((1 - margin) ** n <= family_alpha)
    critical = NormalDist().inv_cdf(1 - family_alpha)
    return NormalDist().cdf(margin * math.sqrt(n / q) - critical)


def choose_formal_n(
    paired_success: Sequence[tuple[bool, bool]],
    paired_safety: Sequence[tuple[bool, bool]],
    alpha: float = 0.05,
    target_power: float = 0.8,
) -> PowerDecision:
    """只从固定 N 候选选择两项条件功效均达标的最小样本量。"""
    if alpha != 0.05 or target_power != 0.8:
        raise ValueError("alpha and target power are fixed by the approved protocol")
    success_count, success_q = _discordance(paired_success)
    safety_count, safety_q = _discordance(paired_safety)
    family_alpha = alpha / FAMILY_SIZE
    powers = {
        n: {
            "success": _conditional_power(n, success_q, 0.03, family_alpha),
            "safety": _conditional_power(n, safety_q, 0.01, family_alpha),
        }
        for n in FORMAL_NS
    }
    selected = next(
        (
            n
            for n, values in powers.items()
            if all(value >= target_power for value in values.values())
        ),
        None,
    )
    return PowerDecision(
        selected,
        powers,
        "smallest allowed N meeting both conditional design powers"
        if selected
        else "INSUFFICIENT_EVIDENCE: conditional design power requires N above 2400",
        {"success": success_q, "safety": safety_q},
        {"success": _discordance_upper(success_count), "safety": _discordance_upper(safety_count)},
        family_alpha=family_alpha,
    )


def choose_formal_n_from_pilot(
    rows: Sequence[Mapping[str, Any]],
    *,
    excluded_groups: set[str],
    method_hashes: Mapping[str, str],
) -> PowerDecision:
    """核对先导组与方法身份后计算条件功效；不凭摘要验收物理来源。"""
    if len(rows) != PILOT_N:
        raise ValueError("power pilot requires exactly 120 source groups")
    groups = [row.get("group_id") for row in rows]
    if any(not isinstance(value, str) or not value for value in groups) or (
        len(set(groups)) != PILOT_N or set(groups) & excluded_groups
    ):
        raise ValueError("power pilot source group isolation failed")
    if set(method_hashes) != {"B0", "JOINT"}:
        raise ValueError("power pilot must bind the B0 and JOINT frozen method pair")
    success, safety = [], []
    for row in rows:
        if row.get("split_role") != "power":
            raise ValueError("power pilot cannot use foundation, selection or formal groups")
        if row.get("method_hashes") != dict(method_hashes):
            raise ValueError("power pilot method versions changed")
        sources = row.get("source_hashes")
        if (
            not isinstance(sources, list)
            or not sources
            or any(
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdef" for char in value)
                for value in sources
            )
        ):
            raise ValueError("power pilot source hashes missing")
        success.append(tuple(row.get("success", ())))
        safety.append(tuple(row.get("safety", ())))
    # Full source acceptance is a separate verifier/integration prerequisite.
    # Merely having boolean outcomes and source hashes cannot publish FINAL.
    return choose_formal_n(success, safety)  # type: ignore[arg-type]
