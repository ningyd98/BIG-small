"""Phase 8.1 PCSC/ETEAC 集成回归测试，覆盖安全边界、证据契约和关键失败路径。"""

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


def _config(tmp_path: Path) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="phase81-crash",
        scenario_id="S15_SQLITE_RESTART_DURING_RUN",
        mode=ExperimentMode.ETEAC,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="restart"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )


def test_sqlite_restart_rebuilds_runtime_and_preserves_terminal_evidence(tmp_path: Path) -> None:
    runner = ExperimentRunner(_config(tmp_path))
    initial_repo_id = id(runner.harness.event_repo)

    execution = runner.run()
    contract = runner._active_contract
    assert contract is not None

    restart_events = [
        event for event in execution.events if event.event_type == "runtime_restarted"
    ]
    completed_ids = [
        event.entity_id for event in execution.events if event.event_type == "step_completed"
    ]

    assert restart_events
    assert id(runner.harness.event_repo) != initial_repo_id
    assert runner.harness.event_repo.get_active_contract(contract.task_id) is not None
    assert runner.harness.event_repo.get_completion_summary_for_task(contract.task_id) is not None
    assert execution.result.completed_step_count == len(set(completed_ids))
    assert execution.result.repeated_completed_step_count == 0
