from __future__ import annotations

import csv
import json
import platform
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from cloud_edge_robot_arm.experiments.models import ExperimentEvent, ExperimentResult
from cloud_edge_robot_arm.experiments.runner import git_sha

# Phase 8/9 实验 artifact 写出器只记录仿真证据，报告文字必须明确不能代表真实硬件。
SUMMARY_COLUMNS = [
    "run_id",
    "experiment_id",
    "scenario_id",
    "mode",
    "seed",
    "network_profile",
    "task_success",
    "result_status",
    "task_completion_time_ms",
    "fault_detection_latency_ms",
    "cloud_response_latency_ms",
    "recovery_latency_ms",
    "cloud_invocation_count",
    "supervisory_decision_count",
    "replan_count",
    "retry_count",
    "uploaded_bytes",
    "downloaded_bytes",
    "mode_switch_count",
    "deferred_switch_count",
    "aborted_transition_count",
    "cache_hit_count",
    "cache_miss_count",
    "simulated_collision_count",
    "unsafe_counterfactual_count",
    "config_hash",
    "result_hash",
]


@dataclass(frozen=True)
class ArtifactWriteResult:
    output_dir: Path
    manifest_path: Path
    raw_runs_path: Path
    events_path: Path
    summary_csv_path: Path
    summary_json_path: Path
    report_path: Path


class ArtifactWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        *,
        run_id: str,
        config_hash: str,
        seed: int,
        results: list[ExperimentResult],
        events: list[ExperimentEvent],
        summary: dict[str, object],
        suite: str,
    ) -> ArtifactWriteResult:
        manifest = self.output_dir / "run_manifest.json"
        raw_runs = self.output_dir / "raw_runs.jsonl"
        event_path = self.output_dir / "events.jsonl"
        summary_csv = self.output_dir / "summary.csv"
        summary_json = self.output_dir / "summary.json"
        report = self.output_dir / "report.md"
        started = datetime.now(UTC)
        manifest.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "git_sha": git_sha(),
                    "config_hash": config_hash,
                    "python_version": sys.version.split()[0],
                    "platform": platform.platform(),
                    "seed": seed,
                    "start_time": started.isoformat(),
                    "end_time": datetime.now(UTC).isoformat(),
                    "experiment_schema_version": "phase8.v1",
                    "suite": suite,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        _write_jsonl(raw_runs, results)
        _write_jsonl(event_path, events)
        _write_csv(summary_csv, results)
        summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        report.write_text(
            render_report(summary=summary, results=results, suite=suite), encoding="utf-8"
        )
        return ArtifactWriteResult(
            output_dir=self.output_dir,
            manifest_path=manifest,
            raw_runs_path=raw_runs,
            events_path=event_path,
            summary_csv_path=summary_csv,
            summary_json_path=summary_json,
            report_path=report,
        )


def _write_jsonl(path: Path, values: Sequence[BaseModel]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for value in values:
            f.write(value.model_dump_json() + "\n")


def _write_csv(path: Path, results: list[ExperimentResult]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for result in results:
            row = {
                "run_id": result.run_id,
                "experiment_id": result.experiment_id,
                "scenario_id": result.scenario_id,
                "mode": result.mode.value,
                "seed": result.seed,
                "network_profile": result.network_profile.value,
                "task_success": result.task_success,
                "result_status": result.result_status.value,
                "task_completion_time_ms": result.task_completion_time_ms,
                "fault_detection_latency_ms": result.fault_detection_latency_ms,
                "cloud_response_latency_ms": result.cloud_response_latency_ms,
                "recovery_latency_ms": result.recovery_latency_ms,
                "cloud_invocation_count": result.cloud_invocation_count,
                "supervisory_decision_count": result.supervisory_decision_count,
                "replan_count": result.replan_count,
                "retry_count": result.retry_count,
                "uploaded_bytes": result.uploaded_bytes,
                "downloaded_bytes": result.downloaded_bytes,
                "mode_switch_count": result.mode_switch_count,
                "deferred_switch_count": result.deferred_switch_count,
                "aborted_transition_count": result.aborted_transition_count,
                "cache_hit_count": result.cache_hit_count,
                "cache_miss_count": result.cache_miss_count,
                "simulated_collision_count": result.simulated_collision_count,
                "unsafe_counterfactual_count": result.unsafe_counterfactual_count,
                "config_hash": result.config_hash,
                "result_hash": result.result_hash,
            }
            writer.writerow(row)


def render_report(
    *,
    summary: dict[str, object],
    results: list[ExperimentResult],
    suite: str,
) -> str:
    success_count = sum(1 for result in results if result.task_success)
    run_count = len(results)
    return (
        "# Phase 8 Experiment Report\n\n"
        f"- Suite: `{suite}`\n"
        f"- Runs: {run_count}\n"
        f"- Successful tasks: {success_count}\n"
        f"- Summary keys: {', '.join(sorted(summary.keys()))}\n\n"
        "当前是 Mock/仿真实验，不能直接代表真实机械臂性能。网络和物理模型是工程抽象，"
        "Phase 9 仍需真实硬件验证。模拟零碰撞不得表述为真实设备安全证明。\n\n"
        "## Data-Supported Conclusions\n\n"
        "本报告只总结已运行样本中的观测指标，不声称 AUTO 在所有指标上优于固定模式。\n\n"
        "## Limits\n\n"
        "当前结果不包含真实机械臂、真实相机、ROS 2、MoveIt 2 或生产 LLM。\n"
    )
