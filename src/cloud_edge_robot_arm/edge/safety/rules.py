from __future__ import annotations

import time
from datetime import UTC, datetime
from math import hypot, sqrt

from cloud_edge_robot_arm.contracts import SafetyDecision
from cloud_edge_robot_arm.edge.safety.errors import (
    ACCELERATION_EXCEEDED,
    CARRY_SAFETY_MARGIN,
    COLLISION_DETECTED,
    COMMAND_EXPIRED,
    CONTEXT_MISMATCH,
    DEVICE_DISCONNECTED,
    ESTOP_ACTIVE,
    FORBIDDEN_ZONE_VIOLATION,
    JOINT_VELOCITY_EXCEEDED,
    MINIMUM_HEIGHT_VIOLATION,
    OBSTACLE_DISTANCE_VIOLATION,
    PATH_COLLISION,
    REACHABILITY_VIOLATION,
    SCENE_FRESHNESS_STALE,
    SCENE_VERSION_MISMATCH,
    STEP_TIMEOUT,
    TASK_DEADLINE_EXCEEDED,
    VELOCITY_EXCEEDED,
    WATCHDOG_TIMEOUT,
    WORKSPACE_VIOLATION,
)
from cloud_edge_robot_arm.edge.safety.models import SafetyContext
from cloud_edge_robot_arm.edge.safety.rule_registry import SafetyRuleEvaluator, SafetyRuleResult

MOTION_SKILLS = {
    "HOME",
    "MOVE_ABOVE",
    "APPROACH",
    "GRASP",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RELEASE",
    "RETREAT",
}

SKILLS_WITH_TARGET_POSE = {
    "MOVE_ABOVE",
    "APPROACH",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RETREAT",
}


def _get_merged_max_tcp_vel(ctx: SafetyContext) -> float:
    merged = ctx.merged_max_tcp_velocity
    contract_limit = ctx.contract.safety_constraints.max_tcp_velocity
    if merged is not None:
        return min(merged, contract_limit)
    return contract_limit


def _get_merged_max_joint_vel(ctx: SafetyContext) -> float:
    merged = ctx.merged_max_joint_velocity
    contract_limit = ctx.contract.safety_constraints.max_joint_velocity
    if merged is not None:
        return min(merged, contract_limit)
    return contract_limit


def _get_merged_max_accel(ctx: SafetyContext) -> float:
    if ctx.merged_max_acceleration is not None:
        return ctx.merged_max_acceleration
    return 5.0


def _get_merged_min_height(ctx: SafetyContext) -> float:
    merged = ctx.merged_minimum_safe_height
    contract_limit = ctx.contract.safety_constraints.minimum_safe_height
    if merged is not None:
        return min(merged, contract_limit)
    return contract_limit


def _get_merged_max_reach(ctx: SafetyContext) -> float:
    if ctx.merged_max_reach_m is not None:
        return ctx.merged_max_reach_m
    return 0.65


def _get_merged_obstacle_dist(ctx: SafetyContext) -> float:
    if ctx.merged_obstacle_safety_distance is not None:
        return ctx.merged_obstacle_safety_distance
    return 0.05


def _get_merged_carry_margin(ctx: SafetyContext) -> float:
    if ctx.merged_carry_safety_margin is not None:
        return ctx.merged_carry_safety_margin
    return 0.02


def _get_merged_scene_staleness(ctx: SafetyContext) -> int:
    if ctx.merged_scene_staleness_ms is not None:
        return ctx.merged_scene_staleness_ms
    return 5_000


def _get_merged_tel_staleness(ctx: SafetyContext) -> int:
    if ctx.merged_telemetry_staleness_ms is not None:
        return ctx.merged_telemetry_staleness_ms
    return 5_000


def _get_merged_watchdog_timeout(ctx: SafetyContext) -> int:
    if ctx.merged_watchdog_timeout_ms is not None:
        return ctx.merged_watchdog_timeout_ms
    return 30_000


def _get_absolute_max_tcp_vel(ctx: SafetyContext) -> float:
    if ctx.absolute_max_tcp_velocity is not None:
        return ctx.absolute_max_tcp_velocity
    return _get_merged_max_tcp_vel(ctx)


