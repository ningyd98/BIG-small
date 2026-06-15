from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.contracts import AutoModeTransitionStatus, ControlMode
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


def _config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="phase81-transition",
        scenario_id="S13_MODE_OSCILLATION_PRESSURE",
        mode=ExperimentMode.AUTO,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="transition"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )


def test_prepare_does_not_change_current_mode_until_commit(tmp_path: Path) -> None:
    harness = RuntimeExperimentHarness(config=_config(tmp_path), clock=VirtualClock())
    contract = harness.create_contract()
    original = harness.current_mode

    prepared = harness.prepare_mode_transition(
        contract.task_id,
        to_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        decision_id="dec-1",
        reason="test",
    )

    assert prepared.status == AutoModeTransitionStatus.PREPARED
    assert harness.current_mode == original

    committed = harness.commit_mode_transition(prepared.transition_id)

    assert committed.status == AutoModeTransitionStatus.COMMITTED
    assert harness.current_mode == ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY


def test_abort_keeps_current_mode(tmp_path: Path) -> None:
    harness = RuntimeExperimentHarness(config=_config(tmp_path), clock=VirtualClock())
    contract = harness.create_contract()
    prepared = harness.prepare_mode_transition(
        contract.task_id,
        to_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        decision_id="dec-2",
        reason="test",
    )

    aborted = harness.abort_mode_transition(prepared.transition_id, reason="atomic_step_active")

    assert aborted.status == AutoModeTransitionStatus.ABORTED
    assert harness.current_mode == ControlMode.PERIODIC_CLOUD_SUPERVISION
