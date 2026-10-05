"""Phase 8.2 故障交错和敏感性回归测试，覆盖安全边界、证据契约和关键失败路径。"""

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
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner


def _config(tmp_path: Path, *, mode: ExperimentMode = ExperimentMode.PCSC) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"phase82-pcsc-ticks-{mode.value.lower()}",
        scenario_id="S01_NORMAL_STATIC",
        mode=mode,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="normal"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=300,
        timeout_ms=30_000,
        artifact_dir=tmp_path / mode.value,
    )


def test_pcsc_normal_task_produces_multiple_periodic_ticks(tmp_path: Path) -> None:
    execution = ExperimentRunner(_config(tmp_path)).run()
    tick_events = [event for event in execution.events if event.event_type == "pcsc_tick"]
    decision_events = [
        event for event in execution.events if event.event_type == "supervisory_decision"
    ]

    assert execution.result.task_completion_time_ms > 600
    assert len(tick_events) >= 2
    assert len(decision_events) == len(tick_events)
    assert execution.result.supervisory_decision_count == len(decision_events)


def test_auto_starts_periodic_ticks_only_after_committed_pcsc_mode(tmp_path: Path) -> None:
    execution = ExperimentRunner(_config(tmp_path, mode=ExperimentMode.AUTO)).run()
    commits = [
        event for event in execution.events if event.event_type == "mode_transition_committed"
    ]
    ticks = [event for event in execution.events if event.event_type == "pcsc_tick"]

    if commits:
        first_commit_time = commits[0].virtual_time_ms
        assert all(event.virtual_time_ms >= first_commit_time for event in ticks)
    assert execution.result.final_mode.value in {
        "PERIODIC_CLOUD_SUPERVISION",
        "EVENT_TRIGGERED_EDGE_AUTONOMY",
    }
