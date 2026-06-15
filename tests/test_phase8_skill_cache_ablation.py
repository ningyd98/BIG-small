from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.experiments.models import (
    AblationType,
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
    cache_policy: CachePolicy,
    ablations: list[AblationType] | None = None,
    scenario_id: str = "S11_SKILL_CACHE_HIT",
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"cache-{cache_policy.value.lower()}",
        scenario_id=scenario_id,
        mode=ExperimentMode.AUTO,
        seed=4,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name=scenario_id.lower()),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=cache_policy,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
        ablations=ablations or [],
    )


def test_cache_enabled_records_hits_and_trusted_template_execution(tmp_path: Path) -> None:
    result = ExperimentRunner(_config(tmp_path, cache_policy=CachePolicy.CACHE_ENABLED)).run_once()

    assert result.cache_hit_count >= 1
    assert result.cache_miss_count == 0
    assert result.trusted_template_execution_count >= 1


def test_no_cache_reuse_ablation_records_miss_and_more_cloud_cost(tmp_path: Path) -> None:
    enabled = ExperimentRunner(
        _config(tmp_path / "enabled", cache_policy=CachePolicy.CACHE_ENABLED)
    ).run_once()
    disabled = ExperimentRunner(
        _config(
            tmp_path / "disabled",
            cache_policy=CachePolicy.NO_CACHE_REUSE,
            ablations=[AblationType.A4_NO_CACHE_REUSE],
        )
    ).run_once()

    assert disabled.cache_hit_count == 0
    assert disabled.cache_miss_count >= 1
    assert disabled.cloud_invocation_count >= enabled.cloud_invocation_count


def test_cache_quarantine_prevents_normal_hit(tmp_path: Path) -> None:
    result = ExperimentRunner(
        _config(
            tmp_path,
            cache_policy=CachePolicy.CACHE_ENABLED,
            scenario_id="S12_SKILL_CACHE_QUARANTINE",
        )
    ).run_once()

    assert result.cache_quarantine_count >= 1
    assert result.cache_hit_count == 0
