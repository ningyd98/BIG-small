"""批量实验 runner。

Batch runner 负责把受控 ExperimentConfig 展开为多次可复现实验，统一写入 artifact。
它接受的是结构化配置，不接受任意脚本、命令或环境变量。
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cloud_edge_robot_arm.experiments.artifacts import ArtifactWriter
from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentEvent,
    ExperimentMode,
    ExperimentResult,
    FaultProfile,
    NetworkProfileName,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.reproducibility import stable_hash
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner
from cloud_edge_robot_arm.experiments.scenario import scenario_registry
from cloud_edge_robot_arm.experiments.statistics import success_rate_summary, summarize_values


@dataclass(frozen=True)
class BatchSummary:
    run_count: int
    success_count: int
    output_dir: Path
    summary: dict[str, object]


SMOKE_SCENARIOS = [
    "S01_NORMAL_STATIC",
    "S02_TARGET_MOVED",
    "S03_OBSTACLE_INSERTED",
    "S04_GRASP_FAILURE",
    "S05_TARGET_LOST",
    "S06_PERCEPTION_DEGRADED",
    "S07_NETWORK_DEGRADED",
    "S08_NETWORK_OUTAGE",
    "S09_CLOUD_UNAVAILABLE",
    "S10_STALE_DUPLICATE_REORDERED_COMMAND",
    "S11_SKILL_CACHE_HIT",
    "S12_SKILL_CACHE_QUARANTINE",
    "S13_MODE_OSCILLATION_PRESSURE",
    "S14_EMERGENCY_STOP",
    "S15_SQLITE_RESTART_DURING_RUN",
]


def run_suite(
    suite: str,
    *,
    output_dir: Path,
    seeds: list[int] | None = None,
    network_names: list[str] | None = None,
) -> BatchSummary:
    if suite not in {"smoke", "validation", "full"}:
        raise ValueError("suite must be smoke, validation or full")
    selected_seeds = seeds if seeds is not None else _default_seeds(suite)
    networks = [
        NetworkProfileName(name)
        for name in (
            network_names
            if network_names is not None
            else (
                ["NORMAL"] if suite == "smoke" else ["GOOD", "NORMAL", "DEGRADED", "POOR", "SEVERE"]
            )
        )
    ]
    scenarios = [s.scenario_id for s in scenario_registry()]
    if suite == "smoke":
        scenarios = SMOKE_SCENARIOS
    modes = [ExperimentMode.PCSC, ExperimentMode.ETEAC, ExperimentMode.AUTO]

    results: list[ExperimentResult] = []
    events: list[ExperimentEvent] = []
    for scenario_id in scenarios:
        for mode in modes:
            for network in networks:
                for seed in selected_seeds:
                    with tempfile.TemporaryDirectory(prefix=f"phase8-{suite}-run-") as tmp_run:
                        config = ExperimentConfig(
                            experiment_id=(
                                f"{suite}-{scenario_id.lower()}-{mode.value.lower()}-"
                                f"{network.value.lower()}-{seed}"
                            ),
                            scenario_id=scenario_id,
                            mode=mode,
                            seed=seed,
                            repetitions=1,
                            network_profile=network,
                            fault_profile=FaultProfile(name=scenario_id.lower()),
                            task_profile=TaskProfile(name="pick_place"),
                            cache_policy=CachePolicy.CACHE_ENABLED,
                            risk_policy_version="risk-v1",
                            supervision_period_ms=300,
                            timeout_ms=30_000,
                            artifact_dir=Path(tmp_run),
                        )
                        execution = ExperimentRunner(config).run()
                        results.append(execution.result)
                        events.extend(execution.events)

    success_count = sum(1 for result in results if result.task_success)
    summary = _summary_payload(results)
    hash_payload = {
        "suite": suite,
        "seeds": selected_seeds,
        "networks": [n.value for n in networks],
    }
    ArtifactWriter(output_dir).write(
        run_id=f"batch-{stable_hash(hash_payload)[:16]}",
        config_hash=stable_hash(hash_payload),
        seed=selected_seeds[0] if selected_seeds else 0,
        results=results,
        events=events,
        summary=summary,
        suite=suite,
    )
    return BatchSummary(
        run_count=len(results),
        success_count=success_count,
        output_dir=output_dir,
        summary=summary,
    )


def _default_seeds(suite: str) -> list[int]:
    if suite == "smoke":
        return [0]
    if suite == "validation":
        return [0, 1, 2]
    return list(range(10))


def _summary_payload(results: list[ExperimentResult]) -> dict[str, object]:
    success = success_rate_summary(
        sum(1 for result in results if result.task_success), len(results)
    )
    duration = summarize_values([float(result.task_completion_time_ms) for result in results])
    cloud = summarize_values([float(result.cloud_invocation_count) for result in results])
    by_mode: dict[str, dict[str, object]] = {}
    for mode in ExperimentMode:
        mode_results = [result for result in results if result.mode == mode]
        if not mode_results:
            continue
        by_mode[mode.value] = {
            "run_count": len(mode_results),
            "success_rate": success_rate_summary(
                sum(1 for result in mode_results if result.task_success),
                len(mode_results),
            ).model_dump(mode="json"),
            "completion_time_ms": summarize_values(
                [float(result.task_completion_time_ms) for result in mode_results]
            ).model_dump(mode="json"),
            "fault_detection_latency_ms": summarize_values(
                [
                    float(result.fault_detection_latency_ms)
                    for result in mode_results
                    if result.fault_detection_latency_ms is not None
                ]
            ).model_dump(mode="json"),
            "recovery_latency_ms": summarize_values(
                [
                    float(result.recovery_latency_ms)
                    for result in mode_results
                    if result.recovery_latency_ms is not None
                ]
            ).model_dump(mode="json"),
            "cloud_invocation_count": summarize_values(
                [float(result.cloud_invocation_count) for result in mode_results]
            ).model_dump(mode="json"),
            "downloaded_bytes": summarize_values(
                [float(result.downloaded_bytes) for result in mode_results]
            ).model_dump(mode="json"),
            "retry_count": summarize_values(
                [float(result.retry_count) for result in mode_results]
            ).model_dump(mode="json"),
            "mode_switch_count": summarize_values(
                [float(result.mode_switch_count) for result in mode_results]
            ).model_dump(mode="json"),
        }
    by_network: dict[str, dict[str, object]] = {}
    for network in NetworkProfileName:
        network_results = [result for result in results if result.network_profile == network]
        if not network_results:
            continue
        by_network[network.value] = {
            "run_count": len(network_results),
            "success_rate": success_rate_summary(
                sum(1 for result in network_results if result.task_success),
                len(network_results),
            ).model_dump(mode="json"),
            "completion_time_ms": summarize_values(
                [float(result.task_completion_time_ms) for result in network_results]
            ).model_dump(mode="json"),
            "fault_detection_latency_ms": summarize_values(
                [
                    float(result.fault_detection_latency_ms)
                    for result in network_results
                    if result.fault_detection_latency_ms is not None
                ]
            ).model_dump(mode="json"),
            "recovery_latency_ms": summarize_values(
                [
                    float(result.recovery_latency_ms)
                    for result in network_results
                    if result.recovery_latency_ms is not None
                ]
            ).model_dump(mode="json"),
            "cloud_invocation_count": summarize_values(
                [float(result.cloud_invocation_count) for result in network_results]
            ).model_dump(mode="json"),
            "downloaded_bytes": summarize_values(
                [float(result.downloaded_bytes) for result in network_results]
            ).model_dump(mode="json"),
            "retry_count": summarize_values(
                [float(result.retry_count) for result in network_results]
            ).model_dump(mode="json"),
            "mode_switch_count": summarize_values(
                [float(result.mode_switch_count) for result in network_results]
            ).model_dump(mode="json"),
        }
    by_mode_scenario = _group_summary(
        results,
        key=lambda result: f"{result.mode.value}×{result.scenario_id}",
    )
    by_network_scenario = _group_summary(
        results,
        key=lambda result: f"{result.network_profile.value}×{result.scenario_id}",
    )
    by_mode_network = _group_summary(
        results,
        key=lambda result: f"{result.mode.value}×{result.network_profile.value}",
    )
    by_seed = _group_summary(results, key=lambda result: str(result.seed))
    return {
        "run_count": len(results),
        "success_count": sum(1 for result in results if result.task_success),
        "success_rate": success.model_dump(mode="json"),
        "task_completion_time_ms": duration.model_dump(mode="json"),
        "cloud_invocation_count": cloud.model_dump(mode="json"),
        "by_mode": by_mode,
        "by_network": by_network,
        "mode_by_scenario": by_mode_scenario,
        "network_by_scenario": by_network_scenario,
        "mode_by_network": by_mode_network,
        "seed_variability": by_seed,
        "validity_guard": _validity_guard(results),
        "exclusion_rules": "failed runs are included; no zero-sample group is silently excluded",
    }


def _group_summary(
    results: list[ExperimentResult], *, key: Callable[[ExperimentResult], str]
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[ExperimentResult]] = {}
    for result in results:
        group_key = key(result)
        grouped.setdefault(group_key, []).append(result)
    return {group_key: _metric_view(group_results) for group_key, group_results in grouped.items()}


def _metric_view(results: list[ExperimentResult]) -> dict[str, object]:
    return {
        "run_count": len(results),
        "success_rate": success_rate_summary(
            sum(1 for result in results if result.task_success), len(results)
        ).model_dump(mode="json"),
        "completion_time_ms": summarize_values(
            [float(result.task_completion_time_ms) for result in results]
        ).model_dump(mode="json"),
        "fault_detection_latency_ms": summarize_values(
            [
                float(result.fault_detection_latency_ms)
                for result in results
                if result.fault_detection_latency_ms is not None
            ]
        ).model_dump(mode="json"),
        "recovery_latency_ms": summarize_values(
            [
                float(result.recovery_latency_ms)
                for result in results
                if result.recovery_latency_ms is not None
            ]
        ).model_dump(mode="json"),
        "cloud_invocation_count": summarize_values(
            [float(result.cloud_invocation_count) for result in results]
        ).model_dump(mode="json"),
        "communication_bytes": summarize_values(
            [float(result.uploaded_bytes + result.downloaded_bytes) for result in results]
        ).model_dump(mode="json"),
        "retry_count": summarize_values(
            [float(result.retry_count) for result in results]
        ).model_dump(mode="json"),
        "mode_switch_count": summarize_values(
            [float(result.mode_switch_count) for result in results]
        ).model_dump(mode="json"),
    }


def _validity_guard(results: list[ExperimentResult]) -> dict[str, object]:
    by_mode = _metric_signatures(results, lambda result: result.mode.value)
    by_network = _metric_signatures(results, lambda result: result.network_profile.value)
    by_seed = _metric_signatures(results, lambda result: str(result.seed))
    detection_latencies = [
        result.fault_detection_latency_ms
        for result in results
        if result.fault_detection_latency_ms is not None
    ]
    return {
        "modes_not_identical": len(set(by_mode.values())) > 1 if len(by_mode) > 1 else True,
        "networks_not_identical": len(set(by_network.values())) > 1
        if len(by_network) > 1
        else True,
        "seeds_not_identical": len(set(by_seed.values())) > 1 if len(by_seed) > 1 else True,
        "fault_detection_latency_not_all_zero": any(
            latency is not None and latency > 0 for latency in detection_latencies
        ),
        "pcsc_multi_tick_present": any(
            result.mode == ExperimentMode.PCSC and result.supervisory_decision_count >= 2
            for result in results
        ),
    }


def _metric_signatures(
    results: list[ExperimentResult], key_fn: Callable[[ExperimentResult], str]
) -> dict[str, tuple[float, float, float, float, float, float]]:
    grouped: dict[str, list[ExperimentResult]] = {}
    for result in results:
        grouped.setdefault(key_fn(result), []).append(result)
    return {
        group_key: (
            sum(1.0 for result in group if result.task_success) / max(1, len(group)),
            sum(float(result.task_completion_time_ms) for result in group) / max(1, len(group)),
            sum(float(result.cloud_invocation_count) for result in group) / max(1, len(group)),
            sum(float(result.uploaded_bytes + result.downloaded_bytes) for result in group)
            / max(1, len(group)),
            sum(float(result.mode_switch_count) for result in group) / max(1, len(group)),
            sum(float(result.retry_count) for result in group) / max(1, len(group)),
        )
        for group_key, group in grouped.items()
    }
