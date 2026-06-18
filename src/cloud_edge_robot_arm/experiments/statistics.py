"""实验统计工具。

该模块提供均值、中位数、分位数和 bootstrap 置信区间等论文实验汇总能力。
"""

from __future__ import annotations

import math
import random
from statistics import mean, median

from cloud_edge_robot_arm.experiments.models import MetricSummary


def summarize_values(values: list[float]) -> MetricSummary:
    if not values:
        return MetricSummary(sample_count=0)
    sorted_values = sorted(values)
    p95_index = min(len(sorted_values) - 1, math.ceil(len(sorted_values) * 0.95) - 1)
    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return MetricSummary(
        sample_count=len(values),
        mean=avg,
        standard_deviation=math.sqrt(variance),
        median=median(values),
        p95=sorted_values[p95_index],
        minimum=sorted_values[0],
        maximum=sorted_values[-1],
    )


def success_rate_summary(successes: int, total: int) -> MetricSummary:
    if total <= 0:
        return MetricSummary(sample_count=0, success_rate=None)
    rate = successes / total
    low, high = wilson_interval(successes, total)
    return MetricSummary(
        sample_count=total,
        success_rate=rate,
        confidence_interval_low=low,
        confidence_interval_high=high,
    )


def wilson_interval(successes: int, total: int, *, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        raise ValueError("total must be positive")
    phat = successes / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def bootstrap_mean_ci(
    values: list[float], *, seed: int, samples: int = 1_000
) -> tuple[float, float]:
    if not values:
        raise ValueError("values must not be empty")
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(mean(sample))
    ordered = sorted(means)
    low_index = int(0.025 * (len(ordered) - 1))
    high_index = int(0.975 * (len(ordered) - 1))
    return ordered[low_index], ordered[high_index]
