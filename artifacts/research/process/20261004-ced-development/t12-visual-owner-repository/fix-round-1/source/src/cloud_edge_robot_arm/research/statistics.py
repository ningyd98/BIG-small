"""配对多项得分区间、五假设 Holm 和基础场景簇统计。"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import TYPE_CHECKING, Literal

import numpy as np

if TYPE_CHECKING:
    from cloud_edge_robot_arm.research.assignments import EpisodeRecord


@dataclass(frozen=True)
class EffectEstimate:
    """原始区间与检验结果分列；校正 p 值不能冒充校正区间。"""

    point: float | None
    lower95: float | None
    upper95: float | None
    p_value: float | None
    adjusted_p_value: float | None
    denominator: int
    method: str
    one_sided_lower95: float | None = field(default=None, kw_only=True)
    one_sided_upper95: float | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        if type(self.denominator) is not int or self.denominator < 0 or not self.method:
            raise ValueError("effect denominator/method invalid")
        for value in (
            self.point,
            self.lower95,
            self.upper95,
            self.one_sided_lower95,
            self.one_sided_upper95,
        ):
            if value is not None and not math.isfinite(value):
                raise ValueError("effect estimates must be finite or N/A")
        for value in (self.p_value, self.adjusted_p_value):
            if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError("effect p values must be valid probabilities or N/A")
        if self.lower95 is not None and self.upper95 is not None and self.lower95 > self.upper95:
            raise ValueError("effect interval order invalid")


def _counts(pairs: Sequence[tuple[bool, bool]]) -> tuple[int, int, int]:
    if not pairs or any(
        not isinstance(row, (tuple, list))
        or len(row) != 2
        or any(type(value) is not bool for value in row)
        for row in pairs
    ):
        raise ValueError("paired binary inference requires nonempty strict boolean pairs")
    plus = sum(left and not right for left, right in pairs)
    minus = sum(right and not left for left, right in pairs)
    return plus, minus, len(pairs) - plus - minus


def _null_q(plus: int, minus: int, zero: int, delta: float) -> float:
    # Multinomial likelihood for P(D=+1)=(q+delta)/2,
    # P(D=-1)=(q-delta)/2, P(D=0)=1-q. Maximizing over q gives
    # n*q^2 - [discord+(plus-minus)*delta]*q
    # - [(minus-plus)*delta + zero*delta^2] = 0, constrained q>=|delta|.
    n = plus + minus + zero
    b = plus + minus + (plus - minus) * delta
    c = (minus - plus) * delta + zero * delta * delta
    discriminant = max(0.0, b * b + 4 * n * c)
    q = (b + math.sqrt(discriminant)) / (2 * n)
    return min(1.0, max(abs(delta), q))


def _score(counts: tuple[int, int, int], delta: float) -> float:
    plus, minus, zero = counts
    n = plus + minus + zero
    difference = (plus - minus) / n - delta
    variance = _null_q(plus, minus, zero, delta) - delta * delta
    if difference == 0:
        return 0.0
    if variance <= 0:
        return math.copysign(math.inf, difference)
    return math.sqrt(n) * difference / math.sqrt(variance)


def _score_bounds(counts: tuple[int, int, int], critical: float) -> tuple[float, float]:
    plus, minus, zero = counts
    point = (plus - minus) / (plus + minus + zero)
    lower, upper = -1.0, 1.0
    if _score(counts, -1.0) > critical:
        lo, hi = -1.0, point
        for _ in range(80):
            mid = (lo + hi) / 2
            if _score(counts, mid) > critical:
                lo = mid
            else:
                hi = mid
        lower = (lo + hi) / 2
    if _score(counts, 1.0) < -critical:
        lo, hi = point, 1.0
        for _ in range(80):
            mid = (lo + hi) / 2
            if _score(counts, mid) < -critical:
                hi = mid
            else:
                lo = mid
        upper = (lo + hi) / 2
    return lower, upper


def paired_binary_effect(
    pairs: Sequence[tuple[bool, bool]],
    *,
    null_difference: float = 0.0,
    alternative: Literal["two-sided", "greater", "less"] = "two-sided",
) -> EffectEstimate:
    """按 JOINT−基线的匹配二项差计算受约束多项得分区间/检验。"""
    if not math.isfinite(null_difference) or not -1 <= null_difference <= 1:
        raise ValueError("paired binary null difference invalid")
    if alternative not in {"two-sided", "greater", "less"}:
        raise ValueError("paired binary alternative invalid")
    counts = _counts(pairs)
    plus, minus, _ = counts
    lower, upper = _score_bounds(counts, NormalDist().inv_cdf(0.975))
    lower_one, upper_one = _score_bounds(counts, NormalDist().inv_cdf(0.95))
    score = _score(counts, null_difference)
    p_value = (
        math.erfc(abs(score) / math.sqrt(2))
        if alternative == "two-sided"
        else (
            0.5 * math.erfc(score / math.sqrt(2))
            if alternative == "greater"
            else 0.5 * math.erfc(-score / math.sqrt(2))
        )
    )
    return EffectEstimate(
        (plus - minus) / len(pairs),
        lower,
        upper,
        p_value,
        None,
        len(pairs),
        "MATCHED_MULTINOMIAL_CONSTRAINED_SCORE_80_BISECTIONS",
        one_sided_lower95=lower_one,
        one_sided_upper95=upper_one,
    )


def zero_event_upper_bound(n: int, alpha: float = 0.05) -> float:
    """零事件的精确单侧二项上界；零观察不意味着风险为零。"""
    if type(n) is not int or n <= 0 or not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("zero event bound requires positive independent N and valid alpha")
    return -math.expm1(math.log(alpha) / n)


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """对整个预声明假设族进行逐步 Holm 校正并保持原始键。"""
    if not p_values or any(
        not math.isfinite(value) or not 0 <= value <= 1 for value in p_values.values()
    ):
        raise ValueError("Holm requires nonempty finite p values in [0,1]")
    ordered = sorted(p_values, key=lambda key: (p_values[key], key))
    adjusted = {}
    running = 0.0
    for index, key in enumerate(ordered):
        running = max(running, min(1.0, p_values[key] * (len(ordered) - index)))
        adjusted[key] = running
    return {key: adjusted[key] for key in p_values}


def _value(record: EpisodeRecord, metric: str) -> float:
    if metric.startswith("cloud_requests"):
        return float(record.costs.cloud_model_requests)
    if metric.startswith("application_bytes"):
        return float(record.costs.application_bytes)
    if metric.startswith("duration_penalized_s"):
        return record.duration_penalized_s
    if metric.startswith("decision_latency_s"):
        return record.costs.decision_latency_s
    if metric.startswith("recovery_duration_s"):
        # Before raw independent recovery validation, no declaration shortens Rcap.
        return 60.0
    raise ValueError("unsupported prespecified bootstrap metric")


def _paired_groups(
    records: Sequence[EpisodeRecord],
    metric: str,
    baseline: str,
    joint: str,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    ids = [record.assignment.assignment_id for record in records]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate assignment cannot create extra independent samples")
    groups: dict[str, dict[str, list[EpisodeRecord]]] = defaultdict(lambda: defaultdict(list))
    for record in records:
        if record.assignment.method_id in {baseline, joint}:
            groups[record.assignment.group_id][record.assignment.method_id].append(record)
    if not groups:
        raise ValueError("paired group records missing")
    x, y, strata = [], [], []
    for group in sorted(groups):
        methods = groups[group]
        if set(methods) != {baseline, joint}:
            raise ValueError("all groups must retain paired method records")
        layer = {record.assignment.stratum_id for rows in methods.values() for record in rows}
        if len(layer) != 1:
            raise ValueError("paired base group crosses strata")
        schedules = [
            Counter(
                (record.assignment.physics_seed, record.assignment.network_schedule_id)
                for record in methods[method]
            )
            for method in (baseline, joint)
        ]
        if schedules[0] != schedules[1] or len(methods[baseline]) != len(methods[joint]):
            raise ValueError("paired scene seeds or network schedules differ")
        # Repeated seeds remain inside the base scene cluster, never extra N.
        x.append(float(np.mean([_value(record, metric) for record in methods[baseline]])))
        y.append(float(np.mean([_value(record, metric) for record in methods[joint]])))
        strata.append(next(iter(layer)))
    return np.asarray(x), np.asarray(y), strata


def _aggregate(x: np.ndarray, y: np.ndarray, metric: str) -> np.ndarray:
    if "_p95" in metric:
        base, joint = np.quantile(x, 0.95, axis=-1), np.quantile(y, 0.95, axis=-1)
    elif "_median" in metric:
        base, joint = np.median(x, axis=-1), np.median(y, axis=-1)
    else:
        base, joint = np.mean(x, axis=-1), np.mean(y, axis=-1)
    if metric.endswith("_relative_reduction"):
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.asarray(np.where(base != 0, (base - joint) / base, np.nan))
    return np.asarray(joint - base)


def _permutation_p(
    x: np.ndarray,
    y: np.ndarray,
    metric: str,
    point: float,
    iterations: int,
    seed: int,
) -> float | None:
    n = len(x)
    exact = n <= 16
    total = 2**n if exact else iterations
    rng = np.random.default_rng(seed)
    extreme = 0
    for start in range(0, total, 256):
        count = min(256, total - start)
        if exact:
            indices = np.arange(start, start + count, dtype=np.uint64)[:, None]
            swap = ((indices >> np.arange(n, dtype=np.uint64)) & 1).astype(bool)
        else:
            swap = rng.integers(0, 2, size=(count, n)).astype(bool)
        permuted = _aggregate(np.where(swap, y, x), np.where(swap, x, y), metric)
        if not np.all(np.isfinite(permuted)):
            return None
        if metric.endswith("_relative_reduction"):
            extreme += int(np.count_nonzero(permuted >= point - 1e-12))
        else:
            extreme += int(np.count_nonzero(permuted <= point + 1e-12))
    return extreme / total if exact else (extreme + 1) / (total + 1)


def stratified_paired_bootstrap(
    records: Sequence[EpisodeRecord],
    metric: str,
    iterations: int = 10000,
    seed: int = 20261003,
    *,
    baseline_method: str = "B0",
    joint_method: str = "JOINT",
) -> EffectEstimate:
    """按基础场景簇在每层配对重采样，不把帧或重复种子增加独立 N。"""
    if type(iterations) is not int or iterations < 10000:
        raise ValueError("paired stratified bootstrap requires at least 10000 iterations")
    x, y, strata = _paired_groups(records, metric, baseline_method, joint_method)
    return _bootstrap_arrays(x, y, strata, metric, iterations, seed)


def clustered_rate_reduction(
    counts: Sequence[tuple[float, float]],
    strata: Sequence[str],
    iterations: int = 10000,
    seed: int = 20261003,
) -> EffectEstimate:
    """固定机会在基础场景内汇总事件数，配对公共分母不因方法变化。"""
    if (
        not counts
        or len(counts) != len(strata)
        or any(
            len(pair) != 2 or any(not math.isfinite(value) or value < 0 for value in pair)
            for pair in counts
        )
        or any(not value for value in strata)
    ):
        raise ValueError("clustered opportunity counts/strata invalid")
    if type(iterations) is not int or iterations < 10000:
        raise ValueError("clustered rate bootstrap requires at least 10000 iterations")
    x = np.asarray([base for base, _ in counts], dtype=float)
    y = np.asarray([joint for _, joint in counts], dtype=float)
    return _bootstrap_arrays(
        x, y, list(strata), "cloud_requests_relative_reduction", iterations, seed
    )


def _bootstrap_arrays(
    x: np.ndarray,
    y: np.ndarray,
    strata: Sequence[str],
    metric: str,
    iterations: int,
    seed: int,
) -> EffectEstimate:
    point = float(_aggregate(x, y, metric))
    method = "STRATIFIED_PAIRED_BASE_GROUP_PERCENTILE_WITH_LABEL_EXCHANGE_TEST"
    if not math.isfinite(point):
        return EffectEstimate(None, None, None, None, None, len(x), method + "_BASELINE_ZERO")
    layers = [
        np.asarray([i for i, value in enumerate(strata) if value == layer])
        for layer in sorted(set(strata))
    ]
    rng = np.random.default_rng(seed)
    draws = []
    for start in range(0, iterations, 256):
        count = min(256, iterations - start)
        sampled = np.concatenate(
            [rng.choice(layer, size=(count, len(layer))) for layer in layers], axis=1
        )
        draws.extend(_aggregate(x[sampled], y[sampled], metric).tolist())
    estimates = np.asarray(draws)
    if not np.all(np.isfinite(estimates)):
        return EffectEstimate(
            point, None, None, None, None, len(x), method + "_UNDEFINED_RESAMPLES"
        )
    lower, upper = (float(value) for value in np.quantile(estimates, [0.025, 0.975]))
    one_lower, one_upper = (float(value) for value in np.quantile(estimates, [0.05, 0.95]))
    p = _permutation_p(x, y, metric, point, iterations, seed + 1)
    return EffectEstimate(
        point,
        lower,
        upper,
        p,
        None,
        len(x),
        method,
        one_sided_lower95=one_lower,
        one_sided_upper95=one_upper,
    )