def _get_absolute_max_joint_vel(ctx: SafetyContext) -> float:
    if ctx.absolute_max_joint_velocity is not None:
        return ctx.absolute_max_joint_velocity
    return _get_merged_max_joint_vel(ctx)


def _get_absolute_max_accel(ctx: SafetyContext) -> float:
    if ctx.absolute_max_acceleration is not None:
        return ctx.absolute_max_acceleration
    return _get_merged_max_accel(ctx)


def _point_segment_distance_sq(
    px: float,
    py: float,
    pz: float,
    ax: float,
    ay: float,
    az: float,
    bx: float,
    by: float,
    bz: float,
) -> float:
    dx, dy, dz = bx - ax, by - ay, bz - az
    len_sq = dx * dx + dy * dy + dz * dz
    if len_sq < 1e-12:
        return (px - ax) ** 2 + (py - ay) ** 2 + (pz - az) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy + (pz - az) * dz) / len_sq))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    proj_z = az + t * dz
    return (px - proj_x) ** 2 + (py - proj_y) ** 2 + (pz - proj_z) ** 2


class CommandExpiredRule(SafetyRuleEvaluator):
    rule_id = "CMD_EXPIRED"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.command_valid_until is None or ctx.wall_clock_now is None:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code="NO_DEADLINE",
                message="command deadline missing - fail closed",
            )
        if ctx.wall_clock_now > ctx.command_valid_until:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=COMMAND_EXPIRED,
                message="command has expired",
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="CMD_FRESH",
            message="command is still valid",
        )


class TelemetryFreshnessRule(SafetyRuleEvaluator):
    rule_id = "TEL_FRESH"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.telemetry_timestamp is None:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.PAUSE,
                reason_code="TEL_MISSING",
                message="telemetry timestamp missing - fail closed",
            )
        now = ctx.wall_clock_now or datetime.now(UTC)
        staleness_ms = (now - ctx.telemetry_timestamp).total_seconds() * 1000
        limit = float(_get_merged_tel_staleness(ctx))
        if staleness_ms > limit:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.PAUSE,
                reason_code=SCENE_FRESHNESS_STALE,
                message=f"telemetry is stale by {staleness_ms:.0f}ms",
                measured_value=staleness_ms,
                limit_value=limit,
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="TEL_FRESH",
            message="telemetry is fresh",
        )


class SceneFreshnessRule(SafetyRuleEvaluator):
    rule_id = "SCENE_FRESH"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.scene_updated_at is None:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.PAUSE,
                reason_code="SCENE_MISSING",
                message="scene timestamp missing - fail closed",
            )
        now = ctx.wall_clock_now or datetime.now(UTC)
        staleness_ms = (now - ctx.scene_updated_at).total_seconds() * 1000
        limit = float(_get_merged_scene_staleness(ctx))
        if staleness_ms > limit:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.PAUSE,
                reason_code=SCENE_FRESHNESS_STALE,
                message=f"scene data is stale by {staleness_ms:.0f}ms",
                measured_value=staleness_ms,
                limit_value=limit,
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="SCENE_FRESH",
            message="scene data is fresh",
        )


class SceneVersionRule(SafetyRuleEvaluator):
    rule_id = "SCENE_VERSION"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        expected = ctx.contract.expected_scene_version
        actual = ctx.scene_version
        if actual != expected:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=SCENE_VERSION_MISMATCH,
                message=f"scene version mismatch: expected {expected}, got {actual}",
                measured_value=float(actual),
                limit_value=float(expected),
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="SCENE_MATCH",
            message="scene version matches",
        )


class ContextMatchRule(SafetyRuleEvaluator):
    rule_id = "CTX_MATCH"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        issues: list[str] = []
        if ctx.plan_version != ctx.contract.plan_version:
            issues.append(
                f"plan_version mismatch: {ctx.plan_version} vs {ctx.contract.plan_version}"
            )
        if ctx.command_seq != ctx.contract.command_seq:
            issues.append(f"command_seq mismatch: {ctx.command_seq} vs {ctx.contract.command_seq}")
        if ctx.step_id and ctx.step_id not in {s.step_id for s in ctx.contract.steps}:
            issues.append(f"step_id {ctx.step_id!r} not in contract")
        if issues:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=CONTEXT_MISMATCH,
                message="; ".join(issues),
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="CTX_OK",
            message="context matches contract",
        )


