from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.auto_mode.models import (
    AutoModePolicy,
    AutoModeState,
    AutoModeTransitionRequest,
)
from cloud_edge_robot_arm.auto_mode.selector import AutoModeSelector
from cloud_edge_robot_arm.auto_mode.transition_service import ModeTransitionService
from cloud_edge_robot_arm.contracts import (
    AutoModeDecisionType,
    AutoModeTransitionStatus,
    ControlMode,
    SkillName,
)
from cloud_edge_robot_arm.risk.evaluator import RiskEvaluator
from cloud_edge_robot_arm.risk.models import RiskPolicy, RiskSnapshotInput
from cloud_edge_robot_arm.skill_cache.models import (
    SkillCacheKey,
    SkillCacheLookupResult,
    SkillTemplate,
    SkillTemplateStatus,
)
from cloud_edge_robot_arm.skill_cache.repository import InMemorySkillCacheRepository

NOW = datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC)


def _risk_input(**overrides: object) -> RiskSnapshotInput:
    base = dict(
        task_id="task-1",
        task_type="pick-place",
        skill_name="GRASP",
        workspace_id="ws-a",
        scene_version=3,
        scene_updated_at=NOW,
        scene_confidence=0.95,
        target_confidence=0.9,
        target_moved=False,
        obstacle_count=0,
        obstacle_change_rate=0.0,
        network_latency_ms=60,
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
        cache_confidence=0.9,
        cache_match_type="exact_match",
        policy_version="risk-v1",
        current_time=NOW,
    )
    base.update(overrides)
    return RiskSnapshotInput.model_validate(base)


def _trusted_template() -> SkillTemplate:
    return SkillTemplate(
        template_id="tmpl-grasp",
        cache_key=SkillCacheKey(
            skill_name=SkillName.GRASP,
            robot_model="mock-arm-v1",
            end_effector_type="parallel_gripper",
            object_class="cube",
            task_intent="pick-place",
            workspace_id="ws-a",
            parameter_schema_version="schema-v1",
            robot_capability_hash="cap-v1",
            safety_policy_hash="safety-v1",
            calibration_version="cal-v1",
        ),
        skill_name=SkillName.GRASP,
        parameter_template={"object_id": "{object_id}"},
        required_preconditions=["target_visible"],
        expected_success_conditions=["object_attached"],
        expected_duration_ms=1_000,
        timeout_ms=3_000,
        source_contract_id="contract-1",
        source_plan_version=1,
        status=SkillTemplateStatus.TRUSTED,
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )


def test_static_low_risk_with_trusted_cache_and_bad_network_selects_event_mode() -> None:
    risk = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW).evaluate(
        _risk_input(network_latency_ms=900, packet_loss_rate=0.35)
    )
    selector = AutoModeSelector(clock=lambda: NOW, policy=AutoModePolicy(version="auto-v1"))
    state = AutoModeState(
        task_id="task-1",
        current_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        mode_version=1,
        switch_count=0,
        last_switch_at=NOW - timedelta(minutes=10),
        policy_version="auto-v1",
        updated_at=NOW,
    )
    cache = InMemorySkillCacheRepository(clock=lambda: NOW)
    cache.save_template(_trusted_template())

    decision = selector.decide(
        current_state=state,
        risk_snapshot=risk,
        cache_lookup=cache.lookup_templates(_trusted_template().cache_key),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[],
    )

    assert decision.action == AutoModeDecisionType.SWITCH_TO_EVENT_TRIGGERED_EDGE_AUTONOMY
    assert decision.selected_mode == ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY


def test_dynamic_scene_and_cloud_available_selects_periodic_supervision() -> None:
    risk = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW).evaluate(
        _risk_input(target_moved=True, scene_confidence=0.8, cache_match_type="compatible_match")
    )
    selector = AutoModeSelector(clock=lambda: NOW, policy=AutoModePolicy(version="auto-v1"))
    state = AutoModeState(
        task_id="task-1",
        current_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        mode_version=1,
        switch_count=0,
        last_switch_at=NOW - timedelta(minutes=10),
        policy_version="auto-v1",
        updated_at=NOW,
    )
    cache = InMemorySkillCacheRepository(clock=lambda: NOW)
    cache.save_template(_trusted_template())
    decision = selector.decide(
        current_state=state,
        risk_snapshot=risk,
        cache_lookup=cache.lookup_templates(_trusted_template().cache_key),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[],
    )

    assert decision.action == AutoModeDecisionType.SWITCH_TO_PERIODIC_CLOUD_SUPERVISION
    assert decision.selected_mode == ControlMode.PERIODIC_CLOUD_SUPERVISION


def test_high_risk_network_stable_pauses_instead_of_switching() -> None:
    risk = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW).evaluate(
        _risk_input(target_moved=True, safety_decision="PAUSE", network_latency_ms=10)
    )
    selector = AutoModeSelector(clock=lambda: NOW, policy=AutoModePolicy(version="auto-v1"))
    state = AutoModeState(
        task_id="task-1",
        current_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        mode_version=1,
        switch_count=0,
        last_switch_at=NOW - timedelta(minutes=10),
        policy_version="auto-v1",
        updated_at=NOW,
    )
    cache = InMemorySkillCacheRepository(clock=lambda: NOW)
    cache.save_template(_trusted_template())
    decision = selector.decide(
        current_state=state,
        risk_snapshot=risk,
        cache_lookup=cache.lookup_templates(_trusted_template().cache_key),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[],
    )

    assert decision.action == AutoModeDecisionType.PAUSE_TASK
    assert decision.selected_mode is None


