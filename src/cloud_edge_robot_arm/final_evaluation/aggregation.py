"""Phase 12 聚合工具。

聚合阶段读取 raw runs，按模式、实验和后端生成统计摘要，同时保留失败与环境阻塞数量。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.final_evaluation.models import (
    HardwareClaims,
    Phase12Aggregate,
    Phase12Profile,
    Phase12RunStatus,
)
from cloud_edge_robot_arm.final_evaluation.statistics import (
    compute_group_statistics,
    paired_difference_summary,
    success_rate_interval,
)


def load_raw_runs(output_root: Path) -> list[dict[str, Any]]:
    """读取 Phase 12 JSONL 原始运行。"""

    path = output_root / "runs/raw_runs.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def aggregate_results(profile: Phase12Profile, rows: list[dict[str, Any]]) -> Phase12Aggregate:
    """生成聚合模型，硬件声明始终保持软件/仿真边界。"""

    success_count = sum(1 for row in rows if row.get("status") == Phase12RunStatus.SUCCESS.value)
    blocked = sum(1 for row in rows if row.get("status") == Phase12RunStatus.BLOCKED_BY_ENV.value)
    failed = len(rows) - success_count - blocked
    return Phase12Aggregate(
        profile=profile,
        run_count=len(rows),
        success_count=success_count,
        failed_count=failed,
        blocked_by_env_count=blocked,
        unsafe_command_execution_count=sum(
            int(row.get("unsafe_command_execution_count", 0)) for row in rows
        ),
        by_mode=_group_payload(rows, "control_mode"),
        by_experiment=_group_payload(rows, "experiment_id"),
        by_backend=_group_payload(rows, "backend"),
        hardware_claims=HardwareClaims(),
    )


def write_aggregate(output_root: Path, profile: Phase12Profile) -> dict[str, Any]:
    """读取 raw runs 并写出 aggregate、paired 和 summary artifact。"""

    rows = load_raw_runs(output_root)
    aggregate = aggregate_results(profile, rows)
    output_dir = output_root / "aggregates"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = aggregate.model_dump(mode="json")
    (output_dir / "phase12_aggregate.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    paired = _paired_payload(rows)
    paired_dir = output_root / "paired"
    paired_dir.mkdir(parents=True, exist_ok=True)
    (paired_dir / "paired_summary.json").write_text(
        json.dumps(paired, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"aggregate": payload, "paired": paired}


def _group_payload(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    stats = compute_group_statistics(rows, group_key=key, metric_key="total_completion_time_ms")
    counters: dict[str, Counter[str]] = {}
    for row in rows:
        label = str(row.get(key))
        counters.setdefault(label, Counter())[str(row.get("status"))] += 1
    for label, counter in counters.items():
        total = sum(counter.values())
        successes = counter.get(Phase12RunStatus.SUCCESS.value, 0)
        low, high = success_rate_interval(successes, total)
        stats.setdefault(label, {})
        stats[label].update(
            {
                "run_count": total,
                "success_count": successes,
                "success_rate": successes / total if total else 0.0,
                "success_rate_ci95": [low, high],
                "status_counts": dict(counter),
            }
        )
    return stats


def _paired_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    by_key: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("experiment_id") != "F15_MUJOCO_ISAAC_PAIRED":
            continue
        key = f"{row.get('scenario_id')}|{row.get('seed')}|{row.get('control_mode')}"
        by_key.setdefault(key, []).append(row)
    for key, items in sorted(by_key.items()):
        left = next((item for item in items if item.get("backend") == "MUJOCO"), None)
        right = next((item for item in items if item.get("backend") == "ISAAC_SIM"), None)
        if left is None or right is None:
            continue
        pairs.append(
            {
                "pairing_key": key,
                "left_value": left["total_completion_time_ms"],
                "right_value": right["total_completion_time_ms"],
                "left_status": left["status"],
                "right_status": right["status"],
            }
        )
    return paired_difference_summary(pairs)
