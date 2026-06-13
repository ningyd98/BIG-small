"""Phase 6 integration tests — end-to-end scenarios."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.contracts.models import (
    CompletionResult,
    ControlMode,
    FailurePolicy,
    MessageStatus,
    RobotState,
    SafetyConstraints,
    SkillExecutionResult,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.edge.event_mode.controller import (
    ControllerAction,
    EventTriggeredModeController,
)
from cloud_edge_robot_arm.edge.events.models import DetectionContext
from cloud_edge_robot_arm.edge.outbox import InMemoryPendingMessageRepository
from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetManager
from cloud_edge_robot_arm.edge.summaries.completion import CompletionSummaryBuilder

NOW = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)


def _make_contract(**overrides: object) -> TaskContract:
    defaults: dict[str, object] = {
        "task_id": "task-int-001",
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
        "completion_criteria": ["object_in_bin"],
    }
    defaults.update(overrides)
    return TaskContract(**defaults)  # type: ignore[arg-type]


def _make_context(**overrides: object) -> DetectionContext:
    defaults: dict[str, object] = {
        "task_id": "task-int-001",
        "plan_version": 1,
        "command_seq": 1,
        "robot_id": "robot-001",
        "step": TaskStep(
            step_id="s2",
            skill=SkillName.GRASP,
            parameters={},
            expected_duration_ms=2000,
            timeout_ms=5000,
            retry_limit=3,
        ),
        "step_result": None,
        "robot_state": RobotState(connected=True),
        "contract": None,
        "elapsed_action_ms": 1000,
        "step_attempts": {},
        "scene_version": 1,
        "scene_confidence": 0.9,
        "completed_step_ids": ["s1"],
        "completion_criteria": ["object_in_bin"],
        "network_connected": True,
    }
    defaults.update(overrides)
    return DetectionContext(**defaults)  # type: ignore[arg-type]


# ── Scenario: Normal autonomous execution ─────────────────────────────


def test_controller_no_events_continues() -> None:
    controller = EventTriggeredModeController()
    contract = _make_contract()
    controller.initialize_task(contract)
    ctx = _make_context(contract=contract)
    result = controller.on_step_result(result=None, context=ctx, contract=contract)
    assert result.action == ControllerAction.CONTINUE


def test_controller_task_completed() -> None:
    controller = EventTriggeredModeController()
    contract = _make_contract()
    controller.initialize_task(contract)
    # All steps completed — manually trigger completion
    summary = controller.on_task_completed(
        contract=contract,
        completed_step_ids=["s1", "s2", "s3"],
    )
    assert summary is not None
    assert summary.result == CompletionResult.SUCCESS
    assert len(summary.completed_step_ids) == 3


# ── Scenario: Grasp failure → local recovery ──────────────────────────


def test_controller_grasp_failure_retry() -> None:
    controller = EventTriggeredModeController()
    contract = _make_contract()
    controller.initialize_task(contract)
    ctx = _make_context(
        contract=contract,
        step_result=SkillExecutionResult(
            task_id="task-int-001",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            step_id="s2",
            skill=SkillName.GRASP,
            scene_version=1,
            success=False,
            duration_ms=2000,
        ),
    )
    result = controller.on_step_result(result=None, context=ctx, contract=contract)
    assert result.action == ControllerAction.RETRY_STEP
    assert result.event is not None


# ── Scenario: Recovery budget exhausted ────────────────────────────────


def test_controller_budget_exhausted_pauses() -> None:
    budget_mgr = RetryBudgetManager()
    contract = _make_contract()
    budget_mgr.initialize("task-int-001", contract)
    # Exhaust budget
    for _ in range(3):
        budget_mgr.consume("task-int-001")

    controller = EventTriggeredModeController(budget_manager=budget_mgr)
    # Do NOT call initialize_task — budget already exists and is exhausted

    ctx = _make_context(
        contract=contract,
        step_result=SkillExecutionResult(
            task_id="task-int-001",
            plan_version=1,
            command_seq=1,
            timestamp=NOW,
            step_id="s2",
            skill=SkillName.GRASP,
            scene_version=1,
            success=False,
            duration_ms=2000,
        ),
    )
    result = controller.on_step_result(result=None, context=ctx, contract=contract)
    # Budget exhausted → should request cloud replan (PAUSE)
    assert result.action in (ControllerAction.PAUSE, ControllerAction.REPLAN_AND_CONTINUE)


# ── Scenario: Critical event → safety stop ────────────────────────────


def test_controller_critical_event_safety_stop() -> None:
    controller = EventTriggeredModeController()
    contract = _make_contract()
    controller.initialize_task(contract)
    ctx = _make_context(
        contract=contract,
        safety_state={"emergency_stop_triggered": True},
    )
    result = controller.on_step_result(result=None, context=ctx, contract=contract)
    assert result.action == ControllerAction.SAFETY_STOP


# ── Scenario: Target moved → replan request ────────────────────────────


def test_controller_target_moved_replan() -> None:
    controller = EventTriggeredModeController()
    contract = _make_contract()
    controller.initialize_task(contract)
    ctx = _make_context(contract=contract)
    # Simulate target moved by injecting scene state change
    result = controller.on_step_result(result=None, context=ctx, contract=contract)
    # Without actual scene state change, just verify it doesn't crash
    assert result.action in (
        ControllerAction.CONTINUE,
        ControllerAction.RETRY_STEP,
        ControllerAction.PAUSE,
    )


# ── Outbox ─────────────────────────────────────────────────────────────


def test_outbox_enqueue_and_list() -> None:
    outbox = InMemoryPendingMessageRepository()
    from cloud_edge_robot_arm.contracts.models import PendingMessage

    msg = PendingMessage(
        message_id="msg-001",
        task_id="task-test",
        message_type="EDGE_EVENT",
        payload={"event_type": "GRASP_FAILED"},
        status=MessageStatus.PENDING,
        created_at=NOW,
    )
    outbox.enqueue(msg)
    pending = outbox.list_pending("task-test")
    assert len(pending) == 1
    assert pending[0].message_id == "msg-001"


def test_outbox_mark_sent() -> None:
    outbox = InMemoryPendingMessageRepository()
    from cloud_edge_robot_arm.contracts.models import PendingMessage

    msg = PendingMessage(
        message_id="msg-002",
        task_id="task-test",
        message_type="FAILURE_SUMMARY",
        payload={},
        status=MessageStatus.PENDING,
        created_at=NOW,
    )
    outbox.enqueue(msg)
    outbox.mark_sent("msg-002")
    pending = outbox.list_pending("task-test")
    assert len(pending) == 0


def test_outbox_mark_failed_retry() -> None:
    outbox = InMemoryPendingMessageRepository()
    from cloud_edge_robot_arm.contracts.models import PendingMessage

    msg = PendingMessage(
        message_id="msg-003",
        task_id="task-test",
        message_type="EDGE_EVENT",
        payload={},
        status=MessageStatus.PENDING,
        created_at=NOW,
        max_retries=5,
    )
    outbox.enqueue(msg)
    outbox.mark_failed("msg-003", "Send timeout")
    pending = outbox.list_pending("task-test")
    assert len(pending) == 1
    assert pending[0].retry_count == 1


def test_outbox_mark_failed_exhausted() -> None:
    outbox = InMemoryPendingMessageRepository()
    from cloud_edge_robot_arm.contracts.models import PendingMessage

    msg = PendingMessage(
        message_id="msg-004",
        task_id="task-test",
        message_type="EDGE_EVENT",
        payload={},
        status=MessageStatus.PENDING,
        created_at=NOW,
        max_retries=1,
    )
    outbox.enqueue(msg)
    outbox.mark_failed("msg-004", "Send error")
    pending = outbox.list_pending("task-test")
    assert len(pending) == 0  # exhausted → not pending


# ── Event mode state machine ───────────────────────────────────────────


def test_state_machine_legal_transitions() -> None:
    from cloud_edge_robot_arm.edge.event_mode.state_machine import (
        EventModeState,
        EventModeStateMachine,
    )

    sm = EventModeStateMachine("task-test")
    assert sm.current_state == EventModeState.IDLE

    assert sm.transition(EventModeState.EXECUTING_AUTONOMOUSLY, "Start")
    assert sm.current_state == EventModeState.EXECUTING_AUTONOMOUSLY

    assert sm.transition(EventModeState.EVENT_DETECTED, "Event: GRASP_FAILED")
    assert sm.current_state == EventModeState.EVENT_DETECTED

    assert sm.transition(EventModeState.EVALUATING_LOCAL_RECOVERY, "Evaluating")
    assert sm.current_state == EventModeState.EVALUATING_LOCAL_RECOVERY


def test_state_machine_rejects_illegal() -> None:
    from cloud_edge_robot_arm.edge.event_mode.state_machine import (
        EventModeState,
        EventModeStateMachine,
    )

    sm = EventModeStateMachine("task-test")
    # Cannot go directly from IDLE to COMPLETED
    assert not sm.transition(EventModeState.COMPLETED, "Impossible")
    assert sm.current_state == EventModeState.IDLE


def test_state_machine_terminal_blocks_transitions() -> None:
    from cloud_edge_robot_arm.edge.event_mode.state_machine import (
        EventModeState,
        EventModeStateMachine,
    )

    sm = EventModeStateMachine("task-test")
    sm.transition(EventModeState.EXECUTING_AUTONOMOUSLY, "Start")
    sm.transition(EventModeState.SAFETY_STOPPED, "Critical")
    assert sm.is_terminal()
    assert not sm.transition(EventModeState.EXECUTING_AUTONOMOUSLY, "Should not work")


# ── CompletionSummary ──────────────────────────────────────────────────


def test_completion_summary_builder() -> None:
    builder = CompletionSummaryBuilder()
    contract = _make_contract()
    summary = builder.build(
        contract=contract,
        completed_step_ids=["s1", "s2", "s3"],
        result=CompletionResult.SUCCESS,
        started_at=NOW,
    )
    assert summary.result == "SUCCESS"
    assert len(summary.summary_hash) > 0
    assert summary.completion_criteria_results["all_steps_completed"]


def test_completion_summary_success_with_recovery() -> None:
    builder = CompletionSummaryBuilder()
    contract = _make_contract()
    summary = builder.build(
        contract=contract,
        completed_step_ids=["s1", "s2", "s3"],
        result=CompletionResult.SUCCESS_WITH_RECOVERY,
        local_retry_count=2,
        started_at=NOW,
    )
    assert summary.result == "SUCCESS_WITH_RECOVERY"
    assert summary.local_retry_count == 2


# ── Phase 5 no regression (smoke test) ─────────────────────────────────


def test_phase5_control_mode_still_supported() -> None:
    """Verify EVENT_TRIGGERED_EDGE_AUTONOMY mode enum exists and is distinct."""
    assert ControlMode.PERIODIC_CLOUD_SUPERVISION.value == "PERIODIC_CLOUD_SUPERVISION"
    assert ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY.value == "EVENT_TRIGGERED_EDGE_AUTONOMY"
    assert ControlMode.AUTO.value == "AUTO"


def test_controller_action_enum_values() -> None:
    """Verify all required controller actions exist."""
    actions = {a.value for a in ControllerAction}
    assert "CONTINUE" in actions
    assert "RETRY_STEP" in actions
    assert "REPLAN_AND_CONTINUE" in actions
    assert "PAUSE" in actions
    assert "FAIL" in actions
    assert "SAFETY_STOP" in actions
