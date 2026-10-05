"""Phase 8.2 故障交错和敏感性回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.contracts import ControlMode
from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner


def test_auto_transition_commits_only_after_step_safe_boundary(tmp_path: Path) -> None:
    config = ExperimentConfig(
        experiment_id="phase82-transition-safe-boundary",
        scenario_id="S01_NORMAL_STATIC",
        mode=ExperimentMode.AUTO,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="normal"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=250,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )
    execution = ExperimentRunner(config).run()
    prepared = next(
        event for event in execution.events if event.event_type == "mode_transition_prepared"
    )
    deferred = next(
        event for event in execution.events if event.event_type == "mode_transition_deferred"
    )
    committed = next(
        event for event in execution.events if event.event_type == "mode_transition_committed"
    )
    completed = [event for event in execution.events if event.event_type == "step_completed"]

    assert prepared.virtual_time_ms <= deferred.virtual_time_ms
    assert any(event.virtual_time_ms <= committed.virtual_time_ms for event in completed)
    assert committed.virtual_time_ms > prepared.virtual_time_ms
    assert execution.result.deferred_switch_count >= 1
    assert execution.result.final_mode == ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY
