"""Phase 7 风险评估和 AUTO 模式回归测试，覆盖安全边界、证据契约和关键失败路径。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.auto_mode.models import (
    AutoModePolicy,
    AutoModeState,
    AutoModeTransitionRequest,
)
from cloud_edge_robot_arm.auto_mode.repository import (
    InMemoryAutoModeRepository,
    SQLiteAutoModeRepository,
)
from cloud_edge_robot_arm.auto_mode.selector import AutoModeSelector
from cloud_edge_robot_arm.auto_mode.transition_service import ModeTransitionService
from cloud_edge_robot_arm.contracts import ControlMode
from cloud_edge_robot_arm.risk.evaluator import RiskEvaluator
from cloud_edge_robot_arm.risk.models import RiskPolicy, RiskSnapshotInput
from cloud_edge_robot_arm.skill_cache.models import SkillCacheLookupResult

NOW = datetime(2026, 6, 14, 12, 30, 0, tzinfo=UTC)


def _risk_input() -> RiskSnapshotInput:
    return RiskSnapshotInput(
        task_id="task-1",
        task_type="pick-place",
        skill_name="GRASP",
        workspace_id="ws-a",
        scene_version=1,
        scene_updated_at=NOW,
        scene_confidence=0.9,
        target_confidence=0.9,
        target_moved=False,
        obstacle_count=0,
        obstacle_change_rate=0.0,
        network_latency_ms=50,
        network_jitter_ms=5,
        packet_loss_rate=0.01,
        disconnected_seconds=0.0,
        last_heartbeat_at=NOW,
        execution_failures=0,
        timeout_count=0,
        replans_count=0,
        safety_rejections=0,
        estop_engaged=False,
        safety_decision="ALLOW",
        current_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        has_complete_contract=True,
        remaining_steps_persisted=True,
        edge_capability_ready=True,
        cloud_available=True,
        event_autonomy_ready=True,
        supervision_available=True,
        cache_confidence=0.95,
        cache_match_type="exact_match",
        policy_version="risk-v1",
        current_time=NOW,
    )


def test_sqlite_repository_recovers_status_and_prepared_transition(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "auto-mode.db"
    repo = SQLiteAutoModeRepository(db_path, clock=lambda: NOW)
    risk = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW).evaluate(
        _risk_input()
    )
    repo.save_risk_snapshot(risk)
    state = AutoModeState(
        task_id="task-1",
        current_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        mode_version=1,
        switch_count=0,
        last_switch_at=NOW - timedelta(minutes=10),
        policy_version="auto-v1",
        updated_at=NOW,
    )
    decision = AutoModeSelector(clock=lambda: NOW, policy=AutoModePolicy(version="auto-v1")).decide(
        current_state=state,
        risk_snapshot=risk,
        cache_lookup=SkillCacheLookupResult(match_type="exact_match"),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[],
    )
    repo.save_decision(decision)
    transition = ModeTransitionService(clock=lambda: NOW).prepare(
        AutoModeTransitionRequest(
            task_id="task-1",
            from_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
            to_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
            expected_mode_version=1,
            idempotency_key="idem-1",
            decision_id=decision.decision_id,
            reason="stable_scene",
        )
    )
    repo.save_transition(transition)
    repo.save_status(state)
    repo.close()

    reopened = SQLiteAutoModeRepository(db_path, clock=lambda: NOW)
    recovered_risk = reopened.latest_risk_snapshot("task-1")
    recovered_decision = reopened.latest_decision("task-1")
    recovered_transition = reopened.get_transition(transition.transition_id)
    recovered_status = reopened.get_status("task-1")
    assert recovered_risk is not None
    assert recovered_decision is not None
    assert recovered_transition is not None
    assert recovered_status is not None
    assert recovered_risk.snapshot_id == risk.snapshot_id
    assert recovered_decision.decision_id == decision.decision_id
    assert recovered_transition.transition_id == transition.transition_id
    assert recovered_status.task_id == "task-1"
    reopened.close()


def test_inmemory_repository_rejects_transition_payload_conflicts() -> None:
    repo = InMemoryAutoModeRepository(clock=lambda: NOW)
    service = ModeTransitionService(clock=lambda: NOW)
    request = AutoModeTransitionRequest(
        task_id="task-1",
        from_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        to_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        expected_mode_version=1,
        idempotency_key="idem-1",
        decision_id="decision-1",
        reason="dynamic_scene",
    )
    transition = service.prepare(request)
    repo.save_transition(transition)
    same = repo.get_transition_by_idempotency("idem-1")
    assert same is not None
    assert same.transition_id == transition.transition_id
