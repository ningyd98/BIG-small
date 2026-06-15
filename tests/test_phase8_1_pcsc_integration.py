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
        experiment_id="phase81-pcsc",
        scenario_id="S01_NORMAL_STATIC",
        mode=ExperimentMode.PCSC,
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


def test_pcsc_runs_real_periodic_supervisor_and_network_delivery(tmp_path: Path) -> None:
    runner = ExperimentRunner(_config(tmp_path))
    execution = runner.run()
    contract = runner._active_contract
    assert contract is not None

    decisions = runner.harness.supervisor.decisions_for_task(contract.task_id)
    events = [event.event_type for event in execution.events]

    assert decisions
    assert execution.result.supervisory_decision_count == len(decisions)
    assert "supervisory_decision" in events
    assert "network_delivered" in events
    assert execution.result.completed_step_count == len(contract.steps)
