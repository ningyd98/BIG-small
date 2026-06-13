from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts import RobotState, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.safety.models import (
    Obstacle,
    SafetyContext,
    WorkspaceDefinition,
)
from cloud_edge_robot_arm.edge.safety.policy import MergedSafetyConstraints


class SafetyContextBuilder:
    def __init__(
        self,
        *,
        merged: MergedSafetyConstraints,
        obstacles: list[Obstacle] | None = None,
        forbidden_zones: list[WorkspaceDefinition] | None = None,
    ) -> None:
        self._merged = merged
        self._obstacles = obstacles or merged.obstacles
        self._forbidden_zones = forbidden_zones or merged.forbidden_zones

    def build(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        robot_state: RobotState,
        scene_version: int,
        scene_updated_at: datetime | None = None,
        telemetry_timestamp: datetime | None = None,
        step_started_at_mono: float | None = None,
        task_started_at_mono: float | None = None,
        requested_velocity: float = 0.0,
        requested_acceleration: float = 0.0,
        wall_clock_now: datetime | None = None,
    ) -> SafetyContext:
        now = wall_clock_now or datetime.now(UTC)
        return SafetyContext(
            task_id=contract.task_id,
            plan_version=contract.plan_version,
            command_seq=contract.command_seq,
            step_id=step.step_id,
            skill=step.skill.value,
            parameters=dict(step.parameters),
            contract=contract,
            robot_connected=robot_state.connected,
            robot_stopped=robot_state.stopped,
            robot_estop_engaged=robot_state.estop_engaged,
            robot_collision_detected=robot_state.collision_detected,
            tcp_x=robot_state.tcp_pose.x,
            tcp_y=robot_state.tcp_pose.y,
            tcp_z=robot_state.tcp_pose.z,
            tcp_velocity=requested_velocity,
            requested_acceleration=requested_acceleration,
            joint_velocities=[],
            scene_version=scene_version,
            scene_updated_at=scene_updated_at,
            telemetry_timestamp=telemetry_timestamp,
            command_issued_at=contract.issued_at,
            command_valid_until=contract.valid_until,
            obstacles=list(self._obstacles),
            forbidden_zones=list(self._forbidden_zones),
            holding_object=robot_state.holding_object_id is not None,
            step_started_at=step_started_at_mono,
            task_started_at_mono=task_started_at_mono,
            task_deadline_utc=contract.valid_until,
            wall_clock_now=now,
            merged_max_tcp_velocity=self._merged.max_tcp_velocity,
            merged_max_joint_velocity=self._merged.max_joint_velocity,
            merged_max_acceleration=self._merged.max_acceleration,
            merged_minimum_safe_height=self._merged.minimum_safe_height,
            merged_max_reach_m=self._merged.max_reach_m,
            merged_obstacle_safety_distance=self._merged.obstacle_safety_distance,
            merged_carry_safety_margin=self._merged.carry_safety_margin,
            merged_scene_staleness_ms=self._merged.scene_staleness_ms,
            merged_telemetry_staleness_ms=self._merged.telemetry_staleness_ms,
            merged_watchdog_timeout_ms=self._merged.watchdog_timeout_ms,
        )
