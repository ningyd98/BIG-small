"""Phase 8.1 PCSC/ETEAC 集成回归测试，覆盖安全边界、证据契约和关键失败路径。"""

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


def _config(tmp_path: Path, scenario_id: str) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"phase81-{scenario_id.lower()}",
        scenario_id=scenario_id,
        mode=ExperimentMode.ETEAC,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name=scenario_id.lower()),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path / scenario_id,
    )


def test_target_move_fault_is_injected_between_step_start_and_terminal(tmp_path: Path) -> None:
    execution = ExperimentRunner(_config(tmp_path, "S02_TARGET_MOVED")).run()
    event_types = [event.event_type for event in execution.events]

    first_step_started = event_types.index("step_started")
    fault_injected = event_types.index("fault_injected")
    terminal = event_types.index("run_completed")

    assert first_step_started < fault_injected < terminal
    injected = execution.events[fault_injected]
    assert injected.virtual_time_ms > 0
    assert injected.payload["fault_type"] == "TARGET_MOVED"


def test_network_outage_fault_is_not_initial_state(tmp_path: Path) -> None:
    execution = ExperimentRunner(_config(tmp_path, "S08_NETWORK_OUTAGE")).run()
    fault_events = [event for event in execution.events if event.event_type == "fault_injected"]
    assert fault_events
    assert fault_events[0].virtual_time_ms >= 800
    assert any(
        event.event_type == "step_started"
        and event.virtual_time_ms < fault_events[0].virtual_time_ms
        for event in execution.events
    )
