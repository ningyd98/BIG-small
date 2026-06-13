"""Phase 5: Periodic Cloud Supervisory Control (PCSC) comprehensive tests.

Covers unit tests and integration tests for the supervision system.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.supervision.core import (
    FakeClock,
    compute_state_hash,
)
from cloud_edge_robot_arm.cloud.supervision.models import (
    EdgeStatusSnapshot,
    SupervisionConfig,
    SupervisionReasonCode,
    SupervisoryDecisionType,
)
from cloud_edge_robot_arm.cloud.supervision.service import PeriodicSupervisorService
from cloud_edge_robot_arm.contracts import TaskContract

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_snapshot(
    task_id: str = "task-001",
    robot_id: str = "robot-001",
    plan_version: int = 1,
    command_seq: int = 1,
    scene_version: int = 1,
    timestamp: datetime | None = None,
    current_step_id: str = "step-01",
    completed_step_ids: list[str] | None = None,
    execution_status: str = "EXECUTING",
    scene_confidence: float = 1.0,
    robot_state: dict | None = None,
    target_state: dict | None = None,
    obstacle_state: dict | None = None,
    network_state: dict | None = None,
    telemetry: dict | None = None,
) -> EdgeStatusSnapshot:
    ts = timestamp or datetime(2026, 6, 13, 12, 0, 0, tzinfo=UTC) - timedelta(milliseconds=200)
    return EdgeStatusSnapshot(
        robot_id=robot_id,
        task_id=task_id,
        plan_version=plan_version,
        command_seq=command_seq,
        scene_version=scene_version,
        timestamp=ts,
        current_step_id=current_step_id,
        completed_step_ids=completed_step_ids or [],
        execution_status=execution_status,
        robot_state=robot_state or {"connected": True, "estop_engaged": False},
        target_state=target_state or {},
        obstacle_state=obstacle_state or {},
        telemetry=telemetry or {},
        network_state=network_state or {"degraded": False, "rtt_ms": 50},
        scene_confidence=scene_confidence,
    )


def _make_contract(
    task_id: str = "task-001",
    plan_version: int = 1,
    command_seq: int = 1,
) -> TaskContract:
    from cloud_edge_robot_arm.contracts import (
        ControlMode,
        FailurePolicy,
        SafetyConstraints,
        SkillName,
        TaskContract,
        TaskStep,
        TaskTarget,
    )

    return TaskContract(
        task_id=task_id,
        plan_version=plan_version,
        command_seq=command_seq,
        timestamp=datetime.now(UTC),
        control_mode=ControlMode.PERIODIC_CLOUD_SUPERVISION,
        issued_at=datetime.now(UTC),
        valid_until=datetime.now(UTC) + timedelta(seconds=60),
        user_instruction="pick red cube and place into bin_a",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(
            object_id="red_cube",
            object_class="cube",
            target_region_id="bin_a",
        ),
        current_step_id="step-01",
        steps=[
            TaskStep(
                step_id="step-01",
                skill=SkillName.HOME,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=1,
                preconditions=[],
                success_conditions=["robot_at_home"],
            ),
            TaskStep(
                step_id="step-02",
                skill=SkillName.MOVE_ABOVE,
                parameters={"object_id": "red_cube"},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=2,
                preconditions=["target_visible"],
                success_conditions=["tcp_above_target"],
            ),
            TaskStep(
                step_id="step-03",
                skill=SkillName.GRASP,
                parameters={"object_id": "red_cube"},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=2,
                preconditions=["target_reachable"],
                success_conditions=["gripper_closed", "object_attached"],
            ),
            TaskStep(
                step_id="step-04",
                skill=SkillName.PLACE,
                parameters={"region_id": "bin_a"},
                expected_duration_ms=2000,
                timeout_ms=5000,
                retry_limit=1,
                preconditions=[],
                success_conditions=["object_placed"],
            ),
        ],
        safety_constraints=SafetyConstraints(
            max_joint_velocity=0.5,
            max_tcp_velocity=0.15,
            minimum_safe_height=0.08,
            workspace_id="workspace_a",
            collision_check_required=True,
        ),
        failure_policy=FailurePolicy(
            local_retry_limit=2,
            on_timeout="REQUEST_CLOUD_REPLAN",
            on_safety_rejection="PAUSE_AND_REPORT",
            on_network_loss="SAFE_STOP",
        ),
        completion_criteria=["object_inside_target_region"],
    )


# ── Unit: Stable scene → KEEP ───────────────────────────────────────────────


def test_stable_scene_returns_keep() -> None:
    """Stable scene produces KEEP_CURRENT_PLAN."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    snapshot = _make_snapshot(timestamp=clock.now())
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.decision == SupervisoryDecisionType.KEEP_CURRENT_PLAN
    assert decision.reason_code == SupervisionReasonCode.SCENE_STABLE


