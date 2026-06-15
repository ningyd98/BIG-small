from __future__ import annotations

from pathlib import Path

from cloud_edge_robot_arm.contracts import ControlMode
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


def _config(
    tmp_path: Path, mode: ExperimentMode, scenario_id: str = "S01_NORMAL_STATIC"
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"exp-{mode.value.lower()}",
        scenario_id=scenario_id,
        mode=mode,
        seed=1,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="default"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )


def test_pcsc_eteac_and_auto_run_through_unified_interface(tmp_path: Path) -> None:
    results = [
        ExperimentRunner(_config(tmp_path, mode)).run_once()
        for mode in (ExperimentMode.PCSC, ExperimentMode.ETEAC, ExperimentMode.AUTO)
    ]

    assert [result.mode for result in results] == [
        ExperimentMode.PCSC,
        ExperimentMode.ETEAC,
        ExperimentMode.AUTO,
    ]
    assert all(result.result_status == ResultStatus.SUCCESS for result in results)
    assert all(result.simulated_collision_count == 0 for result in results)
    assert results[0].cloud_invocation_count >= results[1].cloud_invocation_count


def test_auto_is_selector_not_third_execution_path(tmp_path: Path) -> None:
    result = ExperimentRunner(_config(tmp_path, ExperimentMode.AUTO)).run_once()

    assert result.initial_mode in {
        ControlMode.PERIODIC_CLOUD_SUPERVISION,
        ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
    }
    assert result.final_mode in {
        ControlMode.PERIODIC_CLOUD_SUPERVISION,
        ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
    }
    assert result.initial_mode != ControlMode.AUTO
    assert result.final_mode != ControlMode.AUTO
