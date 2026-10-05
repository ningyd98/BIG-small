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


def test_pcsc_ticks_are_interleaved_between_atomic_steps(tmp_path: Path) -> None:
    config = ExperimentConfig(
        experiment_id="phase82-tick-interleaving",
        scenario_id="S01_NORMAL_STATIC",
        mode=ExperimentMode.PCSC,
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
    step_started = [
        event.virtual_time_ms for event in execution.events if event.event_type == "step_started"
    ]
    tick_times = [
        event.virtual_time_ms for event in execution.events if event.event_type == "pcsc_tick"
    ]
    terminal_time = next(
        event.virtual_time_ms for event in execution.events if event.event_type == "task_terminal"
    )

    assert len(step_started) >= 3
    assert any(step_started[0] < tick_time < terminal_time for tick_time in tick_times)
    assert any(
        earlier < tick_time < later
        for earlier, later in zip(step_started, step_started[1:], strict=False)
        for tick_time in tick_times
    )