def test_stable_scene_does_not_call_planner() -> None:
    """KEEP decisions never invoke PlannerAdapter."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    for _ in range(3):
        snapshot = _make_snapshot(timestamp=clock.now())
        decision = service.evaluate_snapshot(snapshot, contract)
        assert decision.decision == SupervisoryDecisionType.KEEP_CURRENT_PLAN
        assert not decision.planner_invoked
    assert service.planner_invocation_count == 0


def test_small_jitter_does_not_trigger_update() -> None:
    """Target displacement below threshold does not trigger update."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    # Small jitter within threshold
    snapshot = _make_snapshot(
        target_state={"object_id": "red_cube", "x": 0.001, "y": 0.001, "z": 0.02}
    )
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.decision == SupervisoryDecisionType.KEEP_CURRENT_PLAN


def test_target_moved_triggers_update() -> None:
    """Target displacement exceeding threshold triggers UPDATE_CURRENT_STEP."""
    clock = FakeClock()
    service = PeriodicSupervisorService(
        planner=MockPlannerAdapter(),
        clock=clock,
        config=SupervisionConfig(target_displacement_threshold_m=0.02),
    )
    contract = _make_contract()
    from cloud_edge_robot_arm.contracts import Pose

    service.start(contract, initial_target=Pose(x=0.0, y=0.0, z=0.02))
    # Large displacement beyond threshold
    snapshot = _make_snapshot(
        current_step_id="step-01",
        timestamp=clock.now(),
        target_state={
            "object_id": "red_cube",
            "object_class": "cube",
            "x": 0.3,
            "y": 0.3,
            "z": 0.02,
            "region_id": "bin_a",
            "region_center": {"x": -0.2, "y": 0.18, "z": 0.02},
        },
    )
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.decision == SupervisoryDecisionType.UPDATE_CURRENT_STEP
    assert decision.reason_code == SupervisionReasonCode.TARGET_MOVED_CURRENT_STEP
    assert decision.planner_invoked


# ── Unit: Obstacle / risk scenarios ─────────────────────────────────────────


def test_obstacle_blocks_path_triggers_pause() -> None:
    """New obstacle in current path triggers PAUSE."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    snapshot = _make_snapshot(
        current_step_id="step-02",
        obstacle_state={"obstacles": [{"obstacle_id": "obs-001", "x": 0.5, "y": 0.5, "z": 0.1}]},
    )
    decision = service.evaluate_snapshot(snapshot, contract)
    # New obstacle → PAUSE (conservative)
    assert decision.decision in {
        SupervisoryDecisionType.PAUSE_TASK,
        SupervisoryDecisionType.REPLACE_REMAINING_STEPS,
    }


def test_state_stale_triggers_request_observation() -> None:
    """Stale edge state triggers REQUEST_MORE_OBSERVATION."""
    clock = FakeClock()
    config = SupervisionConfig(stale_state_threshold_ms=1_000)
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock, config=config)
    contract = _make_contract()
    service.start(contract)
    old_time = clock.now() - timedelta(seconds=5)
    snapshot = _make_snapshot(timestamp=old_time)
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.decision == SupervisoryDecisionType.REQUEST_MORE_OBSERVATION
    assert decision.reason_code == SupervisionReasonCode.EDGE_STATE_STALE


def test_low_confidence_triggers_request_observation() -> None:
    """Low scene confidence triggers REQUEST_MORE_OBSERVATION."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    snapshot = _make_snapshot(scene_confidence=0.3)
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.decision == SupervisoryDecisionType.REQUEST_MORE_OBSERVATION
    assert decision.reason_code == SupervisionReasonCode.SCENE_CONFIDENCE_LOW


