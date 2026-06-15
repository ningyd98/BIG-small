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


def _config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="phase81-real-executor",
        scenario_id="S01_NORMAL_STATIC",
        mode=ExperimentMode.ETEAC,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="normal"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )


def test_runner_uses_task_executor_records_not_synthetic_steps(tmp_path: Path) -> None:
    runner = ExperimentRunner(_config(tmp_path))
    execution = runner.run()
    contract = runner._active_contract
    assert contract is not None

    records = runner.harness.step_execution_records(contract.task_id)
    step_started = [event for event in execution.events if event.event_type == "step_started"]
    step_completed = [event for event in execution.events if event.event_type == "step_completed"]

    assert runner.harness.observer.task_executor_calls == 1
    assert len(records) == len(contract.steps)
    assert len(step_started) == len(contract.steps)
    assert len(step_completed) == len(contract.steps)
    assert execution.result.completed_step_count == len(
        {record.step_id for record in records if record.success}
    )
    assert all("safety_decision" in event.payload for event in step_completed)
