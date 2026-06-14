"""Phase 6 recovery and replanning tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.cloud.replanning.adapters import (
    MockReplannerAdapter,
    RuleBasedReplannerAdapter,
)
from cloud_edge_robot_arm.cloud.replanning.service import LocalReplanningService
from cloud_edge_robot_arm.cloud.replanning.validators import (
    CompletedStepsProtectionValidator,
    ReplanScopeValidator,
)
from cloud_edge_robot_arm.contracts.models import (
    ControlMode,
    EdgeEvent,
    EdgeEventType,
    EventSeverity,
    FailurePolicy,
    LocalReplanningRequest,
    RecoveryAction,
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.edge.recovery.manager import LocalRecoveryManager
from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetService
from cloud_edge_robot_arm.edge.summaries.failure import FailureSummaryBuilder
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)


def _make_contract(**overrides: object) -> TaskContract:
    defaults: dict[str, object] = {
        "task_id": "task-test-001",
        "plan_version": 1,
        "command_seq": 1,
        "timestamp": NOW,
        "control_mode": ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        "issued_at": NOW,
        "valid_until": NOW + timedelta(minutes=5),
        "user_instruction": "Pick red cube and place in bin A",
        "scene_version": 1,
        "expected_scene_version": 1,
        "task_target": TaskTarget(object_id="obj-1", object_class="cube", target_region_id="bin-a"),
        "steps": [
            TaskStep(
                step_id="s1",
                skill=SkillName.APPROACH,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s2",
                skill=SkillName.GRASP,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s3",
                skill=SkillName.LIFT,
                parameters={},
                expected_duration_ms=1500,
                timeout_ms=4000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s4",
                skill=SkillName.PLACE,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
        ],
        "safety_constraints": SafetyConstraints(
            max_joint_velocity=1.0,
            max_tcp_velocity=0.5,
            minimum_safe_height=0.08,
            workspace_id="ws-1",
        ),
        "failure_policy": FailurePolicy(
            local_retry_limit=3,
            on_timeout="pause",
            on_safety_rejection="stop",
            on_network_loss="pause",
        ),
        "completion_criteria": ["object_in_bin_a"],
    }
    defaults.update(overrides)
    return TaskContract(**defaults)  # type: ignore[arg-type]


# ── RetryBudgetService ─────────────────────────────────────────────────


def test_recovery_budget_initialized_from_contract() -> None:
    mgr = RetryBudgetService(repository=InMemoryEventAutonomyRepository())
    contract = _make_contract()
    budget = mgr.initialize("task-test-001", contract)
    assert budget.effective_retry_limit == 3
    assert budget.remaining_retries == 3
    assert budget.retry_count_used == 0


def test_recovery_budget_can_attempt() -> None:
    mgr = RetryBudgetService(repository=InMemoryEventAutonomyRepository())
    contract = _make_contract()
    mgr.initialize("task-test-001", contract)
    allowed, reason = mgr.can_attempt("task-test-001")
    assert allowed
    assert reason == "OK"


def test_recovery_budget_exhausted() -> None:
    mgr = RetryBudgetService(repository=InMemoryEventAutonomyRepository())
    contract = _make_contract()
    mgr.initialize("task-test-001", contract)
    for _ in range(3):
        mgr.consume("task-test-001")
    allowed, reason = mgr.can_attempt("task-test-001")
    assert not allowed
    assert reason == "RETRY_BUDGET_EXHAUSTED"


def test_recovery_budget_deduct_reduces_count() -> None:
    mgr = RetryBudgetService(repository=InMemoryEventAutonomyRepository())
    contract = _make_contract()
    mgr.initialize("task-test-001", contract)
    updated = mgr.consume("task-test-001")
    assert updated is not None
    assert updated.remaining_retries == 2
    assert updated.retry_count_used == 1


def test_recovery_budget_unknown_task() -> None:
    mgr = RetryBudgetService(repository=InMemoryEventAutonomyRepository())
    allowed, reason = mgr.can_attempt("nonexistent")
    assert not allowed
    assert reason == "NO_BUDGET_INITIALIZED"


# ── LocalRecoveryManager ───────────────────────────────────────────────


def test_recovery_grasp_failure_allows_retry() -> None:
    mgr = LocalRecoveryManager(
        budget_manager=RetryBudgetService(repository=InMemoryEventAutonomyRepository())
    )
    contract = _make_contract()
    mgr._budget_manager.initialize("task-test-001", contract)

    event = EdgeEvent(
        task_id="task-test-001",
        plan_version=1,
        command_seq=1,
        timestamp=NOW,
        event_id="evt-001",
        event_type=EdgeEventType.GRASP_FAILED,
        step_id="s2",
        severity=EventSeverity.ERROR,
    )
    decision = mgr.evaluate(event, contract)
    assert decision.action == RecoveryAction.RETRY_SAME_SKILL
    assert decision.allowed


def test_recovery_safety_rejected_pauses() -> None:
    mgr = LocalRecoveryManager()
    event = EdgeEvent(
        task_id="task-test-001",
        plan_version=1,
        command_seq=1,
        timestamp=NOW,
        event_id="evt-002",
        event_type=EdgeEventType.SAFETY_REJECTED,
        step_id="s2",
        severity=EventSeverity.ERROR,
    )
    decision = mgr.evaluate(event)
    assert decision.action == RecoveryAction.PAUSE_AND_REPORT
    assert not decision.allowed


def test_recovery_critical_event_stops() -> None:
    mgr = LocalRecoveryManager()
    event = EdgeEvent(
        task_id="task-test-001",
        plan_version=1,
        command_seq=1,
        timestamp=NOW,
        event_id="evt-003",
        event_type=EdgeEventType.EMERGENCY_STOP_TRIGGERED,
        step_id="s2",
        severity=EventSeverity.CRITICAL,
    )
    decision = mgr.evaluate(event)
    assert decision.action == RecoveryAction.STOP_AND_REPORT
    assert not decision.allowed


def test_recovery_target_moved_requests_replan() -> None:
    mgr = LocalRecoveryManager()
    event = EdgeEvent(
        task_id="task-test-001",
        plan_version=1,
        command_seq=1,
        timestamp=NOW,
        event_id="evt-004",
        event_type=EdgeEventType.TARGET_MOVED,
        step_id="s2",
        severity=EventSeverity.WARNING,
    )
    decision = mgr.evaluate(event)
    assert decision.action == RecoveryAction.REQUEST_CLOUD_REPLAN


def test_recovery_budget_exhausted_after_retries() -> None:
    budget_mgr = RetryBudgetService(repository=InMemoryEventAutonomyRepository())
    contract = _make_contract()
    budget_mgr.initialize("task-test-001", contract)
    for _ in range(3):
        budget_mgr.consume("task-test-001")

    mgr = LocalRecoveryManager(budget_manager=budget_mgr)
    event = EdgeEvent(
        task_id="task-test-001",
        plan_version=1,
        command_seq=1,
        timestamp=NOW,
        event_id="evt-005",
        event_type=EdgeEventType.GRASP_FAILED,
        step_id="s2",
        severity=EventSeverity.ERROR,
    )
    decision = mgr.evaluate(event, contract)
    assert decision.action == RecoveryAction.REQUEST_CLOUD_REPLAN


# ── FailureSummaryBuilder ──────────────────────────────────────────────


def test_failure_summary_builder_grasp_failure() -> None:
    builder = FailureSummaryBuilder()
    contract = _make_contract()
    event = EdgeEvent(
        task_id="task-test-001",
        plan_version=1,
        command_seq=1,
        timestamp=NOW,
        event_id="evt-006",
        event_type=EdgeEventType.GRASP_FAILED,
        step_id="s2",
        severity=EventSeverity.ERROR,
        scene_version=1,
    )
    summary = builder.build(event=event, contract=contract, completed_step_ids=["s1"])
    assert summary.failed_step_id == "s2"
    assert summary.completed_step_ids == ["s1"]
    assert summary.failure_type == "grasp_failure"
    assert len(summary.summary_hash) > 0
    assert summary.confirmed_facts.get("event_type") == "GRASP_FAILED"
    assert "possible_grasp_offset" in summary.suspected_causes


def test_failure_summary_builder_deterministic() -> None:
    builder = FailureSummaryBuilder()
    contract = _make_contract()
    event = EdgeEvent(
        task_id="task-test-001",
        plan_version=1,
        command_seq=1,
        timestamp=NOW,
        event_id="evt-007",
        event_type=EdgeEventType.GRASP_FAILED,
        step_id="s2",
        severity=EventSeverity.ERROR,
    )
    summary1 = builder.build(event=event, contract=contract)
    summary2 = builder.build(event=event, contract=contract)
    assert summary1.summary_hash == summary2.summary_hash
    assert summary1.failure_type == summary2.failure_type


# ── CompletedStepsProtectionValidator ──────────────────────────────────


def test_completed_steps_validator_accepts_valid() -> None:
    validator = CompletedStepsProtectionValidator()
    completed = ["s1"]
    original = [
        TaskStep(
            step_id="s1",
            skill=SkillName.APPROACH,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
        TaskStep(
            step_id="s2",
            skill=SkillName.GRASP,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
    ]
    new = [
        TaskStep(
            step_id="s1",
            skill=SkillName.APPROACH,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
        TaskStep(
            step_id="s2-new",
            skill=SkillName.GRASP,
            parameters={"adjusted": True},
            expected_duration_ms=3000,
            timeout_ms=8000,
            retry_limit=3,
        ),
    ]
    is_valid, errors = validator.validate(completed, original, new)
    assert is_valid
    assert errors == []


def test_completed_steps_validator_rejects_missing_step() -> None:
    validator = CompletedStepsProtectionValidator()
    completed = ["s1", "s2"]
    original = [
        TaskStep(
            step_id="s1",
            skill=SkillName.APPROACH,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
        TaskStep(
            step_id="s2",
            skill=SkillName.GRASP,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
    ]
    new = [
        TaskStep(
            step_id="s1",
            skill=SkillName.APPROACH,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
    ]
    is_valid, errors = validator.validate(completed, original, new)
    assert not is_valid
    assert any("s2" in e for e in errors)


def test_completed_steps_validator_rejects_skill_change() -> None:
    validator = CompletedStepsProtectionValidator()
    completed = ["s1"]
    original = [
        TaskStep(
            step_id="s1",
            skill=SkillName.APPROACH,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
    ]
    new = [
        TaskStep(
            step_id="s1",
            skill=SkillName.GRASP,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
    ]
    is_valid, errors = validator.validate(completed, original, new)
    assert not is_valid
    assert any("skill changed" in e for e in errors)


# ── ReplanScopeValidator ──────────────────────────────────────────────


def test_replan_scope_validator_observation_no_steps() -> None:
    validator = ReplanScopeValidator()
    is_valid, msg = validator.validate("MORE_OBSERVATION_REQUIRED", "Need more data", [])
    assert is_valid
    assert msg == "OK"


def test_replan_scope_validator_observation_rejects_steps() -> None:
    validator = ReplanScopeValidator()
    is_valid, msg = validator.validate(
        "MORE_OBSERVATION_REQUIRED",
        "Need more data",
        [
            TaskStep(
                step_id="x",
                skill=SkillName.HOME,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
            )
        ],
    )
    assert not is_valid


def test_replan_scope_validator_safety_stop_no_steps() -> None:
    validator = ReplanScopeValidator()
    is_valid, msg = validator.validate("NO_REPLAN_SAFETY_STOP", "Unsafe", [])
    assert is_valid
    assert msg == "OK"


# ── ReplannerAdapter ──────────────────────────────────────────────────


def test_mock_replanner_returns_canned() -> None:
    adapter = MockReplannerAdapter()
    request = LocalReplanningRequest(
        request_id="req-001",
        trigger_event_id="evt-006",
        robot_id="robot-001",
        task_id="task-test-001",
        current_plan_version=1,
        current_command_seq=1,
        completed_step_ids=["s1"],
        failed_step_id="s2",
    )
    response = adapter.replan(request)
    assert response.outcome == "REPLANNED"
    assert response.new_plan_version == 2
    assert response.new_command_seq == 2
    assert len(response.new_steps) > 0


def test_rule_based_replanner_observation_scope() -> None:
    adapter = RuleBasedReplannerAdapter()
    request = LocalReplanningRequest(
        request_id="req-002",
        trigger_event_id="evt-007",
        robot_id="robot-001",
        task_id="task-test-001",
        current_plan_version=1,
        current_command_seq=1,
        requested_replan_scope="MORE_OBSERVATION_REQUIRED",
    )
    response = adapter.replan(request)
    assert response.outcome == "REQUEST_MORE_OBSERVATION"


def test_rule_based_replanner_safety_stop() -> None:
    adapter = RuleBasedReplannerAdapter()
    request = LocalReplanningRequest(
        request_id="req-003",
        trigger_event_id="evt-008",
        robot_id="robot-001",
        task_id="task-test-001",
        current_plan_version=1,
        current_command_seq=1,
        requested_replan_scope="NO_REPLAN_SAFETY_STOP",
    )
    response = adapter.replan(request)
    assert response.outcome == "REJECTED"


def test_rule_based_replanner_full_replan() -> None:
    adapter = RuleBasedReplannerAdapter()
    request = LocalReplanningRequest(
        request_id="req-004",
        trigger_event_id="evt-009",
        robot_id="robot-001",
        task_id="task-test-001",
        current_plan_version=1,
        current_command_seq=1,
        requested_replan_scope="FAILED_STEP_AND_REMAINING",
        completed_step_ids=["s1"],
        failed_step_id="s2",
    )
    response = adapter.replan(request)
    assert response.outcome == "REPLANNED"
    assert response.new_plan_version == 2


# ── LocalReplanningService ────────────────────────────────────────────


def test_replanning_service_process() -> None:
    from cloud_edge_robot_arm.contracts.models import LocalReplanningResponse

    # Create mock adapter that preserves completed step "s1"
    canned = LocalReplanningResponse(
        request_id="req-005",
        outcome="REPLANNED",
        reason="Test",
        new_steps=[
            TaskStep(
                step_id="s1",
                skill=SkillName.APPROACH,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s2-new",
                skill=SkillName.GRASP,
                parameters={},
                expected_duration_ms=3000,
                timeout_ms=8000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s3-new",
                skill=SkillName.LIFT,
                parameters={},
                expected_duration_ms=1500,
                timeout_ms=4000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s4-new",
                skill=SkillName.PLACE,
                parameters={},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
        ],
        new_plan_version=2,
        new_command_seq=2,
    )
    adapter = MockReplannerAdapter(canned_response=canned)
    service = LocalReplanningService(adapter=adapter)
    request = LocalReplanningRequest(
        request_id="req-005",
        trigger_event_id="evt-010",
        robot_id="robot-001",
        task_id="task-test-001",
        current_plan_version=1,
        current_command_seq=1,
        completed_step_ids=["s1"],
        failed_step_id="s2",
    )
    contract = _make_contract()
    response = service.process(request, contract)
    assert response.outcome == "REPLANNED"


def test_replanning_service_get_result() -> None:
    adapter = MockReplannerAdapter()
    service = LocalReplanningService(adapter=adapter)
    request = LocalReplanningRequest(
        request_id="req-006",
        trigger_event_id="evt-011",
        robot_id="robot-001",
        task_id="task-test-001",
        current_plan_version=1,
        current_command_seq=1,
    )
    service.process(request)
    result = service.get_result("req-006")
    assert result is not None
    assert result.outcome == "REJECTED"
    assert "checkpoint not found" in result.validation_errors