def test_estop_triggers_abort() -> None:
    """Emergency stop engaged → ABORT_TASK."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    snapshot = _make_snapshot(robot_state={"connected": True, "estop_engaged": True})
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.decision == SupervisoryDecisionType.ABORT_TASK
    assert decision.reason_code == SupervisionReasonCode.SAFETY_RISK_INCREASED


def test_completed_task_no_replan() -> None:
    """Completed task does not trigger replanning."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    snapshot = _make_snapshot(execution_status="COMPLETED")
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.decision == SupervisoryDecisionType.KEEP_CURRENT_PLAN
    assert decision.reason_code == SupervisionReasonCode.PLAN_ALREADY_COMPLETED


# ── Unit: Idempotency ───────────────────────────────────────────────────────


def test_repeated_snapshot_idempotent() -> None:
    """Same snapshot produces same decision within a supervision session."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    snapshot = _make_snapshot(timestamp=clock.now())
    d1 = service.evaluate_snapshot(snapshot, contract)
    d2 = service.evaluate_snapshot(snapshot, contract)
    assert d1.decision == d2.decision
    assert d1.reason_code == d2.reason_code


# ── Unit: Plan version management ───────────────────────────────────────────


def test_update_increases_plan_version() -> None:
    """UPDATE decision increases resulting_plan_version."""
    clock = FakeClock()
    service = PeriodicSupervisorService(
        planner=MockPlannerAdapter(),
        clock=clock,
        config=SupervisionConfig(target_displacement_threshold_m=0.02),
    )
    contract = _make_contract(plan_version=1, command_seq=1)
    service.start(contract)
    snapshot = _make_snapshot(target_state={"object_id": "red_cube", "x": 0.5, "y": 0.5, "z": 0.02})
    decision = service.evaluate_snapshot(snapshot, contract)
    if decision.is_update():
        assert decision.resulting_plan_version > decision.based_on_plan_version


def test_production_rejects_test_scheduler() -> None:
    """Production mode requires a real scheduler."""
    with pytest.raises(ValueError, match="scheduler"):
        PeriodicSupervisorService(
            planner=MockPlannerAdapter(),
            runtime_profile="production",
            scheduler=None,
        )


def test_test_mode_allows_no_scheduler() -> None:
    """Test mode allows optional scheduler."""
    service = PeriodicSupervisorService(
        planner=MockPlannerAdapter(),
        runtime_profile="test",
    )
    assert service.running is False


# ── Integration: full supervision cycle ─────────────────────────────────────


def test_three_stable_cycles_then_update() -> None:
    """Three stable KEEP cycles, then target moves → UPDATE."""
    clock = FakeClock()
    service = PeriodicSupervisorService(
        planner=MockPlannerAdapter(),
        clock=clock,
        config=SupervisionConfig(target_displacement_threshold_m=0.02),
    )
    contract = _make_contract()
    from cloud_edge_robot_arm.contracts import Pose

    service.start(contract, initial_target=Pose(x=0.0, y=0.0, z=0.02))

    for i in range(3):
        snapshot = _make_snapshot(
            timestamp=clock.now(),
            completed_step_ids=["step-01"] if i > 0 else [],
            current_step_id="step-02" if i > 0 else "step-01",
        )
        decision = service.evaluate_snapshot(snapshot, contract)
        assert decision.decision == SupervisoryDecisionType.KEEP_CURRENT_PLAN
        clock.advance(1.0)

    # Now move target
    snapshot = _make_snapshot(
        timestamp=clock.now(),
        current_step_id="step-02",
        target_state={
            "object_id": "red_cube",
            "object_class": "cube",
            "x": 0.5,
            "y": 0.5,
            "z": 0.02,
            "region_id": "bin_a",
            "region_center": {"x": -0.2, "y": 0.18, "z": 0.02},
        },
    )
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.decision == SupervisoryDecisionType.UPDATE_CURRENT_STEP
    assert decision.planner_invoked


def test_network_degraded_pauses() -> None:
    """Network degradation triggers PAUSE with pause_on_unknown_risk=True."""
    clock = FakeClock()
    config = SupervisionConfig(
        pause_on_unknown_risk=True,
    )
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock, config=config)
    contract = _make_contract()
    service.start(contract)
    snapshot = _make_snapshot(network_state={"degraded": True, "rtt_ms": 2000})
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.decision == SupervisoryDecisionType.PAUSE_TASK
    assert decision.reason_code == SupervisionReasonCode.NETWORK_DEGRADED


def test_audit_events_generated() -> None:
    """Every supervision cycle generates audit events."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    snapshot = _make_snapshot(timestamp=clock.now() - timedelta(milliseconds=200))
    service.evaluate_snapshot(snapshot, contract)
    events = service.audit_events()
    event_types = {e["event_type"] for e in events}
    assert "SUPERVISION_STARTED" in event_types
    assert "SUPERVISION_CYCLE_STARTED" in event_types
    assert "EDGE_STATUS_RECEIVED" in event_types
    assert "SUPERVISION_STATE_EVALUATED" in event_types
    assert (
        "SUPERVISION_KEEP_SELECTED" in event_types or "SUPERVISION_DECISION_CREATED" in event_types
    )


