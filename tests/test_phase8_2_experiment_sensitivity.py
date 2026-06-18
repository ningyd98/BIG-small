"""Phase 8.2 故障交错和敏感性回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from cloud_edge_robot_arm.experiments.batch_runner import run_suite
from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner


def _config(
    tmp_path: Path,
    *,
    scenario_id: str,
    mode: ExperimentMode,
    network: NetworkProfileName,
    seed: int,
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"phase82-sensitive-{scenario_id.lower()}-{mode.value.lower()}-{network.value.lower()}-{seed}",
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
        artifact_dir=tmp_path / scenario_id / mode.value / network.value / str(seed),
    )


def test_network_profile_changes_pcsc_dynamic_metrics(tmp_path: Path) -> None:
    good = (
        ExperimentRunner(
            _config(
                tmp_path,
                scenario_id="S08_NETWORK_OUTAGE",
                mode=ExperimentMode.PCSC,
                network=NetworkProfileName.GOOD,
                seed=0,
            )
        )
        .run()
        .result
    )
    severe = (
        ExperimentRunner(
            _config(
                tmp_path,
                scenario_id="S08_NETWORK_OUTAGE",
                mode=ExperimentMode.PCSC,
                network=NetworkProfileName.SEVERE,
                seed=0,
            )
        )
        .run()
        .result
    )

    assert (
        good.task_completion_time_ms,
        good.recovery_latency_ms,
        good.downloaded_bytes,
    ) != (
        severe.task_completion_time_ms,
        severe.recovery_latency_ms,
        severe.downloaded_bytes,
    )


def test_pcsc_and_eteac_have_different_cloud_invocation_mechanisms(tmp_path: Path) -> None:
    pcsc = (
        ExperimentRunner(
            _config(
                tmp_path,
                scenario_id="S02_TARGET_MOVED",
                mode=ExperimentMode.PCSC,
                network=NetworkProfileName.NORMAL,
                seed=0,
            )
        )
        .run()
        .result
    )
    eteac = (
        ExperimentRunner(
            _config(
                tmp_path,
                scenario_id="S02_TARGET_MOVED",
                mode=ExperimentMode.ETEAC,
                network=NetworkProfileName.NORMAL,
                seed=0,
            )
        )
        .run()
        .result
    )

    assert pcsc.cloud_invocation_count != eteac.cloud_invocation_count


def test_seed_changes_reproducible_network_samples(tmp_path: Path) -> None:
    first = (
        ExperimentRunner(
            _config(
                tmp_path,
                scenario_id="S08_NETWORK_OUTAGE",
                mode=ExperimentMode.PCSC,
                network=NetworkProfileName.DEGRADED,
                seed=1,
            )
        )
        .run()
        .result
    )
    second = (
        ExperimentRunner(
            _config(
                tmp_path,
                scenario_id="S08_NETWORK_OUTAGE",
                mode=ExperimentMode.PCSC,
                network=NetworkProfileName.DEGRADED,
                seed=2,
            )
        )
        .run()
        .result
    )

    assert (first.downloaded_bytes, first.task_completion_time_ms, first.result_hash) != (
        second.downloaded_bytes,
        second.task_completion_time_ms,
        second.result_hash,
    )


def test_validation_summary_contains_non_identical_mode_and_network_metrics(tmp_path: Path) -> None:
    summary = run_suite(
        "full",
        output_dir=tmp_path,
        seeds=[0, 1],
        network_names=["GOOD", "SEVERE"],
    )

    by_mode = cast(dict[str, Any], summary.summary["by_mode"])
    by_network = cast(dict[str, Any], summary.summary["by_network"])
    assert len({str(value) for value in by_mode.values()}) > 1
    assert len({str(value) for value in by_network.values()}) > 1
