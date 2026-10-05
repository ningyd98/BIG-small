"""Phase 8 实验场景和指标回归测试，覆盖安全边界、证据契约和关键失败路径。"""

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


def test_safety_counterfactual_counts_shadow_risk_without_formal_collision(
    tmp_path: Path,
) -> None:
    config = ExperimentConfig(
        experiment_id="safety-shadow",
        scenario_id="S03_OBSTACLE_INSERTED",
        mode=ExperimentMode.ETEAC,
        seed=5,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="obstacle"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
        ablations=[AblationType.A7_SAFETY_SHADOW_COUNTERFACTUAL],
    )

    result = ExperimentRunner(config).run_once()

    assert result.unsafe_counterfactual_count >= 1
    assert result.simulated_collision_count == 0
    assert result.safety_reject_count + result.safety_pause_count >= 1