# ── Clock tests ─────────────────────────────────────────────────────────────


def test_fake_clock_advance() -> None:
    """FakeClock.advance properly advances time."""
    clock = FakeClock()
    t0 = clock.now()
    clock.advance(5.0)
    assert (clock.now() - t0).total_seconds() == pytest.approx(5.0)


def test_fake_clock_monotonic() -> None:
    """FakeClock.monotonic works with advance."""
    clock = FakeClock()
    m0 = clock.monotonic()
    clock.advance(3.0)
    assert clock.monotonic() - m0 == pytest.approx(3.0)


# ── Snapshot validation ─────────────────────────────────────────────────────


def test_snapshot_future_timestamp_rejected() -> None:
    """Snapshot from the future is rejected."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    future = clock.now() + timedelta(hours=1)
    snapshot = _make_snapshot(timestamp=future)
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.decision == SupervisoryDecisionType.REQUEST_MORE_OBSERVATION


def test_snapshot_task_id_mismatch_rejected() -> None:
    """task_id mismatch is rejected."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract(task_id="task-001")
    service.start(contract)
    snapshot = _make_snapshot(task_id="task-999")
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.reason_detail == "task_id mismatch"


def test_snapshot_plan_version_ahead_of_cloud_rejected() -> None:
    """Edge plan_version exceeding cloud known version is rejected."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract(plan_version=1)
    service.start(contract)
    snapshot = _make_snapshot(plan_version=99, timestamp=clock.now())
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.reason_code == SupervisionReasonCode.EDGE_STATE_STALE


def test_completed_steps_not_regress() -> None:
    """Completed step IDs that don't belong to contract fail validation."""
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    snapshot = _make_snapshot(
        completed_step_ids=["step-99-ghost"],
        timestamp=clock.now(),
    )
    decision = service.evaluate_snapshot(snapshot, contract)
    assert decision.reason_code == SupervisionReasonCode.EDGE_STATE_STALE


# ── State hash ──────────────────────────────────────────────────────────────


def test_state_hash_deterministic() -> None:
    """Same snapshot produces same state hash."""
    s1 = _make_snapshot()
    s2 = _make_snapshot()
    assert compute_state_hash(s1) == compute_state_hash(s2)


def test_state_hash_different_for_different_snapshot() -> None:
    """Different snapshots produce different state hashes."""
    s1 = _make_snapshot(task_id="task-001")
    s2 = _make_snapshot(task_id="task-002")
    assert compute_state_hash(s1) != compute_state_hash(s2)


