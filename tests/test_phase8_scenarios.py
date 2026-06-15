from __future__ import annotations

from pathlib import Path

import pytest

from cloud_edge_robot_arm.experiments.models import (
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfileName,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner
from cloud_edge_robot_arm.experiments.scenario import scenario_registry


@pytest.mark.parametrize("scenario", scenario_registry(), ids=lambda s: s.scenario_id)
def test_each_required_scenario_has_key_metadata(scenario) -> None:  # type: ignore[no-untyped-def]
    assert scenario.description
    assert scenario.expected_invariants
    assert scenario.allowed_result_statuses
    assert scenario.maximum_virtual_duration_ms > 0


@pytest.mark.parametrize(
    "scenario_id",
    [
        "S01_NORMAL_STATIC",
        "S02_TARGET_MOVED",
        "S03_OBSTACLE_INSERTED",
        "S04_GRASP_FAILURE",
        "S05_TARGET_LOST",
        "S06_PERCEPTION_DEGRADED",
        "S07_NETWORK_DEGRADED",
        "S08_NETWORK_OUTAGE",
        "S09_CLOUD_UNAVAILABLE",
        "S10_STALE_DUPLICATE_REORDERED_COMMAND",
        "S11_SKILL_CACHE_HIT",
        "S12_SKILL_CACHE_QUARANTINE",
        "S13_MODE_OSCILLATION_PRESSURE",
        "S14_EMERGENCY_STOP",
        "S15_SQLITE_RESTART_DURING_RUN",
    ],
)
def test_each_required_scenario_runs_one_smoke_case(tmp_path: Path, scenario_id: str) -> None:
    config = ExperimentConfig(
        experiment_id=f"scenario-{scenario_id.lower()}",
        scenario_id=scenario_id,
        mode=ExperimentMode.AUTO,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name=scenario_id.lower()),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )

    result = ExperimentRunner(config).run_once()

    assert (
        result.result_status
        in scenario_registry()[int(scenario_id[1:3]) - 1].allowed_result_statuses
    )
    assert result.repeated_completed_step_count == 0
    assert result.simulated_collision_count == 0
