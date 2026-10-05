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

EXPECTED_CRASH_POINTS = {
    "C1_ACTIVE_CONTRACT_SAVED",
    "C2_RISK_SNAPSHOT_SAVED",
    "C3_AUTO_DECISION_SAVED",
    "C4_TRANSITION_PREPARED_BEFORE_COMMIT",
    "C5_REPLAN_SAVED_BEFORE_CAS_APPLY",
    "C6_CAS_APPLIED_BEFORE_ACK",
    "C7_EXECUTION_RECORD_SAVED_BEFORE_STATISTICS",
    "C8_OUTBOX_CLAIMED_BEFORE_ACK",
    "C9_CHECKPOINT_UPDATED_BEFORE_NEXT_STEP",
}


def test_sqlite_restart_covers_all_phase82_crash_points(tmp_path: Path) -> None:
    config = ExperimentConfig(
        experiment_id="phase82-crash-points",
        scenario_id="S15_SQLITE_RESTART_DURING_RUN",
        mode=ExperimentMode.AUTO,
        seed=0,
        repetitions=1,
        network_profile=NetworkProfileName.NORMAL,
        fault_profile=FaultProfile(name="restart"),
        task_profile=TaskProfile(name="pick_place"),
        cache_policy=CachePolicy.CACHE_ENABLED,
        risk_policy_version="risk-v1",
        supervision_period_ms=300,
        timeout_ms=30_000,
        artifact_dir=tmp_path,
    )
    execution = ExperimentRunner(config).run()
    recovered = {
        str(event.payload.get("crash_point"))
        for event in execution.events
        if event.event_type == "sqlite_restart_recovered"
    }

    assert EXPECTED_CRASH_POINTS.issubset(recovered)
    assert execution.result.repeated_completed_step_count == 0
    assert execution.result.result_status.value in {
        "SUCCESS",
        "NEEDS_OBSERVATION",
        "SAFETY_STOPPED",
    }