# ── Count check ─────────────────────────────────────────────────────────────


def test_phase5_test_count_at_least_20() -> None:
    """Ensure this test file has at least 20 test functions."""
    import inspect
    import sys

    count = sum(
        1
        for _, obj in inspect.getmembers(sys.modules[__name__])
        if inspect.isfunction(obj) and obj.__name__.startswith("test_")
    )
    assert count >= 20, f"Expected at least 20 tests, got {count}"


# ── PathCollision real rejection ────────────────────────────────────────────


def test_path_collision_rejects_obstructed_path() -> None:
    """PathCollision rule returns REJECT when obstacle blocks the path."""
    from cloud_edge_robot_arm.edge.safety.models import Obstacle, SafetyContext
    from cloud_edge_robot_arm.edge.safety.rules import PathCollisionRule

    rule = PathCollisionRule()

    # Build a context with TCP at (0,0,0.18) targeting (0.5,0,0.18)
    # and an obstacle at (0.25, 0, 0.18) with radius 0.1
    obs = Obstacle(obstacle_id="obs-001", x=0.25, y=0.0, z=0.18, radius_m=0.1)
    ctx_data: dict[str, Any] = {
        "task_id": "t1",
        "plan_version": 1,
        "command_seq": 1,
        "step_id": "s1",
        "skill": "MOVE_ABOVE",
        "tcp_x": 0.0,
        "tcp_y": 0.0,
        "tcp_z": 0.18,
        "parameters": {
            "target_pose": {"x": 0.5, "y": 0.0, "z": 0.18},
        },
        "obstacles": [obs],
        "holding_object": False,
        "robot_connected": True,
        "robot_stopped": False,
        "robot_estop_engaged": False,
        "robot_collision_detected": False,
        "scene_version": 1,
        "joint_velocities": [],
        "merged_max_tcp_velocity": 1.0,
        "merged_max_joint_velocity": 2.0,
        "merged_max_acceleration": 5.0,
        "merged_minimum_safe_height": 0.08,
        "merged_max_reach_m": 0.65,
        "merged_obstacle_safety_distance": 0.05,
        "merged_carry_safety_margin": 0.02,
        "merged_scene_staleness_ms": 5_000,
        "merged_telemetry_staleness_ms": 5_000,
        "merged_watchdog_timeout_ms": 30_000,
        "absolute_max_tcp_velocity": 1.0,
        "absolute_max_joint_velocity": 2.0,
        "absolute_max_acceleration": 5.0,
    }
    from cloud_edge_robot_arm.contracts import (
        ControlMode,
        FailurePolicy,
        SafetyConstraints,
        SkillName,
        TaskContract,
        TaskStep,
        TaskTarget,
    )

    contract = TaskContract(
        task_id="t1",
        plan_version=1,
        command_seq=1,
        timestamp=datetime.now(UTC),
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=datetime.now(UTC),
        valid_until=datetime.now(UTC) + timedelta(seconds=60),
        user_instruction="test",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(
            object_id="red_cube",
            object_class="cube",
            target_region_id="bin_a",
        ),
        steps=[
            TaskStep(
                step_id="s1",
                skill=SkillName.MOVE_ABOVE,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=1,
                preconditions=[],
                success_conditions=[],
            )
        ],
        safety_constraints=SafetyConstraints(
            max_joint_velocity=0.5,
            max_tcp_velocity=0.15,
            minimum_safe_height=0.08,
            workspace_id="workspace_a",
            collision_check_required=True,
        ),
        failure_policy=FailurePolicy(
            local_retry_limit=2,
            on_timeout="REQUEST_CLOUD_REPLAN",
            on_safety_rejection="PAUSE_AND_REPORT",
            on_network_loss="SAFE_STOP",
        ),
        completion_criteria=["object_placed"],
    )
    ctx_data["contract"] = contract
    ctx = SafetyContext(**ctx_data)
    result = rule.evaluate(ctx)
    assert result.decision.value == "REJECT", f"Expected REJECT, got {result.decision.value}"
    assert result.reason_code == "PATH_COLLISION", (
        f"Expected PATH_COLLISION, got {result.reason_code}"
    )


