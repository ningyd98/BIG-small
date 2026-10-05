"""Phase 9 物理仿真和跨后端验证测试辅助模块，封装夹具以保持回归用例可读。"""

from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    TaskProfile,
)


def phase9_experiment_config(
    tmp_path: Path,
    *,
    scenario_id: str,
    mode: ExperimentMode,
    network_profile: NetworkProfileName = NetworkProfileName.NORMAL,
    seed: int = 0,
    supervision_period_ms: int = 300,
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"phase9-{scenario_id.lower()}-{mode.value.lower()}",
        scenario_id=scenario_id,
        mode=mode,
        seed=seed,
        repetitions=1,
        network_profile=network_profile,
        fault_profile=FaultProfile(name=scenario_id.lower()),
        task_profile=TaskProfile(name="physical_pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=supervision_period_ms,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )
