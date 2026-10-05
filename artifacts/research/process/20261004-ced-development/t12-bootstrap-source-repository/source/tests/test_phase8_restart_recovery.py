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
from cloud_edge_robot_arm.experiments.runner import ExperimentRunner


def test_sqlite_restart_during_run_recovers_without_duplicate_application(
    tmp_path: Path,
) -> None:
    config = ExperimentConfig(
        experiment_id="restart",
        scenario_id="S15_SQLITE_RESTART_DURING_RUN",
        mode=ExperimentMode.AUTO,
        seed=2,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="sqlite_restart"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )

    result = ExperimentRunner(config).run_once()

    assert result.mode_switch_count <= 1
    assert result.repeated_completed_step_count == 0
    assert result.terminal_reason in {"completed", "needs_observation_after_restart"}
    assert result.invariant_violations == []