class DeviceConnectedRule(SafetyRuleEvaluator):
    rule_id = "DEV_CONNECTED"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if not ctx.robot_connected:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=DEVICE_DISCONNECTED,
                message="robot is not connected",
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="DEV_OK",
            message="device is connected",
        )


class EStopRule(SafetyRuleEvaluator):
    rule_id = "ESTOP"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.robot_estop_engaged:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.EMERGENCY_STOP,
                reason_code=ESTOP_ACTIVE,
                message="emergency stop is engaged",
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="ESTOP_CLEAR",
            message="no emergency stop active",
        )


class CollisionRule(SafetyRuleEvaluator):
    rule_id = "COLLISION"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.robot_collision_detected:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.EMERGENCY_STOP,
                reason_code=COLLISION_DETECTED,
                message="collision detected",
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="NO_COLLISION",
            message="no collision detected",
        )


def _in_workspace(
    x: float,
    y: float,
    z: float,
    ws_min_x: float,
    ws_max_x: float,
    ws_min_y: float,
    ws_max_y: float,
    ws_min_z: float,
    ws_max_z: float,
) -> bool:
    return ws_min_x <= x <= ws_max_x and ws_min_y <= y <= ws_max_y and ws_min_z <= z <= ws_max_z


class WorkspaceRule(SafetyRuleEvaluator):
    rule_id = "WORKSPACE"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.skill not in MOTION_SKILLS:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NON_MOTION",
                message="skill is not a motion skill",
            )
        ws = ctx.contract.safety_constraints.workspace_id
        ws_x_min, ws_x_max = -0.5, 0.5
        ws_y_min, ws_y_max = -0.5, 0.5
        ws_z_min, ws_z_max = 0.0, 0.6

        if not _in_workspace(
            ctx.tcp_x,
            ctx.tcp_y,
            ctx.tcp_z,
            ws_x_min,
            ws_x_max,
            ws_y_min,
            ws_y_max,
            ws_z_min,
            ws_z_max,
        ):
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=WORKSPACE_VIOLATION,
                message=(
                    f"current TCP ({ctx.tcp_x:.3f}, {ctx.tcp_y:.3f}, {ctx.tcp_z:.3f}) "
                    f"outside workspace"
                ),
                details={"workspace_id": ws, "check": "current_pose"},
            )

        target = ctx.parameters.get("target_pose")
        if isinstance(target, dict):
            tx = float(target.get("x", ctx.tcp_x))
            ty = float(target.get("y", ctx.tcp_y))
            tz = float(target.get("z", ctx.tcp_z))
            if not _in_workspace(
                tx, ty, tz, ws_x_min, ws_x_max, ws_y_min, ws_y_max, ws_z_min, ws_z_max
            ):
                return SafetyRuleResult(
                    rule_id=self.rule_id,
                    decision=SafetyDecision.REJECT,
                    reason_code=WORKSPACE_VIOLATION,
                    message=(f"target TCP ({tx:.3f}, {ty:.3f}, {tz:.3f}) outside workspace"),
                    details={"workspace_id": ws, "check": "target_pose"},
                )

        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="WS_OK",
            message="TCP and target within workspace",
        )


class ForbiddenZoneRule(SafetyRuleEvaluator):
    rule_id = "FORBIDDEN"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.skill not in MOTION_SKILLS:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NON_MOTION",
                message="skill is not a motion skill",
            )
        for zone in ctx.forbidden_zones:
            if (
                zone.x_min <= ctx.tcp_x <= zone.x_max
                and zone.y_min <= ctx.tcp_y <= zone.y_max
                and zone.z_min <= ctx.tcp_z <= zone.z_max
            ):
                return SafetyRuleResult(
                    rule_id=self.rule_id,
                    decision=SafetyDecision.REJECT,
                    reason_code=FORBIDDEN_ZONE_VIOLATION,
                    message=f"TCP in forbidden zone {zone.workspace_id}",
                )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="NO_FORBIDDEN",
            message="TCP is not in any forbidden zone",
        )


