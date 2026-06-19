"""Phase 12 聚合工具。

聚合阶段读取 raw runs，按模式、实验和后端生成统计摘要，同时保留失败与环境阻塞数量。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.final_evaluation.models import (
    ACTUAL_RUN_COUNT_SEMANTICS,
    ExecutionSource,
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

    authoritative_rows = [row for row in rows if row.get("authoritative_for_thesis") is True]
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
        synthetic_sample_count=sum(
            1
            for row in rows
            if row.get("execution_source") == ExecutionSource.SYNTHETIC_PIPELINE_SAMPLE.value
        ),
        actual_run_count_semantics=ACTUAL_RUN_COUNT_SEMANTICS,
        actual_run_count=sum(1 for row in rows if row.get("runtime_invoked") is True),
        adapter_attempt_count=sum(1 for row in rows if row.get("adapter_attempted") is True),
        runtime_invocation_count=sum(1 for row in rows if row.get("runtime_invoked") is True),
        runtime_completion_count=sum(1 for row in rows if row.get("runtime_completed") is True),
        blocked_before_runtime_count=sum(
            1
            for row in rows
            if row.get("status") == Phase12RunStatus.BLOCKED_BY_ENV.value
            and row.get("environment_check_completed") is True
            and row.get("runtime_invoked") is not True
        ),
        authoritative_thesis_run_count=len(authoritative_rows),
        by_mode=_group_payload(rows, "control_mode"),
        by_experiment=_group_payload(rows, "experiment_id"),
        by_backend=_group_payload(rows, "backend"),
        authoritative_by_mode=_group_payload(authoritative_rows, "control_mode"),
        authoritative_by_experiment=_group_payload(authoritative_rows, "experiment_id"),
        authoritative_by_backend=_group_payload(authoritative_rows, "backend"),
        hardware_claims=_aggregate_hardware_claims(rows),
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
    authoritative_counters: Counter[str] = Counter()
    for row in rows:
        label = str(row.get(key))
        counters.setdefault(label, Counter())[str(row.get("status"))] += 1
        if row.get("authoritative_for_thesis") is True:
            authoritative_counters[label] += 1
    for label, counter in counters.items():
        total = sum(counter.values())
        successes = counter.get(Phase12RunStatus.SUCCESS.value, 0)
        low, high = success_rate_interval(successes, total)
        stats.setdefault(label, {})
        stats[label].update(
            {
                "run_count": total,
                "authoritative_run_count": authoritative_counters.get(label, 0),
                "success_count": successes,
                "success_rate": successes / total if total else 0.0,
                "success_rate_ci95": [low, high],
                "status_counts": dict(counter),
            }
        )
    return stats


def _aggregate_hardware_claims(rows: list[dict[str, Any]]) -> HardwareClaims:
    """从 raw runs 聚合硬件声明，避免 aggregate 把异常 evidence 写成默认安全值。"""

    return HardwareClaims(
        real_controller_contacted=_any_hardware_true(rows, "real_controller_contacted"),
        hardware_motion_observed=_any_hardware_true(rows, "hardware_motion_observed"),
        hardware_write_operations=_hardware_write_operations(rows),
        highest_real_hardware_acceptance_level=_highest_hardware_level(rows),
        real_robot_validation=_highest_robot_validation(rows),
    )


def _any_hardware_true(rows: list[dict[str, Any]], key: str) -> bool:
    return any(
        row.get(key, False) is True or row.get("hardware_claims", {}).get(key, False) is True
        for row in rows
    )


def _hardware_write_operations(rows: list[dict[str, Any]]) -> list[str]:
    operations: set[str] = set()
    for row in rows:
        for value in (
            row.get("hardware_write_operations"),
            row.get("hardware_claims", {}).get("hardware_write_operations"),
        ):
            if isinstance(value, list):
                operations.update(str(item) for item in value)
    return sorted(operations)


def _highest_hardware_level(rows: list[dict[str, Any]]) -> str:
    order = {
        "NONE": 0,
        "LEVEL_0": 1,
        "LEVEL_1": 2,
        "LEVEL_2": 3,
        "LEVEL_3": 4,
        "LEVEL_4": 5,
        "LEVEL_5": 6,
        "LEVEL_6": 7,
    }
    return _highest_ordered_value(
        rows,
        "highest_real_hardware_acceptance_level",
        order,
        default="NONE",
    )


def _highest_robot_validation(rows: list[dict[str, Any]]) -> str:
    order = {
        "NOT_STARTED": 0,
        "LEVEL_0_PASSED": 1,
        "LEVEL_1_PASSED": 2,
        "LEVEL_2_PASSED": 3,
        "LEVEL_3_PASSED": 4,
        "LEVEL_4_PASSED": 5,
        "LEVEL_5_PASSED": 6,
        "LEVEL_6_PASSED": 7,
    }
    return _highest_ordered_value(rows, "real_robot_validation", order, default="NOT_STARTED")


def _highest_ordered_value(
    rows: list[dict[str, Any]],
    key: str,
    order: dict[str, int],
    *,
    default: str,
) -> str:
    highest = default
    for row in rows:
        for value in (row.get(key), row.get("hardware_claims", {}).get(key)):
            candidate = str(value or default)
            if order.get(candidate, -1) > order.get(highest, -1):
                highest = candidate
    return highest


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
        pairs.append(
            {
                "pairing_key": key,
                "left_value": left.get("total_completion_time_ms") if left else None,
                "right_value": right.get("total_completion_time_ms") if right else None,
                "left_status": left.get("status") if left else None,
                "right_status": right.get("status") if right else None,
                "left_runtime_completed": left.get("runtime_completed") if left else False,
                "right_runtime_completed": right.get("runtime_completed") if right else False,
                "left_source_artifact_hash": left.get("source_artifact_hash") if left else "",
                "right_source_artifact_hash": right.get("source_artifact_hash") if right else "",
                "left_authoritative": left.get("authoritative_for_thesis") if left else False,
                "right_authoritative": right.get("authoritative_for_thesis") if right else False,
            }
        )
    return paired_difference_summary(pairs)
