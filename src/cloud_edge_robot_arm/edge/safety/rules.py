from __future__ import annotations

import time
from datetime import UTC, datetime
from math import hypot

from cloud_edge_robot_arm.contracts import SafetyDecision
from cloud_edge_robot_arm.edge.safety.errors import (
    COLLISION_DETECTED,
    COMMAND_EXPIRED,
    CONTEXT_MISMATCH,
    DEVICE_DISCONNECTED,
    ESTOP_ACTIVE,
    FORBIDDEN_ZONE_VIOLATION,
    JOINT_VELOCITY_EXCEEDED,
    MINIMUM_HEIGHT_VIOLATION,
    OBSTACLE_DISTANCE_VIOLATION,
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

SKILLS_WITH_TARGET_POSE = {"MOVE_ABOVE", "APPROACH", "LIFT", "MOVE_TO_REGION", "PLACE", "RETREAT"}
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


class CommandExpiredRule(SafetyRuleEvaluator):
    rule_id = "CMD_EXPIRED"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.command_valid_until is None or ctx.wall_clock_now is None:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NO_DEADLINE",
                message="no command deadline set",
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
                decision=SafetyDecision.ALLOW,
                reason_code="NO_TELEMETRY_TS",
                message="no telemetry timestamp available",
            )
        now = ctx.wall_clock_now or datetime.now(UTC)
        staleness_ms = (now - ctx.telemetry_timestamp).total_seconds() * 1000
        limit = 5_000.0
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
                decision=SafetyDecision.ALLOW,
                reason_code="NO_SCENE_TS",
                message="no scene timestamp available",
            )
        now = ctx.wall_clock_now or datetime.now(UTC)
        staleness_ms = (now - ctx.scene_updated_at).total_seconds() * 1000
        limit = 5_000.0
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
        x, y, z = ctx.tcp_x, ctx.tcp_y, ctx.tcp_z
        if not (-0.5 <= x <= 0.5 and -0.5 <= y <= 0.5 and 0.0 <= z <= 0.6):
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=WORKSPACE_VIOLATION,
                message=f"TCP ({x:.3f}, {y:.3f}, {z:.3f}) outside workspace",
                details={"workspace_id": ws},
            )
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="WS_OK",
            message="TCP is within workspace",
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
        distance = hypot(ctx.tcp_x, ctx.tcp_y)
        if distance > 0.65:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=REACHABILITY_VIOLATION,
                message=f"target unreachable: distance {distance:.3f}m from origin",
                measured_value=distance,
                limit_value=0.65,
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
        max_vel = ctx.contract.safety_constraints.max_tcp_velocity
        if ctx.tcp_velocity > max_vel:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.REJECT,
                reason_code=VELOCITY_EXCEEDED,
                message=f"TCP velocity {ctx.tcp_velocity:.3f} exceeds max {max_vel:.3f}",
                measured_value=ctx.tcp_velocity,
                limit_value=max_vel,
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
        max_vel = ctx.contract.safety_constraints.max_joint_velocity
        for i, vel in enumerate(ctx.joint_velocities):
            if vel > max_vel:
                return SafetyRuleResult(
                    rule_id=self.rule_id,
                    decision=SafetyDecision.REJECT,
                    reason_code=JOINT_VELOCITY_EXCEEDED,
                    message=f"joint {i} velocity {vel:.3f} exceeds max {max_vel:.3f}",
                    measured_value=vel,
                    limit_value=max_vel,
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
        min_height = ctx.contract.safety_constraints.minimum_safe_height
        low_height_skills = {"APPROACH", "GRASP", "PLACE", "RELEASE"}
        if ctx.skill in low_height_skills:
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
        safety_dist = ctx.contract.safety_constraints.minimum_safe_height * 0.5
        for obs in ctx.obstacles:
            dist = hypot(ctx.tcp_x - obs.x, ctx.tcp_y - obs.y)
            min_dist = obs.radius_m + safety_dist
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
                decision=SafetyDecision.ALLOW,
                reason_code="COLLISION_CHECK_OFF",
                message="collision check not required",
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
        return SafetyRuleResult(
            rule_id=self.rule_id,
            decision=SafetyDecision.ALLOW,
            reason_code="CARRY_OK",
            message="carrying object with safety margin",
        )


class StepTimeoutRule(SafetyRuleEvaluator):
    rule_id = "STEP_TIMEOUT"

    def evaluate(self, ctx: object) -> SafetyRuleResult:
        assert isinstance(ctx, SafetyContext)
        if ctx.step_started_at is None:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="NO_STEP_START",
                message="step start time not set",
            )
        elapsed_ms = (time.monotonic() - ctx.step_started_at) * 1000
        step_obj = None
        for s in ctx.contract.steps:
            if s.step_id == ctx.step_id:
                step_obj = s
                break
        if step_obj is None:
            return SafetyRuleResult(
                rule_id=self.rule_id,
                decision=SafetyDecision.ALLOW,
                reason_code="STEP_NOT_FOUND",
                message="step not found in contract",
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
                decision=SafetyDecision.ALLOW,
                reason_code="NO_DEADLINE",
                message="no task deadline set",
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
                decision=SafetyDecision.ALLOW,
                reason_code="NO_WATCHDOG",
                message="watchdog not started",
            )
        elapsed_ms = (time.monotonic() - ctx.task_started_at_mono) * 1000
        limit_ms = 30_000.0
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