class ReachabilityRule(SafetyRuleEvaluator):
    rule_id = "REACHABILITY"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.skill not in SKILLS_WITH_TARGET_POSE:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NON_MOTION",
                message="skill does not require reachability check",
            )
        max_reach = _get_merged_max_reach(ctx)
        target = ctx.parameters.get("target_pose")
        if isinstance(target, dict):
            tx = float(target.get("x", 0))
            ty = float(target.get("y", 0))
            distance = hypot(tx, ty)
        else:
            distance = hypot(ctx.tcp_x, ctx.tcp_y)

        if distance > max_reach:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=REACHABILITY_VIOLATION,
                message=f"target unreachable: distance {distance:.3f}m > max {max_reach:.3f}m",
                measured_value=distance,
                limit_value=max_reach,
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="REACHABLE",
            message="target is reachable",
        )


class TcpVelocityRule(SafetyRuleEvaluator):
    rule_id = "TCP_VEL"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.skill not in MOTION_SKILLS:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NON_MOTION",
                message="skill is not a motion skill",
            )
        max_vel = _get_merged_max_tcp_vel(ctx)
        absolute = _get_absolute_max_tcp_vel(ctx)
        if ctx.tcp_velocity > absolute:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=VELOCITY_EXCEEDED,
                message=(
                    f"TCP velocity {ctx.tcp_velocity:.3f} exceeds absolute max {absolute:.3f}"
                ),
                measured_value=ctx.tcp_velocity,
                limit_value=absolute,
            )
        if ctx.tcp_velocity > max_vel:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW_WITH_LIMITS,
                reason_code="TCP_VELOCITY_LIMITED",
                message=(f"TCP velocity {ctx.tcp_velocity:.3f} limited to {max_vel:.3f}"),
                measured_value=ctx.tcp_velocity,
                limit_value=max_vel,
                limited_parameters={"tcp_velocity": max_vel},
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="VEL_OK",
            message="TCP velocity within limits",
        )


class JointVelocityRule(SafetyRuleEvaluator):
    rule_id = "JOINT_VEL"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.skill not in MOTION_SKILLS:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NON_MOTION",
                message="skill is not a motion skill",
            )
        max_vel = _get_merged_max_joint_vel(ctx)
        absolute = _get_absolute_max_joint_vel(ctx)
        if not ctx.joint_velocities:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="JOINT_VEL_OK",
                message="no joint velocity samples to check",
            )
        worst = max(ctx.joint_velocities)
        if worst > absolute:
            idx = ctx.joint_velocities.index(worst)
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=JOINT_VELOCITY_EXCEEDED,
                message=f"joint {idx} velocity {worst:.3f} exceeds absolute max {absolute:.3f}",
                measured_value=worst,
                limit_value=absolute,
            )
        if worst > max_vel:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW_WITH_LIMITS,
                reason_code="JOINT_VELOCITY_LIMITED",
                message=f"joint velocity {worst:.3f} limited to {max_vel:.3f}",
                measured_value=worst,
                limit_value=max_vel,
                limited_parameters={"joint_velocity": max_vel},
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="JOINT_VEL_OK",
            message="joint velocities within limits",
        )


class AccelerationRule(SafetyRuleEvaluator):
    rule_id = "ACCEL"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.skill not in MOTION_SKILLS:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NON_MOTION",
                message="skill is not a motion skill",
            )
        max_accel = _get_merged_max_accel(ctx)
        absolute = _get_absolute_max_accel(ctx)
        accel = ctx.requested_acceleration
        if accel > absolute:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=ACCELERATION_EXCEEDED,
                message=f"acceleration {accel:.3f} exceeds absolute max {absolute:.3f}",
                measured_value=accel,
                limit_value=absolute,
            )
        if accel > max_accel:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW_WITH_LIMITS,
                reason_code="ACCELERATION_LIMITED",
                message=f"acceleration {accel:.3f} limited to {max_accel:.3f}",
                measured_value=accel,
                limit_value=max_accel,
                limited_parameters={"acceleration": max_accel},
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="ACCEL_OK",
            message="acceleration within limits",
        )


