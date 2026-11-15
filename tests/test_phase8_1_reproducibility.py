"""Phase 8.1 PCSC/ETEAC 集成回归测试，覆盖安全边界、证据契约和关键失败路径。"""

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
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner
from tests.experiment_event_semantics import semantic_event_digest


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
    """比较完整语义轨迹；事务随机身份做一对一别名，保留跨事件关联。"""
    return semantic_event_digest(events, exclude_lifecycle=True)


def test_same_config_and_seed_reproduce_result_and_event_trace(tmp_path: Path) -> None:
    first = ExperimentRunner(_config(tmp_path, "a")).run()
    second = ExperimentRunner(_config(tmp_path, "b")).run()

    assert first.result.result_hash == second.result.result_hash
    assert _event_digest(first.events) == _event_digest(second.events)


def test_event_digest_keeps_transition_lineage_time_and_payload(tmp_path: Path) -> None:
    events = ExperimentRunner(_config(tmp_path, "control")).run().events
    reference = _event_digest(events)
    index = next(
        i for i, event in enumerate(events) if event.event_type == "mode_transition_committed"
    )
    original = events[index]
    prepared = next(event for event in events if event.event_type == "mode_transition_prepared")
    assert original.entity_id == prepared.entity_id
    mutations = [
        {"entity_id": "different-transition"},
        {"virtual_time_ms": original.virtual_time_ms + 1},
        {"payload": {**original.payload, "to_mode": "PERIODIC_CLOUD_SUPERVISION"}},
    ]
    for mutation in mutations:
        changed = list(events)
        changed[index] = original.model_copy(update=mutation, deep=True)
        assert _event_digest(changed) != reference, mutation

    transitions = [
        event
        for event in events
        if event.event_type
        in {
            "mode_transition_prepared",
            "mode_transition_deferred",
            "mode_transition_committed",
        }
    ]
    assert len(transitions) == 3
    distinct = transitions + [
        event.model_copy(update={"entity_id": "second-transition"}, deep=True)
        for event in transitions
    ]
    merged = transitions + transitions
    assert _event_digest(distinct) != _event_digest(merged)
    non_transition = next(
        i for i, event in enumerate(events) if event.event_type == "risk_snapshot_saved"
    )
    changed = list(events)
    changed[non_transition] = events[non_transition].model_copy(
        update={"entity_id": "different-risk-snapshot"}, deep=True
    )
    assert _event_digest(changed) != reference
