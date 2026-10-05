"""Phase 8.2 故障交错和敏感性回归测试，覆盖安全边界、证据契约和关键失败路径。"""

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


def test_eteac_normal_task_has_no_periodic_ticks(tmp_path: Path) -> None:
    config = ExperimentConfig(
        experiment_id="phase82-eteac-no-ticks",
        scenario_id="S01_NORMAL_STATIC",
        mode=ExperimentMode.ETEAC,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="normal"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=250,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )
    execution = ExperimentRunner(config).run()

    assert not [event for event in execution.events if event.event_type == "pcsc_tick"]
    assert execution.result.supervisory_decision_count == 0