class MinimumHeightRule(SafetyRuleEvaluator):
    rule_id = "MIN_HEIGHT"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.skill not in MOTION_SKILLS:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NON_MOTION",
                message="skill is not a motion skill",
            )
        min_height = _get_merged_min_height(ctx)
        low_height_skills = {"APPROACH", "GRASP", "PLACE", "RELEASE"}
        if ctx.skill in low_height_skills:
            if ctx.scene_updated_at is None:
                return SafetyRuleResult(
                    rule_id=self.rule_id,
                    decision=SafetyDecision.REJECT,
                    reason_code=MINIMUM_HEIGHT_VIOLATION,
                    message=(f"low-height exception for {ctx.skill} requires fresh scene data"),
                )
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="LOW_HEIGHT_EXCEPTION",
                message=f"skill {ctx.skill} exempt from minimum height",
            )
        if ctx.tcp_z < min_height:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=MINIMUM_HEIGHT_VIOLATION,
                message=f"TCP height {ctx.tcp_z:.3f} below minimum {min_height:.3f}",
                measured_value=ctx.tcp_z,
                limit_value=min_height,
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="HEIGHT_OK",
            message="TCP height within limits",
        )


class ObstacleDistanceRule(SafetyRuleEvaluator):
    rule_id = "OBSTACLE"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.skill not in MOTION_SKILLS:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NON_MOTION",
                message="skill is not a motion skill",
            )
        safety_dist = _get_merged_obstacle_dist(ctx)
        carry_margin = _get_merged_carry_margin(ctx) if ctx.holding_object else 0.0
        effective_dist = safety_dist + carry_margin
        for obs in ctx.obstacles:
            dist = hypot(ctx.tcp_x - obs.x, ctx.tcp_y - obs.y)
            min_dist = obs.radius_m + effective_dist
            if dist < min_dist:
                return SafetyRuleResult(
                    rule_id=self.rule_id,
                    decision=SafetyDecision.REJECT,
                    reason_code=OBSTACLE_DISTANCE_VIOLATION,
                    message=(
                        f"TCP too close to obstacle {obs.obstacle_id}: "
                        f"{dist:.3f}m < {min_dist:.3f}m"
                    ),
                    measured_value=dist,
                    limit_value=min_dist,
                )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="OBSTACLE_CLEAR",
            message="sufficient distance from obstacles",
        )


class PathCollisionRule(SafetyRuleEvaluator):
    rule_id = "PATH_COLLISION"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.skill not in MOTION_SKILLS:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NON_MOTION",
                message="skill is not a motion skill",
            )
        if not ctx.contract.safety_constraints.collision_check_required:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=PATH_COLLISION,
                message="collision check required but disabled in contract - fail closed",
            )
        if not ctx.obstacles:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NO_OBSTACLES",
                message="no obstacles to check against",
            )
        tcp_radius = 0.02
        carry_margin = _get_merged_carry_margin(ctx) if ctx.holding_object else 0.0
        effective_radius = tcp_radius + carry_margin
        safety_dist = _get_merged_obstacle_dist(ctx)
        min_clearance = effective_radius + safety_dist

        ax, ay, az = ctx.tcp_x, ctx.tcp_y, ctx.tcp_z
        target = ctx.parameters.get("target_pose")
        if isinstance(target, dict):
            bx = float(target.get("x", ax))
            by = float(target.get("y", ay))
            bz = float(target.get("z", az))
        else:
            bx, by, bz = ax, ay, az

        for obs in ctx.obstacles:
            dist_sq = _point_segment_distance_sq(obs.x, obs.y, obs.z, ax, ay, az, bx, by, bz)
            effective_min = obs.radius_m + min_clearance
            if dist_sq < effective_min * effective_min:
                dist = sqrt(dist_sq)
                return SafetyRuleResult(
                    rule_id=self.rule_id,
                    decision=SafetyDecision.REJECT,
                    reason_code=PATH_COLLISION,
                    message=(
                        f"path intersects obstacle {obs.obstacle_id}: "
                        f"clearance {dist:.3f}m < {effective_min:.3f}m"
                    ),
                    measured_value=dist,
                    limit_value=effective_min,
                )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="PATH_CLEAR",
            message="path collision check passed",
        )


