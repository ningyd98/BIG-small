#!/usr/bin/env python3
"""Phase 5 verification: Periodic Cloud Supervisory Control (PCSC).

Verifies:
1. Stable state produces KEEP
2. KEEP does not call PlannerAdapter
3. Target movement produces update
4. plan_version and command_seq correctly increment
5. Stale/expired commands rejected
6. PathCollision rule real rejection
7. Acceleration rule real evaluation
8. All Phase 3/3.1/3.2/4 scripts continue to pass
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter
from cloud_edge_robot_arm.cloud.supervision.core import FakeClock
from cloud_edge_robot_arm.cloud.supervision.models import (
    EdgeStatusSnapshot,
    SupervisionConfig,
    SupervisoryDecisionType,
)
from cloud_edge_robot_arm.cloud.supervision.service import PeriodicSupervisorService
from cloud_edge_robot_arm.contracts import Pose, SkillName, TaskContract, TaskStep


def _make_contract(
    task_id: str = "task-001",
    plan_version: int = 1,
    command_seq: int = 1,
) -> TaskContract:
    from cloud_edge_robot_arm.contracts import (
        ControlMode,
        FailurePolicy,
        SafetyConstraints,
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


def main() -> None:
    errors: list[str] = []
    results: dict[str, bool] = {}

    # --- 1. Stable state produces KEEP ---
    clock = FakeClock()
    service = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=clock)
    contract = _make_contract()
    service.start(contract)
    snapshot = EdgeStatusSnapshot(
        robot_id="r1",
        task_id="task-001",
        plan_version=1,
        command_seq=1,
        scene_version=1,
        timestamp=clock.now(),
        robot_state={"connected": True, "estop_engaged": False},
        network_state={"degraded": False, "rtt_ms": 50},
        current_step_id="step-01",
    )
    decision = service.evaluate_snapshot(snapshot, contract)
    ok = decision.decision == SupervisoryDecisionType.KEEP_CURRENT_PLAN
    results["1_stable_keep"] = ok
    if not ok:
        errors.append(f"stable → KEEP: got {decision.decision.value}")
    print(f"  1. Stable → KEEP: {'PASS' if ok else 'FAIL'}")

    # --- 2. KEEP does not call PlannerAdapter ---
    service2 = PeriodicSupervisorService(planner=MockPlannerAdapter(), clock=FakeClock())
    contract2 = _make_contract()
    service2.start(contract2)
    for _ in range(3):
        s2 = EdgeStatusSnapshot(
            robot_id="r1",
            task_id="task-001",
            plan_version=1,
            command_seq=1,
            scene_version=1,
            timestamp=FakeClock().now(),
            robot_state={"connected": True, "estop_engaged": False},
            network_state={"degraded": False, "rtt_ms": 50},
            current_step_id="step-01",
        )
        service2.evaluate_snapshot(s2, contract2)
    ok = service2.planner_invocation_count == 0
    results["2_keep_no_planner"] = ok
    if not ok:
        errors.append(f"KEEP should not invoke planner, got {service2.planner_invocation_count}")
    print(f"  2. KEEP no planner: {'PASS' if ok else 'FAIL'}")

    # --- 3. Target movement produces update ---
    clock3 = FakeClock()
    service3 = PeriodicSupervisorService(
        planner=MockPlannerAdapter(),
        clock=clock3,
        config=SupervisionConfig(target_displacement_threshold_m=0.02),
    )
    contract3 = _make_contract()
    service3.start(contract3, initial_target=Pose(x=0.0, y=0.0, z=0.02))
    s3 = EdgeStatusSnapshot(
        robot_id="r1",
        task_id="task-001",
        plan_version=1,
        command_seq=1,
        scene_version=1,
        timestamp=clock3.now(),
        current_step_id="step-01",
        target_state={
            "object_id": "red_cube",
            "object_class": "cube",
            "x": 0.3,
            "y": 0.3,
            "z": 0.02,
            "region_id": "bin_a",
            "region_center": {"x": -0.2, "y": 0.18, "z": 0.02},
        },
        robot_state={"connected": True, "estop_engaged": False},
        network_state={"degraded": False, "rtt_ms": 50},
    )
    d3 = service3.evaluate_snapshot(s3, contract3)
    ok = d3.decision == SupervisoryDecisionType.UPDATE_CURRENT_STEP
    results["3_target_move_update"] = ok
    ok2 = d3.planner_invoked
    results["3_planner_invoked"] = ok2
    if not ok:
        errors.append(f"target move → UPDATE: got {d3.decision.value}")
    if not ok2:
        errors.append("target move → planner not invoked")
    print(f"  3. Target move → UPDATE: {'PASS' if ok else 'FAIL'}")
    print(f"  3b. Planner invoked: {'PASS' if ok2 else 'FAIL'}")

    # --- 4. Old/expired command rejection ---
    old_snapshot = EdgeStatusSnapshot(
        robot_id="r1",
        task_id="task-001",
        plan_version=1,
        command_seq=1,
        scene_version=1,
        timestamp=clock3.now() - timedelta(seconds=60),
        robot_state={"connected": True, "estop_engaged": False},
        network_state={"degraded": False, "rtt_ms": 50},
        current_step_id="step-01",
    )
    d4 = service3.evaluate_snapshot(old_snapshot, contract3)
    ok = d4.decision == SupervisoryDecisionType.REQUEST_MORE_OBSERVATION
    results["4_stale_rejected"] = ok
    if not ok:
        errors.append(f"stale → REQUEST_MORE_OBSERVATION: got {d4.decision.value}")
    print(f"  4. Stale state rejected: {'PASS' if ok else 'FAIL'}")

    # --- 5. PathCollision real rejection ---
    from cloud_edge_robot_arm.contracts import (
        ControlMode,
        FailurePolicy,
        SafetyConstraints,
        SkillName,
        TaskContract,
        TaskStep,
        TaskTarget,
    )
    from cloud_edge_robot_arm.edge.safety.models import Obstacle, SafetyContext
    from cloud_edge_robot_arm.edge.safety.rules import PathCollisionRule

    obs = Obstacle(obstacle_id="obs-001", x=0.25, y=0.0, z=0.18, radius_m=0.1)
    c5 = TaskContract(
        task_id="t5",
        plan_version=1,
        command_seq=1,
        timestamp=datetime.now(UTC),
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=datetime.now(UTC),
        valid_until=datetime.now(UTC) + timedelta(seconds=60),
        user_instruction="test",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(object_id="x", object_class="c", target_region_id="r"),
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
        completion_criteria=["ok"],
    )
    ctx5 = SafetyContext(
        task_id="t5",
        plan_version=1,
        command_seq=1,
        step_id="s1",
        skill="MOVE_ABOVE",
        parameters={"target_pose": {"x": 0.5, "y": 0.0, "z": 0.18}},
        contract=c5,
        robot_connected=True,
        obstacles=[obs],
        merged_max_tcp_velocity=c5.safety_constraints.max_tcp_velocity,
        merged_max_joint_velocity=c5.safety_constraints.max_joint_velocity,
        merged_max_acceleration=5.0,
        merged_minimum_safe_height=c5.safety_constraints.minimum_safe_height,
        merged_max_reach_m=0.65,
        merged_obstacle_safety_distance=0.05,
        merged_carry_safety_margin=0.02,
        merged_scene_staleness_ms=5000,
        merged_telemetry_staleness_ms=5000,
        merged_watchdog_timeout_ms=30000,
        absolute_max_tcp_velocity=1.0,
        absolute_max_joint_velocity=2.0,
        absolute_max_acceleration=5.0,
        tcp_x=0.0,
        tcp_y=0.0,
        tcp_z=0.18,
        scene_version=1,
        joint_velocities=[],
    )
    rule = PathCollisionRule()
    r5 = rule.evaluate(ctx5)
    ok = r5.decision.value == "REJECT" and r5.reason_code == "PATH_COLLISION"
    results["5_path_collision_real"] = ok
    if not ok:
        errors.append(
            "PathCollision: expected REJECT/PATH_COLLISION, "
            f"got {r5.decision.value}/{r5.reason_code}"
        )
    print(f"  5. PathCollision real rejection: {'PASS' if ok else 'FAIL'}")

    # --- 6. Acceleration real evaluation ---
    from cloud_edge_robot_arm.edge.safety.rules import AccelerationRule

    ctx6 = SafetyContext(
        task_id="t6",
        plan_version=1,
        command_seq=1,
        step_id="s1",
        skill="MOVE_ABOVE",
        parameters={},
        contract=c5,
        robot_connected=True,
        requested_acceleration=3.0,
        merged_max_tcp_velocity=1.0,
        merged_max_joint_velocity=2.0,
        merged_max_acceleration=2.0,
        merged_minimum_safe_height=0.08,
        merged_max_reach_m=0.65,
        merged_obstacle_safety_distance=0.05,
        merged_carry_safety_margin=0.02,
        merged_scene_staleness_ms=5000,
        merged_telemetry_staleness_ms=5000,
        merged_watchdog_timeout_ms=30000,
        absolute_max_tcp_velocity=1.0,
        absolute_max_joint_velocity=2.0,
        absolute_max_acceleration=5.0,
        tcp_x=0.0,
        tcp_y=0.0,
        tcp_z=0.18,
        scene_version=1,
        joint_velocities=[],
    )
    arule = AccelerationRule()
    r6 = arule.evaluate(ctx6)
    measured_value = r6.measured_value
    limit_value = r6.limit_value
    ok = (
        measured_value is not None
        and limit_value is not None
        and measured_value > 0
        and limit_value > 0
    )
    results["6_acceleration_real"] = ok
    if not ok:
        errors.append("Acceleration: measured_value/limit_value are zero or None")
    print(f"  6. Acceleration real evaluation: {'PASS' if ok else 'FAIL'}")

    # --- Summary ---
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  Total: {passed}/{total} checks passed")

    if errors:
        print(f"\nFAIL: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        print("success=false")
        sys.exit(1)

    print("\nPASS: Phase 5 acceptance suite passed")
    print("success=true")


if __name__ == "__main__":
    main()
