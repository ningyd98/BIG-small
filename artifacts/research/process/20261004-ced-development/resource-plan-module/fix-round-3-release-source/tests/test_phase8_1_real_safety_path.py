"""Phase 8.1 PCSC/ETEAC 集成回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.contracts import SafetyDecision
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
        experiment_id=f"phase81-safety-{scenario_id.lower()}",
        scenario_id=scenario_id,
        mode=ExperimentMode.AUTO,
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


def test_safety_counts_come_from_safety_shield_events(tmp_path: Path) -> None:
    runner = ExperimentRunner(_config(tmp_path, "S01_NORMAL_STATIC"))
    execution = runner.run()

    completed = [event for event in execution.events if event.event_type == "step_completed"]

    assert runner.harness.observer.safety_precheck_calls == len(completed)
    assert execution.result.safety_allow_count == len(completed)
    assert execution.result.safety_decision_counts[SafetyDecision.ALLOW] == len(completed)


def test_emergency_stop_reaches_real_safety_stop_path(tmp_path: Path) -> None:
    runner = ExperimentRunner(_config(tmp_path, "S14_EMERGENCY_STOP"))
    execution = runner.run()

    assert execution.result.emergency_stop_count >= 1 or execution.result.safety_reject_count >= 1
    assert execution.result.terminal_reason == "emergency_stop"
    assert any(event.event_type in {"step_failed", "step_rejected"} for event in execution.events)
    assert runner.harness.robot.get_state().estop_engaged is True
