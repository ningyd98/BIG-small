from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentEvent,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.reproducibility import stable_hash
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner


def _config(tmp_path: Path, run_dir: str) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="phase81-repro",
        scenario_id="S02_TARGET_MOVED",
        mode=ExperimentMode.AUTO,
        seed=7,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="target_moved"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path / run_dir,
    )


def _event_digest(events: list[ExperimentEvent]) -> str:
    payload = [
        {
            "t": event.virtual_time_ms,
            "event_type": event.event_type,
            "entity_id": event.entity_id,
            "payload": event.payload,
        }
        for event in events
        if event.event_type
        not in {
            "run_started",
            "run_completed",
        }
    ]
    return stable_hash(payload)


def test_same_config_and_seed_reproduce_result_and_event_trace(tmp_path: Path) -> None:
    first = ExperimentRunner(_config(tmp_path, "a")).run()
    second = ExperimentRunner(_config(tmp_path, "b")).run()

    assert first.result.result_hash == second.result.result_hash
    assert _event_digest(first.events) == _event_digest(second.events)
