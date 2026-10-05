"""Phase 8.1 PCSC/ETEAC 集成回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.experiments.metrics_collector import ExperimentMetricsCollector
from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner


def _config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="phase81-metrics",
        scenario_id="S10_STALE_DUPLICATE_REORDERED_COMMAND",
        mode=ExperimentMode.PCSC,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="commands"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )


def test_metrics_can_be_recomputed_from_events(tmp_path: Path) -> None:
    execution = ExperimentRunner(_config(tmp_path)).run()
    recomputed = ExperimentMetricsCollector.from_events(execution.events).collect()

    assert recomputed.completed_step_count == execution.result.completed_step_count
    assert recomputed.safety_allow_count == execution.result.safety_allow_count
    assert (
        recomputed.stale_command_rejection_count == execution.result.stale_command_rejection_count
    )
    assert recomputed.duplicate_command_rejection_count == (
        execution.result.duplicate_command_rejection_count
    )
