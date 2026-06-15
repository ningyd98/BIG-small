from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from cloud_edge_robot_arm.contracts import ControlMode
from cloud_edge_robot_arm.experiments.models import (
    AblationType,
    CachePolicy,
    ExperimentConfig,
    ExperimentMode,
    FaultProfile,
    NetworkProfile,
    NetworkProfileName,
    TaskProfile,
)
from cloud_edge_robot_arm.experiments.profiles import get_network_profile
from cloud_edge_robot_arm.experiments.reproducibility import config_hash
from cloud_edge_robot_arm.experiments.scenario import scenario_registry


def test_experiment_config_accepts_phase8_smoke_defaults(tmp_path: Path) -> None:
    config = ExperimentConfig(
        experiment_id="exp-smoke",
        scenario_id="S01_NORMAL_STATIC",
        mode=ExperimentMode.PCSC,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="none"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )

    assert config.mode.to_control_mode() == ControlMode.PERIODIC_CLOUD_SUPERVISION
    assert config.config_schema_version == "phase8.v1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed", -1),
        ("repetitions", 0),
        ("supervision_period_ms", 0),
        ("timeout_ms", -1),
    ],
)
def test_experiment_config_rejects_invalid_numeric_values(
    tmp_path: Path, field: str, value: int
) -> None:
    data = {
        "experiment_id": "exp-invalid",
        "scenario_id": "S01_NORMAL_STATIC",
        "mode": ExperimentMode.ETEAC,
        "seed": 1,
        "repetitions": 1,
        "network_profile": NetworkProfileName.GOOD,
        "fault_profile": FaultProfile(name="none"),
        "task_profile": TaskProfile(name="pick_place"),
        "cache_policy": CachePolicy.CACHE_ENABLED,
        "risk_policy_version": "risk-v1",
        "supervision_period_ms": 1_000,
        "timeout_ms": 30_000,
        "artifact_dir": tmp_path,
    }
    data[field] = value

    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate(data)


def test_network_profile_validation_rejects_bad_values() -> None:
    good = get_network_profile(NetworkProfileName.GOOD)
    assert good.base_latency_ms == 20
    assert good.jitter_ms == 0
    assert good.loss_rate == 0.0

    with pytest.raises(ValidationError):
        NetworkProfile.model_validate({**good.model_dump(), "loss_rate": 1.5})


def test_scenario_registry_contains_unique_required_scenarios() -> None:
    registry = scenario_registry()
    scenario_ids = [scenario.scenario_id for scenario in registry]

    assert len(scenario_ids) == 15
    assert len(scenario_ids) == len(set(scenario_ids))
    assert scenario_ids[0] == "S01_NORMAL_STATIC"
    assert scenario_ids[-1] == "S15_SQLITE_RESTART_DURING_RUN"


def test_config_hash_is_stable_and_includes_ablations(tmp_path: Path) -> None:
    base = ExperimentConfig(
        experiment_id="exp-hash",
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
        artifact_dir=tmp_path,
    )
    same = base.model_copy(deep=True)
    ablated = base.model_copy(update={"ablations": [AblationType.A2_AUTO_WITHOUT_NETWORK_SIGNAL]})

    assert config_hash(base) == config_hash(same)
    assert config_hash(base) != config_hash(ablated)
