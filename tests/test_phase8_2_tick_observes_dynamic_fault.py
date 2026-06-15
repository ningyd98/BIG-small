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


def test_tick_after_target_move_observes_dynamic_scene(tmp_path: Path) -> None:
    config = ExperimentConfig(
        experiment_id="phase82-tick-observes-target-move",
        scenario_id="S02_TARGET_MOVED",
        mode=ExperimentMode.PCSC,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="target-move"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=300,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )
    execution = ExperimentRunner(config).run()
    injected_at = next(
        event.virtual_time_ms
        for event in execution.events
        if event.event_type == "fault_injected"
        and event.payload.get("fault_type") == "TARGET_MOVED"
    )
    post_fault_ticks = [
        event
        for event in execution.events
        if event.event_type == "pcsc_tick" and event.virtual_time_ms > injected_at
    ]
    detections = [
        event
        for event in execution.events
        if event.event_type == "fault_detected"
        and event.payload.get("fault_type") == "TARGET_MOVED"
    ]

    assert post_fault_ticks
    assert any(event.payload.get("target_moved") is True for event in post_fault_ticks)
    assert detections
    assert detections[0].virtual_time_ms > injected_at
