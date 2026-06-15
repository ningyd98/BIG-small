from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.contracts import ControlMode, RiskLevel
from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    ResultStatus,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner


def _auto_config(tmp_path: Path, scenario_id: str, network: NetworkProfileName) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"auto-{scenario_id.lower()}",
        scenario_id=scenario_id,
        mode=ExperimentMode.AUTO,
        seed=3,
        repetitions=1,
        network_profile=network,
        fault_profile=FaultProfile(name=scenario_id.lower()),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )


def test_auto_prefers_event_autonomy_when_network_is_degraded(tmp_path: Path) -> None:
    result = ExperimentRunner(
        _auto_config(tmp_path, "S07_NETWORK_DEGRADED", NetworkProfileName.DEGRADED)
    ).run_once()

    assert result.final_mode == ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY
    assert result.mode_switch_count >= 1


def test_auto_requests_observation_for_target_lost(tmp_path: Path) -> None:
    result = ExperimentRunner(
        _auto_config(tmp_path, "S05_TARGET_LOST", NetworkProfileName.NORMAL)
    ).run_once()

    assert result.result_status == ResultStatus.NEEDS_OBSERVATION
    assert result.final_risk_level == RiskLevel.INSUFFICIENT_EVIDENCE


def test_auto_emergency_stop_does_not_switch_around_safety(tmp_path: Path) -> None:
    result = ExperimentRunner(
        _auto_config(tmp_path, "S14_EMERGENCY_STOP", NetworkProfileName.NORMAL)
    ).run_once()

    assert result.result_status == ResultStatus.SAFETY_STOPPED
    assert result.final_risk_level == RiskLevel.CRITICAL
    assert result.emergency_stop_count >= 1
    assert result.mode_switch_count == 0
