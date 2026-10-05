"""论文证据索引构建。

该模块从 Phase 12.2 clean validation artifact、实验注册表和 LLM-only 基线 artifact
派生论文数字、表格索引和结论边界。所有数值均带 source file/source field。
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from cloud_edge_robot_arm.final_evaluation.registry import final_experiment_registry


def build_thesis_evidence(
    *,
    validation_root: Path,
    llm_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """构建论文 evidence JSON，并写入 `thesis/generated`。"""

    output_root.mkdir(parents=True, exist_ok=True)
    rows = _read_jsonl(validation_root / "runs/raw_runs.jsonl")
    summary = _read_json(validation_root / "verification/phase12_summary.json")
    aggregate = _read_json(validation_root / "aggregates/phase12_aggregate.json")
    statistics = _read_json(validation_root / "statistics/phase12_statistics.json")
    paired = _read_json(validation_root / "paired/paired_summary.json")
    llm_summary = _read_optional_json(llm_root / "verification/llm_only_verification.json")
    registry = final_experiment_registry()
    backend_counts = Counter(str(row.get("backend")) for row in rows)
    runtime_backend_counts = Counter(
        str(row.get("backend")) for row in rows if row.get("runtime_invoked") is True
    )
    status_counts = Counter(str(row.get("status")) for row in rows)
    source_counts = Counter(str(row.get("execution_source")) for row in rows)
    mode_counts = Counter(str(row.get("control_mode")) for row in rows)
    experiment_status = _experiment_status(rows)
    metrics = {
        "profile": summary.get("profile", "validation"),
        "status": summary.get("status"),
        "thesis_status": summary.get("thesis_status"),
        "project_status": summary.get("project_status"),
        "run_count": summary.get("run_count"),
        "expected_run_count": summary.get("expected_run_count"),
        "runtime_completion_count": summary.get("runtime_completion_count"),
        "blocked_before_runtime_count": summary.get("blocked_before_runtime_count"),
        "synthetic_sample_count": summary.get("synthetic_sample_count"),
        "authoritative_thesis_run_count": summary.get("authoritative_thesis_run_count"),
        "verifier_gated_authoritative_thesis_run_count": summary.get(
            "verifier_gated_authoritative_thesis_run_count"
        ),
        "usable_authoritative_pair_count": summary.get("usable_authoritative_pair_count"),
        "blocked_pair_count": summary.get("blocked_pair_count"),
        "full_profile_execution_status": summary.get("full_profile_execution_status"),
        "full_profile_readiness_status": summary.get("full_profile_readiness_status"),
        "real_controller_contacted": summary.get("real_controller_contacted"),
        "hardware_motion_observed": summary.get("hardware_motion_observed"),
        "hardware_write_operations": summary.get("hardware_write_operations"),
        "highest_real_hardware_acceptance_level": summary.get(
            "highest_real_hardware_acceptance_level"
        ),
        "unsafe_command_execution_count": summary.get("unsafe_command_execution_count"),
        "backend_counts": dict(backend_counts),
        "runtime_backend_counts": dict(runtime_backend_counts),
        "status_counts": dict(status_counts),
        "source_counts": dict(source_counts),
        "mode_counts": dict(mode_counts),
        "experiment_count": len(experiment_status),
        "experiment_status": experiment_status,
        "by_mode": aggregate.get("authoritative_by_mode", {}),
        "by_backend": aggregate.get("authoritative_by_backend", {}),
        "paired": paired,
        "llm_only": llm_summary or _llm_missing_summary(),
    }
    trace = _claim_trace(metrics, validation_root, llm_root)
    missing = _missing_data_report(metrics)
    figure_index = _figure_index(validation_root)
    table_index = _table_index(validation_root)
    payloads = {
        "thesis_metrics.json": metrics,
        "claim_evidence.json": trace,
        "missing_data_report.json": missing,
        "figure_index.json": figure_index,
        "thesis_tables.json": table_index,
    }
    for name, payload in payloads.items():
        (output_root / name).write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return {
        "metrics": metrics,
        "trace": trace,
        "missing": missing,
        "figure_index": figure_index,
        "table_index": table_index,
        "registry": [item.model_dump(mode="json") for item in registry],
        "statistics": statistics,
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _experiment_status(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    grouped: dict[str, Counter[str]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("experiment_id")), Counter())[str(row.get("status"))] += 1
    return {experiment: dict(counter) for experiment, counter in sorted(grouped.items())}


def _claim_trace(
    metrics: dict[str, Any], validation_root: Path, llm_root: Path
) -> list[dict[str, Any]]:
    """生成关键结论证据追踪矩阵。"""

    validation_summary = "artifacts/phase12_2_clean/validation/verification/phase12_summary.json"
    llm_summary = "artifacts/thesis_baselines/llm_only/verification/llm_only_verification.json"
    items = [
        (
            "第九章",
            "Phase 12 clean validation 已通过",
            "status",
            metrics["status"],
            validation_summary,
            "status",
            "L4",
            True,
            "validation 级，不代表 full profile。",
        ),
        (
            "第九章",
            "运行完成数量",
            "runtime_completion_count",
            metrics["runtime_completion_count"],
            validation_summary,
            "runtime_completion_count",
            "L4",
            True,
            "环境阻塞不计入 runtime completed。",
        ),
        (
            "第九章",
            "环境阻塞数量",
            "blocked_before_runtime_count",
            metrics["blocked_before_runtime_count"],
            validation_summary,
            "blocked_before_runtime_count",
            "L4",
            True,
            "环境阻塞样本不进入 runtime performance 分母。",
        ),
        (
            "第九章",
            "synthetic 样本数量",
            "synthetic_sample_count",
            metrics["synthetic_sample_count"],
            validation_summary,
            "synthetic_sample_count",
            "L4",
            True,
            "clean validation 不包含 synthetic pipeline sample。",
        ),
        (
            "第九章",
            "真实硬件未接触",
            "real_controller_contacted",
            metrics["real_controller_contacted"],
            validation_summary,
            "real_controller_contacted",
            "L4",
            True,
            "不能推出真实机械臂验收完成。",
        ),
        (
            "第九章",
            "物理运动未发生",
            "hardware_motion_observed",
            metrics["hardware_motion_observed"],
            validation_summary,
            "hardware_motion_observed",
            "L4",
            True,
            "不能推出真实机械臂运动实验完成。",
        ),
        (
            "第九章",
            "跨后端配对尚未 accepted",
            "usable_authoritative_pair_count",
            metrics["usable_authoritative_pair_count"],
            validation_summary,
            "usable_authoritative_pair_count",
            "L4",
            True,
            "Isaac blocked 时不能声明 sim-to-sim 一致性。",
        ),
        (
            "第九章",
            "LLM-only fake provider 仅验证管线",
            "model_runtime_type",
            metrics["llm_only"].get("model_runtime_type", "BLOCKED_BY_ENV"),
            llm_summary if llm_root.exists() else "",
            "model_runtime_type",
            "L3",
            False,
            "fake provider 不代表真实大模型效果。",
        ),
    ]
    return [
        {
            "章节": chapter,
            "结论": claim,
            "指标": metric,
            "数值": value,
            "source file": source,
            "source field": field,
            "experiment_id": "",
            "scenario_id": "",
            "backend": "",
            "seed": "",
            "repetition": "",
            "profile": metrics["profile"],
            "authority_level": level,
            "whether_authoritative": authoritative,
            "limitations": limitations,
        }
        for chapter, claim, metric, value, source, field, level, authoritative, limitations in items
    ]


def _missing_data_report(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "full_profile": metrics.get("full_profile_execution_status"),
        "real_robot_validation": "NOT_STARTED",
        "local_model_runtime": "NOT_ACCEPTED",
        "ollama_runtime": "NOT_ACCEPTED",
        "llm_only_runtime": metrics["llm_only"].get("runtime_status", "NOT_RUN"),
        "isaac_pairs": {
            "usable_authoritative_pair_count": metrics.get("usable_authoritative_pair_count"),
            "blocked_pair_count": metrics.get("blocked_pair_count"),
        },
        "required_follow_up": [
            "运行 Phase 12 full profile",
            "配置真实 OpenAI-compatible 或 Ollama runtime 后运行 LLM-only validation",
            "在 Isaac 环境可用时补充 F15 paired runtime",
            "完成真实机械臂 Level 0-6 前不得声明真机实验结论",
        ],
    }


def _figure_index(validation_root: Path) -> list[dict[str, str]]:
    plot_root = validation_root / "plots"
    rows: list[dict[str, str]] = []
    for svg in sorted((plot_root / "svg").glob("*.svg")):
        rows.append(
            {
                "name": svg.stem,
                "path": str(svg),
                "type": "svg",
                "data_source": "aggregate_payload",
                "note": "正式论文优先引用 SVG；PNG 为 placeholder preview。",
            }
        )
    return rows


def _table_index(validation_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for csv_path in sorted((validation_root / "tables/csv").glob("*.csv")):
        with csv_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            data = list(reader)
        rows.append({"name": csv_path.stem, "path": str(csv_path), "row_count": len(data)})
    return rows


def _llm_missing_summary() -> dict[str, Any]:
    return {
        "status": "LLM_ONLY_BASELINE_NOT_RUN",
        "runtime_status": "BLOCKED_BY_ENV",
        "model_runtime_type": "BLOCKED_BY_ENV",
        "model_runtime_accepted": False,
        "authoritative_for_model_performance": False,
    }
