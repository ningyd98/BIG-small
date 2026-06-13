from __future__ import annotations

from datetime import UTC, datetime, timedelta

from cloud_edge_robot_arm.contracts import (
    ControlMode,
    FailurePolicy,
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)


def build_step(
    step_id: str,
    skill: SkillName,
    *,
    parameters: dict[str, object] | None = None,
    timeout_ms: int = 1_000,
    retry_limit: int = 0,
    preconditions: list[str] | None = None,
    success_conditions: list[str] | None = None,
) -> TaskStep:
    return TaskStep(
        step_id=step_id,
        skill=skill,
        parameters=parameters or {},
        expected_duration_ms=10,
        timeout_ms=timeout_ms,
        retry_limit=retry_limit,
        preconditions=preconditions or [],
        success_conditions=success_conditions or [],
    )


def build_pick_place_contract(
    *,
    task_id: str,
    command_seq: int = 1,
    plan_version: int = 1,
    issued_at: datetime | None = None,
    valid_ms: int = 60_000,
    local_retry_limit: int = 1,
) -> TaskContract:
    issued = issued_at or datetime.now(UTC)
    return TaskContract(
        task_id=task_id,
        plan_version=plan_version,
        command_seq=command_seq,
        timestamp=issued,
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=issued,
        valid_until=issued + timedelta(milliseconds=valid_ms),
        user_instruction="place the red cube into bin a",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(
            object_id="red_cube",
            object_class="cube",
            target_region_id="bin_a",
        ),
        steps=[
            build_step("step-home", SkillName.HOME, success_conditions=["robot_in_safe_pose"]),
            build_step(
                "step-move-above",
                SkillName.MOVE_ABOVE,
                parameters={"object_id": "red_cube", "z_offset_m": 0.12},
                success_conditions=["tcp_above_target"],
            ),
            build_step(
                "step-approach",
                SkillName.APPROACH,
                parameters={"object_id": "red_cube"},
                success_conditions=["tcp_near_target"],
            ),
            build_step(
                "step-grasp",
                SkillName.GRASP,
                parameters={"object_id": "red_cube"},
                retry_limit=1,
                success_conditions=["object_attached"],
            ),
            build_step(
                "step-lift",
                SkillName.LIFT,
                parameters={"height_m": 0.16},
                preconditions=["object_attached"],
                success_conditions=["object_attached"],
            ),
            build_step(
                "step-move-region",
                SkillName.MOVE_TO_REGION,
                parameters={"region_id": "bin_a"},
                preconditions=["object_attached"],
                success_conditions=["tcp_above_region"],
            ),
            build_step(
                "step-place",
                SkillName.PLACE,
                parameters={"region_id": "bin_a"},
                preconditions=["object_attached"],
                success_conditions=["object_inside_target_region"],
            ),
            build_step("step-release", SkillName.RELEASE, success_conditions=["gripper_open"]),
            build_step("step-retreat", SkillName.RETREAT, parameters={"distance_m": 0.1}),
            build_step(
                "step-home-final", SkillName.HOME, success_conditions=["robot_in_safe_pose"]
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
            local_retry_limit=local_retry_limit,
            on_timeout="SAFE_STOP",
            on_safety_rejection="PAUSE_AND_REPORT",
            on_network_loss="SAFE_STOP",
        ),
        completion_criteria=["object_inside_target_region", "robot_in_safe_pose"],
    )
