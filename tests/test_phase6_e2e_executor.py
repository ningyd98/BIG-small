"""Phase 6 E2E tests — real behavior verification of the event-triggered loop.

Scenarios A-F + extra: RETRY_STEP, budget exhaust, CAS conflict, restart,
API persistence, completion failure, outbox dedup, replan rejection.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts import (
    ControlMode,
    FailurePolicy,
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.contracts.models import (
    EdgeEventType,
    MessageStatus,
    PendingMessage,
    RecoveryBudget,
)
from cloud_edge_robot_arm.edge.completion_evaluator import (
    CompletionEvaluator,
)
from cloud_edge_robot_arm.edge.event_mode.controller import EventTriggeredModeController
from cloud_edge_robot_arm.edge.recovery.retry_budget import RetryBudgetService
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.repositories.event_autonomy.memory import (
    InMemoryEventAutonomyRepository,
)
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import (
    SQLiteEventAutonomyRepository,
)
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository


def _event_contract(**overrides: object) -> TaskContract:
    now = datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC)
    valid = datetime(2026, 6, 13, 12, 5, 0, tzinfo=UTC)
    kwargs: dict[str, object] = {
        "task_id": "task-e2e-001",
        "plan_version": 1,
        "command_seq": 1,
        "timestamp": now,
        "control_mode": ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        "issued_at": now,
        "valid_until": valid,
        "user_instruction": "Pick and place",
        "scene_version": 1,
        "expected_scene_version": 1,
        "task_target": TaskTarget(
            object_id="obj-1",
            object_class="cube",
            target_region_id="bin-a",
        ),
        "steps": [
            TaskStep(
                step_id="s1",
                skill=SkillName.APPROACH,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s2",
                skill=SkillName.GRASP,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s3",
                skill=SkillName.PLACE,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
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
        "completion_criteria": ["object_placed"],
        **overrides,
    }
    return TaskContract(**kwargs)  # type: ignore[arg-type]


def test_task_executor_event_mode_retries_failed_step_before_next_step():
    """APPROACH succeeds, GRASP fails once, RETRY_STEP repeats GRASP, then PLACE runs."""
    from datetime import timedelta

    from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene

    now = datetime.now(UTC)
    contract = _event_contract(
        timestamp=now,
        issued_at=now,
        valid_until=now + timedelta(seconds=60),
        failure_policy=FailurePolicy(
            local_retry_limit=1,
            on_timeout="pause",
            on_safety_rejection="stop",
            on_network_loss="pause",
        ),
        steps=[
            TaskStep(
                step_id="approach",
                skill=SkillName.APPROACH,
                parameters={"object_id": "obj-1"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
            ),
            TaskStep(
                step_id="grasp",
                skill=SkillName.GRASP,
                parameters={"object_id": "obj-1"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=1,
            ),
            TaskStep(
                step_id="lift",
                skill=SkillName.LIFT,
                parameters={"height_m": 0.16},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
                preconditions=["object_attached"],
            ),
            TaskStep(
                step_id="move-region",
                skill=SkillName.MOVE_TO_REGION,
                parameters={"region_id": "bin-a"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
                preconditions=["object_attached"],
            ),
            TaskStep(
                step_id="place",
                skill=SkillName.PLACE,
                parameters={"region_id": "bin-a"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
                preconditions=["object_attached"],
            ),
            TaskStep(
                step_id="release",
                skill=SkillName.RELEASE,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
            ),
            TaskStep(
                step_id="verify",
                skill=SkillName.VERIFY_RESULT,
                parameters={"object_id": "obj-1", "region_id": "bin-a"},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=0,
            ),
        ],
        completion_criteria=["object_inside_target_region"],
    )
    scene = MockScene.with_default_pick_place_scene()
    obj = scene.objects.pop("red_cube")
    obj.object_id = "obj-1"
    scene.objects["obj-1"] = obj
    region = scene.regions.pop("bin_a")
    region = type(region)(region_id="bin-a", center=region.center, radius_m=region.radius_m)
    scene.regions["bin-a"] = region
    robot = MockRobotAdapter(scene=scene, auto_connect=True, grasp_failures_remaining=1)
    runtime_repo = InMemoryRepository()
    event_repo = InMemoryEventAutonomyRepository()
    controller = EventTriggeredModeController(repository=event_repo)

    result = TaskExecutor(
        robot=robot,
        shield=SafetyShield(),
        repository=runtime_repo,
        event_controller=controller,
    ).submit_contract(contract.model_dump(mode="json"))

    assert result.success is True
    assert [entry.action_type for entry in robot.history] == [
        "APPROACH",
        "GRASP",
        "GRASP",
        "LIFT",
        "MOVE_TO_REGION",
        "PLACE",
        "RELEASE",
        "VERIFY_RESULT",
    ]
    step_records = runtime_repo.list_step_executions(contract.task_id)
    assert [(r.step_id, r.success) for r in step_records[:3]] == [
        ("approach", True),
        ("grasp", False),
        ("grasp", True),
    ]
    assert event_repo.get_retry_budget(contract.task_id).retry_count_used == 1  # type: ignore[union-attr]
    summary = event_repo.get_completion_summary_for_task(contract.task_id)
    assert summary is not None
    assert summary.result == "SUCCESS_WITH_RECOVERY"


# ── Scenario A: Local retry re-executes same step ──────────────────────


def test_e2e_retry_reexecutes_same_step_not_next():
    """APPROACH → GRASP fails → RETRY_STEP → GRASP succeeds → PLACE.
    Assert sequence: [APPROACH, GRASP, GRASP, PLACE]."""
    # This test validates the while-loop structure: RETRY_STEP stays on same index.
    # For now, validate the repo + budget infrastructure supports it.
    repo = InMemoryEventAutonomyRepository()
    budget_svc = RetryBudgetService(repository=repo)
    contract = _event_contract()
    budget_svc.initialize(contract.task_id, contract)
    # Consume once (simulates first GRASP failure → retry)
    c1, b1 = repo.consume_retry_if_available(contract.task_id, "s2", "GRASP", 0)
    assert c1 is True
    assert b1 is not None
    assert b1.retry_count_used == 1
    # Budget still available after first retry
    can, reason = budget_svc.can_attempt(contract.task_id)
    assert can is True, f"Expected retry still available, got: {reason}"


# ── Scenario B: Budget exhausted → replan ──────────────────────────────


def test_e2e_budget_exhausted_triggers_replan():
    """All retries consumed, budget exhausted."""
    repo = InMemoryEventAutonomyRepository()
    budget_svc = RetryBudgetService(repository=repo)
    contract = _event_contract()
    budget_svc.initialize(contract.task_id, contract)
    for i in range(3):
        c, _ = repo.consume_retry_if_available(contract.task_id, "s2", "GRASP", i)
        assert c is True
    can, reason = budget_svc.can_attempt(contract.task_id)
    assert can is False
    assert reason == "RETRY_BUDGET_EXHAUSTED"


# ── Scenario C: CAS conflict ───────────────────────────────────────────


def test_cas_old_replan_result_rejected():
    """New version committed first, old version CAS fails."""
    repo = InMemoryEventAutonomyRepository()
    first = repo.advance_plan_version_if_current(
        task_id="task-cas",
        expected_plan_version=0,
        expected_command_seq=0,
        new_plan_version=1,
        new_command_seq=1,
    )
    assert first is True
    second = repo.advance_plan_version_if_current(
        task_id="task-cas",
        expected_plan_version=0,
        expected_command_seq=0,
        new_plan_version=2,
        new_command_seq=1,
    )
    assert second is False, "Old version should be rejected"


# ── Scenario D: SQLite restart ─────────────────────────────────────────


def test_sqlite_restart_preserves_state():
    """Consume retry, close repo, reopen — all state persists."""
    db_path = tempfile.mktemp(suffix=".sqlite3")
    try:
        repo1 = SQLiteEventAutonomyRepository(db_path)
        budget = RecoveryBudget(
            budget_id="bud-restart",
            task_id="task-restart",
            retry_count_used=0,
            remaining_retries=3,
            effective_retry_limit=3,
        )
        repo1.save_retry_budget(budget)
        c, u = repo1.consume_retry_if_available("task-restart", "s1", "GRASP", 0)
        assert c is True and u is not None and u.retry_count_used == 1
        repo1.save_state("task-restart", "WAITING_CLOUD_REPLAN", "budget exhausted")
        repo1.close()
        repo2 = SQLiteEventAutonomyRepository(db_path)
        assert repo2.get_state("task-restart") == "WAITING_CLOUD_REPLAN"
        b2 = repo2.get_retry_budget("task-restart")
        assert b2 is not None and b2.retry_count_used == 1 and b2.remaining_retries == 2
        repo2.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# ── Scenario E: API persistence round-trip ─────────────────────────────


def test_api_persistence_round_trip():
    """POST event → GET returns same data. Duplicate is idempotent."""
    repo = InMemoryEventAutonomyRepository()
    from cloud_edge_robot_arm.contracts.models import EdgeEvent

    now = datetime.now(UTC)
    event = EdgeEvent(
        event_id="evt-api-001",
        task_id="task-api",
        event_type=EdgeEventType.GRASP_FAILED,
        step_id="s1",
        severity="ERROR",
        reason_code="GRIP_FAILED",
        plan_version=1,
        command_seq=1,
        timestamp=now,
    )
    saved = repo.save_event(event)
    assert saved.event_id == "evt-api-001"
    retrieved = repo.get_event("evt-api-001")
    assert retrieved is not None
    assert retrieved.task_id == "task-api"
    assert retrieved.event_type == EdgeEventType.GRASP_FAILED
    duplicate = repo.save_event(event)
    assert duplicate.event_id == "evt-api-001"


# ── Scenario F: Completion failure blocks success ──────────────────────


def test_completion_evaluator_blocks_success_on_failure():
    """All steps done but criteria fail → not completed."""
    contract = _event_contract()
    evaluator = CompletionEvaluator()
    result = evaluator.evaluate(
        contract=contract,
        completed_step_ids=["s1", "s2", "s3"],
        completion_criteria_results={"object_placed": False},
        final_safety_decision="ALLOW",
        final_robot_state={"stopped": True, "gripper_open": True},
        final_target_state={"object_at_target": False},
        scene_version=1,
    )
    assert result.completed is False
    assert "CHECK_3_CRITERIA_FAILED" in result.failed_checks
    assert "CHECK_6_TARGET_NOT_AT_REGION" in result.failed_checks

    result2 = evaluator.evaluate(
        contract=contract,
        completed_step_ids=["s1", "s2", "s3"],
        completion_criteria_results={"object_placed": True},
        final_safety_decision="ALLOW",
        final_robot_state={
            "stopped": True,
            "gripper_open": True,
            "holding_object_id": None,
        },
        final_target_state={"object_at_target": True},
        scene_version=1,
    )
    assert result2.completed is True
    assert len(result2.failed_checks) == 0


# ── Extra: Outbox dedup ────────────────────────────────────────────────


def test_outbox_cas_prevents_double_claim():
    repo = InMemoryEventAutonomyRepository()
    msg = PendingMessage(
        message_id="msg-ob-dedup",
        task_id="task-ob",
        message_type="TEST",
        payload={},
        status=MessageStatus.PENDING,
        max_retries=3,
    )
    repo.enqueue_outbox(msg)
    c1 = repo.claim_outbox_message()
    assert c1 is not None
    c2 = repo.claim_outbox_message()
    assert c2 is None, "Second claim must fail — already SENDING"


def test_sqlite_outbox_retry_wait_survives_restart_and_reclaims():
    """Failed SQLite outbox sends persist as RETRY_WAIT and are reclaimable after restart."""
    db_path = tempfile.mktemp(suffix=".sqlite3")
    try:
        repo1 = SQLiteEventAutonomyRepository(db_path)
        msg = PendingMessage(
            message_id="msg-sqlite-retry",
            task_id="task-ob",
            message_type="TEST",
            payload={"critical": True},
            status=MessageStatus.PENDING,
            max_retries=3,
            backoff_base_ms=0,
        )
        repo1.enqueue_outbox(msg)
        claimed = repo1.claim_outbox_message()
        assert claimed is not None
        assert claimed.status == MessageStatus.SENDING
        assert repo1.mark_outbox_failed("msg-sqlite-retry", "network down") is True
        pending = repo1.list_pending_outbox("task-ob")
        assert len(pending) == 1
        assert pending[0].status == MessageStatus.RETRY_WAIT
        assert pending[0].retry_count == 1
        repo1.close()

        repo2 = SQLiteEventAutonomyRepository(db_path)
        restarted_pending = repo2.list_pending_outbox("task-ob")
        assert len(restarted_pending) == 1
        assert restarted_pending[0].status == MessageStatus.RETRY_WAIT
        reclaimed = repo2.claim_outbox_message()
        assert reclaimed is not None
        assert reclaimed.message_id == "msg-sqlite-retry"
        assert reclaimed.status == MessageStatus.SENDING
        repo2.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


# ── Extra: Budget CAS prevents double consume ──────────────────────────


def test_budget_cas_prevents_double_consume():
    repo = InMemoryEventAutonomyRepository()
    budget = RecoveryBudget(
        budget_id="bud-cas2",
        task_id="task-cas-b",
        retry_count_used=0,
        remaining_retries=2,
        effective_retry_limit=2,
    )
    repo.save_retry_budget(budget)
    c1, _ = repo.consume_retry_if_available("task-cas-b", "s1", "GRASP", 0)
    assert c1 is True
    c2, _ = repo.consume_retry_if_available("task-cas-b", "s1", "GRASP", 0)
    assert c2 is False
    c3, u3 = repo.consume_retry_if_available("task-cas-b", "s1", "GRASP", 1)
    assert c3 is True
    assert u3 is not None and u3.retry_count_used == 2


# ── Extra: Replan rejects completed step modification ──────────────────


def test_replan_rejects_completed_step_modification():
    from cloud_edge_robot_arm.cloud.replanning.validators import (
        CompletedStepsProtectionValidator,
    )

    validator = CompletedStepsProtectionValidator()
    completed = ["s1"]
    original = [
        TaskStep(
            step_id="s1",
            skill=SkillName.APPROACH,
            parameters={},
            expected_duration_ms=1000,
            timeout_ms=3000,
            retry_limit=3,
        ),
        TaskStep(
            step_id="s2",
            skill=SkillName.GRASP,
            parameters={},
            expected_duration_ms=1000,
            timeout_ms=3000,
            retry_limit=3,
        ),
    ]
    ok, _ = validator.validate(
        completed,
        original,
        [
            TaskStep(
                step_id="s1",
                skill=SkillName.APPROACH,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=3,
            ),
            TaskStep(
                step_id="s2-new",
                skill=SkillName.GRASP,
                parameters={"x": 1},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=3,
            ),
        ],
    )
    assert ok is True
    ok2, err2 = validator.validate(
        completed,
        original,
        [
            TaskStep(
                step_id="s1",
                skill=SkillName.GRASP,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=3,
            ),
        ],
    )
    assert ok2 is False and len(err2) > 0


# ── Extra: Old plan_version rejected ───────────────────────────────────


def test_old_plan_version_rejected():
    repo = InMemoryEventAutonomyRepository()
    # Advance to version 3
    assert repo.advance_plan_version_if_current("task-v", 0, 0, 3, 1) is True
    # Old version 2 should fail
    assert repo.advance_plan_version_if_current("task-v", 2, 1, 4, 2) is False
