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


def _config(tmp_path: Path, *, period_ms: int) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"phase82-detection-{period_ms}",
        scenario_id="S02_TARGET_MOVED",
        mode=ExperimentMode.PCSC,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="target-move"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=period_ms,
        timeout_ms=30_000,
        artifact_dir=tmp_path / str(period_ms),
    )


def test_fault_detection_is_not_recorded_at_injection_time(tmp_path: Path) -> None:
    execution = ExperimentRunner(_config(tmp_path, period_ms=300)).run()
    injected_at = next(
        event.virtual_time_ms for event in execution.events if event.event_type == "fault_injected"
    )
    detected_at = next(
        event.virtual_time_ms for event in execution.events if event.event_type == "fault_detected"
    )

    assert detected_at > injected_at
    assert execution.result.fault_detection_latency_ms == detected_at - injected_at


def test_pcsc_detection_latency_depends_on_supervision_period(tmp_path: Path) -> None:
    fast = ExperimentRunner(_config(tmp_path, period_ms=200)).run().result
    slow = ExperimentRunner(_config(tmp_path, period_ms=700)).run().result

    assert fast.fault_detection_latency_ms is not None
    assert slow.fault_detection_latency_ms is not None
    assert fast.fault_detection_latency_ms != slow.fault_detection_latency_ms