class CarrySafetyRule(SafetyRuleEvaluator):
    rule_id = "CARRY_MARGIN"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if not ctx.holding_object:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NO_CARRY",
                message="not carrying an object",
            )
        if ctx.skill not in MOTION_SKILLS:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NON_MOTION",
                message="skill is not a motion skill",
            )
        carry_margin = _get_merged_carry_margin(ctx)
        if carry_margin <= 0:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=CARRY_SAFETY_MARGIN,
                message="carrying object but carry_safety_margin is zero - fail closed",
                measured_value=carry_margin,
                limit_value=0.01,
            )
        obstacle_dist = _get_merged_obstacle_dist(ctx)
        effective = obstacle_dist + carry_margin
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="CARRY_OK",
            message=f"carrying object with effective clearance {effective:.3f}m",
            measured_value=carry_margin,
            limit_value=obstacle_dist,
        )


class StepTimeoutRule(SafetyRuleEvaluator):
    rule_id = "STEP_TIMEOUT"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.step_started_at is None:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code="STEP_START_MISSING",
                message="step start time missing - fail closed",
            )
        now = ctx.monotonic_now if ctx.monotonic_now is not None else time.monotonic()
        elapsed_ms = (now - ctx.step_started_at) * 1000
        step_obj = None
        for s in ctx.contract.steps:
            if s.step_id == ctx.step_id:
                step_obj = s
                break
        if step_obj is None:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code="STEP_NOT_FOUND",
                message=f"step {ctx.step_id!r} not found in contract - fail closed",
            )
        limit_ms = float(step_obj.timeout_ms)
        if elapsed_ms > limit_ms:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=STEP_TIMEOUT,
                message=(
                    f"step {ctx.step_id} exceeded timeout: {elapsed_ms:.0f}ms > {limit_ms:.0f}ms"
                ),
                measured_value=elapsed_ms,
                limit_value=limit_ms,
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="STEP_TIME_OK",
            message="step within timeout",
        )


class TaskDeadlineRule(SafetyRuleEvaluator):
    rule_id = "TASK_DEADLINE"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.task_deadline_utc is None or ctx.wall_clock_now is None:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code="DEADLINE_MISSING",
                message="task deadline missing - fail closed",
            )
        remaining_ms = (ctx.task_deadline_utc - ctx.wall_clock_now).total_seconds() * 1000
        if remaining_ms <= 0:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=TASK_DEADLINE_EXCEEDED,
                message=f"task deadline exceeded by {-remaining_ms:.0f}ms",
                measured_value=0.0,
                limit_value=0.0,
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="DEADLINE_OK",
            message=f"task deadline OK: {remaining_ms:.0f}ms remaining",
        )


class WatchdogRule(SafetyRuleEvaluator):
    rule_id = "WATCHDOG"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.task_started_at_mono is None:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code="WATCHDOG_MISSING",
                message="watchdog not started - fail closed",
            )
        now = ctx.monotonic_now if ctx.monotonic_now is not None else time.monotonic()
        elapsed_ms = (now - ctx.task_started_at_mono) * 1000
        limit_ms = float(_get_merged_watchdog_timeout(ctx))
        if elapsed_ms > limit_ms:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.EMERGENCY_STOP,
                reason_code=WATCHDOG_TIMEOUT,
                message=f"watchdog timeout: {elapsed_ms:.0f}ms > {limit_ms:.0f}ms",
                measured_value=elapsed_ms,
                limit_value=limit_ms,
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="WATCHDOG_OK",
            message="watchdog within limits",
        )


ALL_RULES: list[type[SafetyRuleEvaluator]] = [
    CommandExpiredRule,
    TelemetryFreshnessRule,
    SceneFreshnessRule,
    SceneVersionRule,
    ContextMatchRule,
    DeviceConnectedRule,
    EStopRule,
    CollisionRule,
    WorkspaceRule,
    ForbiddenZoneRule,
    ReachabilityRule,
    TcpVelocityRule,
    JointVelocityRule,
    AccelerationRule,
    MinimumHeightRule,
    ObstacleDistanceRule,
    PathCollisionRule,
    CarrySafetyRule,
    StepTimeoutRule,
    TaskDeadlineRule,
    WatchdogRule,
]
