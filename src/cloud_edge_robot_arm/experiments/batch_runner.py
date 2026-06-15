from __future__ import annotations

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
    "S08_NETWORK_OUTAGE",
    "S10_STALE_DUPLICATE_REORDERED_COMMAND",
    "S11_SKILL_CACHE_HIT",
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
    if suite not in {"smoke", "full"}:
        raise ValueError("suite must be smoke or full")
    selected_seeds = seeds if seeds is not None else ([0] if suite == "smoke" else list(range(10)))
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
                    config = ExperimentConfig(
                        experiment_id=f"{suite}-{scenario_id.lower()}-{mode.value.lower()}-{network.value.lower()}-{seed}",
                        scenario_id=scenario_id,
                        mode=mode,
                        seed=seed,
                        repetitions=1,
                        network_profile=network,
                        fault_profile=FaultProfile(name=scenario_id.lower()),
                        task_profile=TaskProfile(name="pick_place"),
                        cache_policy=CachePolicy.CACHE_ENABLED,
                        risk_policy_version="risk-v1",
                        supervision_period_ms=1_000,
                        timeout_ms=30_000,
                        artifact_dir=output_dir / "runs" / scenario_id / mode.value / str(seed),
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
        }
    return {
        "run_count": len(results),
        "success_count": sum(1 for result in results if result.task_success),
        "success_rate": success.model_dump(mode="json"),
        "task_completion_time_ms": duration.model_dump(mode="json"),
        "cloud_invocation_count": cloud.model_dump(mode="json"),
        "by_mode": by_mode,
        "by_network": by_network,
        "exclusion_rules": "failed runs are included; no zero-sample group is silently excluded",
    }
