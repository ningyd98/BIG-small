from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from cloud_edge_robot_arm.contracts import Pose, RobotState, TaskContract, TaskStep
from cloud_edge_robot_arm.edge.safety.providers import TelemetrySample

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

SKILLS_WITH_TARGET = {
    "HOME",
    "MOVE_ABOVE",
    "APPROACH",
    "LIFT",
    "MOVE_TO_REGION",
    "PLACE",
    "RETREAT",
}


class TargetPoseResolver(Protocol):
    """Single authority for resolving a skill's target pose from the live scene.

    The robot adapter implements this so the safety shield and the executed
    motion share the *same* resolved target (no separate computation).
    """

    def resolve_target_pose(self, skill: str, parameters: dict[str, Any]) -> Pose | None: ...


@dataclass(frozen=True)
class SafetyExecutionIntent:
    skill: str
    current_pose: Pose
    target_pose: Pose | None
    path_start: Pose
    path_end: Pose
    requested_tcp_velocity: float
    requested_joint_velocity: float
    requested_acceleration: float
    holding_object: bool
    payload_envelope: dict[str, Any] = field(default_factory=dict)
    resolved_parameters: dict[str, Any] = field(default_factory=dict)
    resolvable: bool = True
    unresolved_reason: str | None = None


class SkillSafetyIntentResolver:
    """Resolve a high-level skill into an explicit, checkable execution intent."""

    def __init__(self, target_resolver: TargetPoseResolver) -> None:
        self._target_resolver = target_resolver

    def resolve(
        self,
        *,
        contract: TaskContract,
        step: TaskStep,
        robot_state: RobotState,
        telemetry: TelemetrySample | None,
    ) -> SafetyExecutionIntent:
        skill = step.skill.value
        params = dict(step.parameters)
        current = robot_state.tcp_pose
        holding = robot_state.holding_object_id is not None

        target: Pose | None = None
        resolvable = True
        unresolved_reason: str | None = None
        if skill in SKILLS_WITH_TARGET:
            target = self._target_resolver.resolve_target_pose(skill, params)
            if target is None:
                resolvable = False
                unresolved_reason = f"could not resolve target pose for skill {skill}"

        tcp_velocity, tcp_source = self._resolve_tcp_velocity(contract, params, telemetry)
        joint_velocity, joint_source = self._resolve_joint_velocity(contract, params, telemetry)
        acceleration, accel_source = self._resolve_acceleration(contract, params, telemetry)

        path_start = current
        path_end = target if target is not None else current

        resolved_parameters = dict(params)
        if target is not None:
            resolved_parameters["target_pose"] = {
                "x": target.x,
                "y": target.y,
                "z": target.z,
            }
        resolved_parameters["tcp_velocity"] = tcp_velocity
        resolved_parameters["acceleration"] = acceleration

        payload_envelope = {
            "tcp_velocity_source": tcp_source,
            "joint_velocity_source": joint_source,
            "acceleration_source": accel_source,
            "holding_object": holding,
            "object_id": robot_state.holding_object_id,
        }

        return SafetyExecutionIntent(
            skill=skill,
            current_pose=current,
            target_pose=target,
            path_start=path_start,
            path_end=path_end,
            requested_tcp_velocity=tcp_velocity,
            requested_joint_velocity=joint_velocity,
            requested_acceleration=acceleration,
            holding_object=holding,
            payload_envelope=payload_envelope,
            resolved_parameters=resolved_parameters,
            resolvable=resolvable,
            unresolved_reason=unresolved_reason,
        )

    def _resolve_tcp_velocity(
        self,
        contract: TaskContract,
        params: dict[str, Any],
        telemetry: TelemetrySample | None,
    ) -> tuple[float, str]:
        explicit = params.get("tcp_velocity")
        if isinstance(explicit, int | float) and explicit > 0:
            return float(explicit), "skill_parameter"
        if telemetry is not None and telemetry.tcp_velocity > 0:
            return telemetry.tcp_velocity, "telemetry"
        # conservative local default: the contract's commanded maximum.
        return contract.safety_constraints.max_tcp_velocity, "contract_default"

    def _resolve_joint_velocity(
        self,
        contract: TaskContract,
        params: dict[str, Any],
        telemetry: TelemetrySample | None,
    ) -> tuple[float, str]:
        explicit = params.get("joint_velocity")
        if isinstance(explicit, int | float) and explicit > 0:
            return float(explicit), "skill_parameter"
        if telemetry is not None and telemetry.joint_velocities:
            return max(telemetry.joint_velocities), "telemetry"
        return contract.safety_constraints.max_joint_velocity, "contract_default"

    def _resolve_acceleration(
        self,
        contract: TaskContract,
        params: dict[str, Any],
        telemetry: TelemetrySample | None,
    ) -> tuple[float, str]:
        explicit = params.get("acceleration")
        if isinstance(explicit, int | float) and explicit > 0:
            return float(explicit), "skill_parameter"
        if telemetry is not None and telemetry.acceleration > 0:
            return telemetry.acceleration, "telemetry"
        # conservative default proportional to the commanded tcp velocity budget.
        return contract.safety_constraints.max_tcp_velocity, "contract_default"
