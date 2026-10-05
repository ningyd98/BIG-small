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


def _config(tmp_path: Path, scenario_id: str = "S04_GRASP_FAILURE") -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=f"phase81-eteac-{scenario_id.lower()}",
        scenario_id=scenario_id,
        mode=ExperimentMode.ETEAC,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name=scenario_id.lower()),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=1_000,
        timeout_ms=30_000,
        artifact_dir=tmp_path / scenario_id,
    )


def test_eteac_consumes_real_retry_budget_without_periodic_supervision(tmp_path: Path) -> None:
    runner = ExperimentRunner(_config(tmp_path))
    execution = runner.run()
    contract = runner._active_contract
    assert contract is not None

    budget = runner.harness.event_controller.retry_budget(contract.task_id)
    checkpoint = runner.harness.event_repo.get_latest_execution_checkpoint(contract.task_id)
    step_failed = [event for event in execution.events if event.event_type == "step_failed"]

    assert execution.result.supervisory_decision_count == 0
    assert runner.harness.supervisor.decisions_for_task(contract.task_id) == []
    assert budget is not None
    assert budget.retry_count_used >= 1
    assert checkpoint is not None
    assert step_failed and step_failed[0].entity_id == "step-grasp"
    assert execution.result.retry_count >= 1
