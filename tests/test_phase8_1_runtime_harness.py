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
from cloud_edge_robot_arm.experiments.runtime_harness import RuntimeExperimentHarness
from cloud_edge_robot_arm.simulation.clock import VirtualClock


def _config(tmp_path: Path, *, mode: ExperimentMode = ExperimentMode.ETEAC) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="phase81-harness",
        scenario_id="S01_NORMAL_STATIC",
        mode=mode,
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


def test_runtime_harness_executes_contract_through_real_services(tmp_path: Path) -> None:
    clock = VirtualClock(max_time_ms=30_000)
    harness = RuntimeExperimentHarness(config=_config(tmp_path), clock=clock)
    contract = harness.create_contract()

    result = harness.submit_contract(contract)

    assert result.success is True
    assert harness.observer.contract_validator_calls >= 1
    assert harness.observer.task_executor_calls == 1
    assert harness.observer.safety_precheck_calls >= len(contract.steps)
    assert harness.observer.robot_action_calls >= len(contract.steps)
    assert harness.completion_summary() is not None
    assert harness.completed_step_ids() == [step.step_id for step in contract.steps]
    assert harness.current_mode == ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY
