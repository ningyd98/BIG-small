"""Phase 8 实验场景和指标回归测试，覆盖安全边界、证据契约和关键失败路径。"""

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
from cloud_edge_robot_arm.experiments.reproducibility import stable_hash
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner
from tests.experiment_event_semantics import semantic_event_digest


def _config(tmp_path: Path, seed: int) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="repro",
        scenario_id="S08_NETWORK_OUTAGE",
        mode=ExperimentMode.AUTO,
        seed=seed,
        repetitions=1,
        network_profile=NetworkProfileName.INTERMITTENT,
        fault_profile=FaultProfile(name="network_outage"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )


def test_same_config_and_seed_produce_same_result_hash_and_events(tmp_path: Path) -> None:
    first = ExperimentRunner(_config(tmp_path / "a", 9)).run()
    second = ExperimentRunner(_config(tmp_path / "b", 9)).run()

    assert first.result.result_hash == second.result.result_hash
    for run in (first, second):
        for event in run.events:
            assert event.payload_hash == stable_hash(
                {
                    "t": event.virtual_time_ms,
                    "event_type": event.event_type,
                    "entity_id": event.entity_id,
                    "payload": event.payload,
                }
            )
    assert semantic_event_digest(first.events) == semantic_event_digest(second.events)


def test_different_seed_can_change_seeded_network_trace(tmp_path: Path) -> None:
    first = ExperimentRunner(_config(tmp_path / "a", 9)).run()
    second = ExperimentRunner(_config(tmp_path / "b", 10)).run()

    assert first.result.seed != second.result.seed
    assert first.result.result_hash != second.result.result_hash
