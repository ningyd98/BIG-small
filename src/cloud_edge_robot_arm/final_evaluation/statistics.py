"""Phase 12 统计分析工具。

这里实现描述统计、置信区间、effect size 和配对差异汇总。失败、超时和
BLOCKED_BY_ENV 样本会被单独计数，不会被静默删除。
"""

from __future__ import annotations

import math
from statistics import mean, median
from typing import Any


def compute_group_statistics(
    rows: list[dict[str, Any]], *, group_key: str, metric_key: str
) -> dict[str, dict[str, Any]]:
    """按组计算统计量，并保留 blocked/failed 计数和 effect size。"""

    rows_for_metric = [_metric_eligible_row(row, metric_key) for row in rows]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows_for_metric:
        grouped.setdefault(str(row[group_key]), []).append(row)
    all_values = [
        value
        for value in (_to_float(row.get(metric_key)) for row in rows_for_metric)
        if value is not None
    ]
    overall_mean = mean(all_values) if all_values else 0.0
    overall_std = _stddev(all_values)
    result: dict[str, dict[str, Any]] = {}
    for label, items in sorted(grouped.items()):
        values = [
            value
            for value in (_to_float(row.get(metric_key)) for row in items)
            if value is not None
        ]
        blocked = sum(1 for row in items if row.get("status") == "BLOCKED_BY_ENV")
        failed = sum(
            1 for row in items if row.get("status") in {"FAILED", "TIMEOUT", "SAFETY_STOPPED"}
        )
        all_group_rows = [row for row in rows if str(row.get(group_key)) == label]
        excluded = sum(1 for row in all_group_rows if not _metric_is_eligible(row, metric_key))
        summary = _summarize_values(values)
        effect = None
        summary_mean = summary["mean"]
        if isinstance(summary_mean, int | float) and overall_std > 0:
            effect = (float(summary_mean) - overall_mean) / overall_std
        result[label] = {
            **summary,
            "valid_metric_sample_count": summary["sample_count"],
            "excluded_metric_sample_count": excluded,
            "blocked_by_env_count": blocked,
            "failed_count": failed,
            "effect_size_vs_overall": effect,
        }
    return result


def paired_difference_summary(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """计算配对差异；不可用 pair 只排除数值差异计算，但仍计入审计。"""

    usable: list[float] = []
    blocked = 0
    failed = 0
    for pair in pairs:
        statuses = {str(pair.get("left_status")), str(pair.get("right_status"))}
        if "BLOCKED_BY_ENV" in statuses:
            blocked += 1
        if statuses.intersection({"FAILED", "TIMEOUT", "SAFETY_STOPPED"}):
            failed += 1
        if "BLOCKED_BY_ENV" in statuses:
            continue
        if statuses != {"SUCCESS"}:
            continue
        if (
            pair.get("left_authoritative") is not True
            or pair.get("right_authoritative") is not True
        ):
            failed += 1
            continue
        left = _to_float(pair.get("left_value"))
        right = _to_float(pair.get("right_value"))
        if left is None or right is None:
            failed += 1
            continue
        usable.append(left - right)
    summary = _summarize_values(usable)
    return {
        "pair_count": len(pairs),
        "usable_pair_count": len(usable),
        "usable_authoritative_pair_count": len(usable),
        "blocked_by_env_count": blocked,
        "blocked_pair_count": blocked,
        "failed_pair_count": failed,
        "paired_row_structure_complete": all(
            pair.get("left_status") is not None and pair.get("right_status") is not None
            for pair in pairs
        ),
        "expected_pair_count": len(pairs),
        "paired_backend_experiment_accepted": bool(pairs) and len(usable) == len(pairs),
        "mean_delta": summary["mean"],
        "median_delta": summary["median"],
        "confidence_interval_95": summary["confidence_interval_95"],
        "effect_size": _cohens_d(usable),
    }


def success_rate_interval(successes: int, total: int) -> tuple[float, float]:
    """Wilson 区间用于二项成功率，避免只报告单点成功率。"""

    if total <= 0:
        return 0.0, 0.0
    z = 1.96
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _summarize_values(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "sample_count": 0,
            "mean": None,
            "median": None,
            "standard_deviation": None,
            "minimum": None,
            "maximum": None,
            "p25": None,
            "p75": None,
            "p95": None,
            "confidence_interval_95": None,
        }
    ordered = sorted(values)
    avg = mean(ordered)
    std = _stddev(ordered)
    ci_margin = 1.96 * std / math.sqrt(len(ordered)) if len(ordered) > 1 else 0.0
    return {
        "sample_count": len(ordered),
        "mean": avg,
        "median": median(ordered),
        "standard_deviation": std,
        "minimum": ordered[0],
        "maximum": ordered[-1],
        "p25": _percentile(ordered, 0.25),
        "p75": _percentile(ordered, 0.75),
        "p95": _percentile(ordered, 0.95),
        "confidence_interval_95": [avg - ci_margin, avg + ci_margin],
    }


def _stddev(values: list[float]) -> float:
    if len(values) <= 1:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def _cohens_d(values: list[float]) -> float | None:
    if len(values) <= 1:
        return None
    std = _stddev(values)
    return mean(values) / std if std > 0 else None


def _percentile(ordered: list[float], ratio: float) -> float:
    if not ordered:
        raise ValueError("ordered values must not be empty")
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * ratio) - 1))
    return ordered[index]


def _to_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _metric_eligible_row(row: dict[str, Any], metric_key: str) -> dict[str, Any]:
    return row if _metric_is_eligible(row, metric_key) else {**row, metric_key: None}


def _metric_is_eligible(row: dict[str, Any], metric_key: str) -> bool:
    if row.get("authoritative_for_thesis") is not True:
        return False
    provenance = row.get("metric_provenance", {})
    if "metric_provenance" not in row:
        return True
    if not isinstance(provenance, dict):
        return False
    metric = provenance.get(metric_key)
    if not isinstance(metric, dict):
        return False
    return metric.get("source") in {"MEASURED", "EVENT_DERIVED"}