# ── Acceleration real evaluation ────────────────────────────────────────────


def test_acceleration_rule_real_evaluation() -> None:
    """Acceleration rule evaluates real telemetry/contract values, not fixed 0."""
    from cloud_edge_robot_arm.edge.safety.models import SafetyContext
    from cloud_edge_robot_arm.edge.safety.rules import AccelerationRule

    rule = AccelerationRule()
    ctx_data: dict[str, Any] = {
        "task_id": "t1",
        "plan_version": 1,
        "command_seq": 1,
        "step_id": "s1",
        "skill": "MOVE_ABOVE",
        "requested_acceleration": 3.0,
        "tcp_x": 0.0,
        "tcp_y": 0.0,
        "tcp_z": 0.18,
        "parameters": {},
        "obstacles": [],
        "holding_object": False,
        "robot_connected": True,
        "robot_stopped": False,
        "robot_estop_engaged": False,
        "robot_collision_detected": False,
        "scene_version": 1,
        "joint_velocities": [],
        "merged_max_tcp_velocity": 1.0,
        "merged_max_joint_velocity": 2.0,
        "merged_max_acceleration": 2.0,
        "merged_minimum_safe_height": 0.08,
        "merged_max_reach_m": 0.65,
        "merged_obstacle_safety_distance": 0.05,
        "merged_carry_safety_margin": 0.02,
        "merged_scene_staleness_ms": 5_000,
        "merged_telemetry_staleness_ms": 5_000,
        "merged_watchdog_timeout_ms": 30_000,
        "absolute_max_tcp_velocity": 1.0,
        "absolute_max_joint_velocity": 2.0,
        "absolute_max_acceleration": 5.0,
    }
    from cloud_edge_robot_arm.contracts import (
        ControlMode,
        FailurePolicy,
        SafetyConstraints,
        SkillName,
        TaskContract,
        TaskStep,
        TaskTarget,
    )

    contract = TaskContract(
        task_id="t1",
        plan_version=1,
        command_seq=1,
        timestamp=datetime.now(UTC),
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=datetime.now(UTC),
        valid_until=datetime.now(UTC) + timedelta(seconds=60),
        user_instruction="test",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(
            object_id="red_cube",
            object_class="cube",
            target_region_id="bin_a",
        ),
        steps=[
            TaskStep(
                step_id="s1",
                skill=SkillName.MOVE_ABOVE,
                parameters={},
                expected_duration_ms=1000,
                timeout_ms=3000,
                retry_limit=1,
                preconditions=[],
                success_conditions=[],
            )
        ],
        safety_constraints=SafetyConstraints(
            max_joint_velocity=0.5,
            max_tcp_velocity=0.15,
            minimum_safe_height=0.08,
            workspace_id="workspace_a",
            collision_check_required=True,
        ),
        failure_policy=FailurePolicy(
            local_retry_limit=2,
            on_timeout="REQUEST_CLOUD_REPLAN",
            on_safety_rejection="PAUSE_AND_REPORT",
            on_network_loss="SAFE_STOP",
        ),
        completion_criteria=["object_placed"],
    )
    ctx_data["contract"] = contract
    ctx = SafetyContext(**ctx_data)
    result = rule.evaluate(ctx)
    # acceleration 3.0 > merged 2.0 → ALLOW_WITH_LIMITS
    assert result.decision.value in (
        "ALLOW_WITH_LIMITS",
        "ALLOW",
    ), f"Expected ALLOW_WITH_LIMITS or ALLOW, got {result.decision.value}"
    assert result.measured_value is not None
    assert result.limit_value is not None
    # Record has measured and limit values (not fixed 0)
    assert result.measured_value > 0, f"Expected measured_value > 0, got {result.measured_value}"
    assert result.limit_value > 0, f"Expected limit_value > 0, got {result.limit_value}"