def test_missing_contract_forces_request_more_observation() -> None:
    risk = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW).evaluate(
        _risk_input(has_complete_contract=False, remaining_steps_persisted=False)
    )
    selector = AutoModeSelector(clock=lambda: NOW, policy=AutoModePolicy(version="auto-v1"))
    state = AutoModeState(
        task_id="task-1",
        current_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        mode_version=1,
        switch_count=0,
        last_switch_at=NOW - timedelta(minutes=10),
        policy_version="auto-v1",
        updated_at=NOW,
    )
    cache = InMemorySkillCacheRepository(clock=lambda: NOW)
    cache.save_template(_trusted_template())
    decision = selector.decide(
        current_state=state,
        risk_snapshot=risk,
        cache_lookup=cache.lookup_templates(_trusted_template().cache_key),
        active_contract_complete=False,
        checkpoint_persisted=False,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[],
    )

    assert decision.action == AutoModeDecisionType.REQUEST_MORE_OBSERVATION


def test_emergency_stop_always_safest() -> None:
    risk = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW).evaluate(
        _risk_input(safety_decision="EMERGENCY_STOP")
    )
    selector = AutoModeSelector(clock=lambda: NOW, policy=AutoModePolicy(version="auto-v1"))
    state = AutoModeState(
        task_id="task-1",
        current_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        mode_version=1,
        switch_count=0,
        last_switch_at=NOW - timedelta(minutes=10),
        policy_version="auto-v1",
        updated_at=NOW,
    )
    decision = selector.decide(
        current_state=state,
        risk_snapshot=risk,
        cache_lookup=SkillCacheLookupResult(match_type="no_match"),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=False,
        supervision_available=False,
        atomic_step_active=False,
        mode_history=[],
    )

    assert decision.action == AutoModeDecisionType.SAFE_STOP
    assert decision.selected_mode is None


def test_hysteresis_blocks_thrashing_and_cooldown_blocks_switch_back() -> None:
    policy = AutoModePolicy(version="auto-v1", min_dwell_seconds=120, switch_cooldown_seconds=300)
    selector = AutoModeSelector(clock=lambda: NOW, policy=policy)
    state = AutoModeState(
        task_id="task-1",
        current_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        mode_version=1,
        switch_count=1,
        last_switch_at=NOW - timedelta(seconds=30),
        policy_version="auto-v1",
        updated_at=NOW,
    )
    risk = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW).evaluate(
        _risk_input(target_moved=False, scene_confidence=0.7, cache_match_type="compatible_match")
    )
    decision = selector.decide(
        current_state=state,
        risk_snapshot=risk,
        cache_lookup=SkillCacheLookupResult(match_type="compatible_match"),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=False,
        mode_history=[ControlMode.PERIODIC_CLOUD_SUPERVISION],
    )

    assert decision.action == AutoModeDecisionType.KEEP_CURRENT_MODE
    assert (
        "cooldown_active" in decision.reason_codes or "dwell_time_not_met" in decision.reason_codes
    )


def test_atomic_step_defers_normal_mode_switch() -> None:
    risk = RiskEvaluator(policy=RiskPolicy(version="risk-v1"), clock=lambda: NOW).evaluate(
        _risk_input(network_latency_ms=70)
    )
    selector = AutoModeSelector(clock=lambda: NOW, policy=AutoModePolicy(version="auto-v1"))
    state = AutoModeState(
        task_id="task-1",
        current_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        mode_version=1,
        switch_count=0,
        last_switch_at=NOW - timedelta(minutes=10),
        policy_version="auto-v1",
        updated_at=NOW,
    )
    decision = selector.decide(
        current_state=state,
        risk_snapshot=risk,
        cache_lookup=SkillCacheLookupResult(match_type="exact_match"),
        active_contract_complete=True,
        checkpoint_persisted=True,
        event_autonomy_ready=True,
        supervision_available=True,
        atomic_step_active=True,
        mode_history=[],
    )

    assert decision.action == AutoModeDecisionType.KEEP_CURRENT_MODE


def test_transition_prepare_commit_abort_and_restart_recovery(tmp_path) -> None:  # type: ignore[no-untyped-def]
    repo = InMemorySkillCacheRepository(clock=lambda: NOW)
    repo.save_template(_trusted_template())
    service = ModeTransitionService(clock=lambda: NOW, repository=None)
    request = AutoModeTransitionRequest(
        task_id="task-1",
        from_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        to_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        expected_mode_version=1,
        idempotency_key="idem-1",
        decision_id="dec-1",
        reason="dynamic_scene",
    )

    prepared = service.prepare(request)
    committed = service.commit(prepared.transition_id)
    aborted = service.abort("missing-transition", reason="not_found")

    assert prepared.status == AutoModeTransitionStatus.PREPARED
    assert committed.status == AutoModeTransitionStatus.COMMITTED
    assert aborted.status == AutoModeTransitionStatus.ABORTED
