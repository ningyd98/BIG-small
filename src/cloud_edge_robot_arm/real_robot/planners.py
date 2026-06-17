from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.contracts import Pose, TaskContract


class PlannerTrajectorySummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    point_count: int = Field(ge=0)
    path_length_m: float = Field(ge=0)
    planning_time_ms: int = Field(ge=0)
    max_velocity_scale: float = Field(ge=0)
    max_acceleration_scale: float = Field(ge=0)
    joint_trajectory: list[dict[str, object]] = Field(default_factory=list)


class PlannerSafetyMargin(BaseModel):
    model_config = ConfigDict(frozen=True)

    minimum_distance_m: float = Field(ge=0)
    workspace_margin_m: float = Field(ge=0)
    limiting_rule: str


class DryRunPlanResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    planner_backend: str
    moveit_runtime_used: bool
    collision_validation_claimed: bool
    hardware_readiness_claimed: bool
    trajectory_summary: PlannerTrajectorySummary
    safety_margin: PlannerSafetyMargin
    joint_limits_valid: bool
    robot_model_valid: bool
    planning_group_valid: bool


@runtime_checkable
class MoveItDryRunPlanner(Protocol):
    def validate_robot_model(self, contract: TaskContract) -> bool: ...

    def validate_planning_group(self, contract: TaskContract) -> bool: ...

    def load_planning_scene(self, contract: TaskContract) -> dict[str, object]: ...

    def plan_step(self, contract: TaskContract) -> DryRunPlanResult: ...

    def compute_trajectory_summary(self, contract: TaskContract) -> PlannerTrajectorySummary: ...

    def compute_collision_clearance(self, contract: TaskContract) -> PlannerSafetyMargin: ...

    def validate_joint_limits(self, contract: TaskContract) -> bool: ...


class SyntheticDryRunPlanner:
    planner_backend = "SYNTHETIC"

    def validate_robot_model(self, contract: TaskContract) -> bool:
        _ = contract
        return True

    def validate_planning_group(self, contract: TaskContract) -> bool:
        _ = contract
        return True

    def load_planning_scene(self, contract: TaskContract) -> dict[str, object]:
        return {
            "scene_source": "synthetic",
            "step_count": len(contract.steps),
            "collision_validation_claimed": False,
        }

    def plan_step(self, contract: TaskContract) -> DryRunPlanResult:
        return DryRunPlanResult(
            planner_backend=self.planner_backend,
            moveit_runtime_used=False,
            collision_validation_claimed=False,
            hardware_readiness_claimed=False,
            trajectory_summary=self.compute_trajectory_summary(contract),
            safety_margin=self.compute_collision_clearance(contract),
            joint_limits_valid=self.validate_joint_limits(contract),
            robot_model_valid=self.validate_robot_model(contract),
            planning_group_valid=self.validate_planning_group(contract),
        )

    def compute_trajectory_summary(self, contract: TaskContract) -> PlannerTrajectorySummary:
        poses = [_target_pose_for_step(index) for index, _ in enumerate(contract.steps)]
        path_length = sum(
            poses[index].distance_xy_to(poses[index - 1]) for index in range(1, len(poses))
        )
        return PlannerTrajectorySummary(
            point_count=max(1, len(contract.steps)),
            path_length_m=round(path_length, 6),
            planning_time_ms=max(1, len(contract.steps) * 3),
            max_velocity_scale=0.05,
            max_acceleration_scale=0.05,
            joint_trajectory=[],
        )

    def compute_collision_clearance(self, contract: TaskContract) -> PlannerSafetyMargin:
        _ = contract
        return PlannerSafetyMargin(
            minimum_distance_m=0.0,
            workspace_margin_m=0.0,
            limiting_rule="SYNTHETIC_NOT_COLLISION_VALIDATED",
        )

    def validate_joint_limits(self, contract: TaskContract) -> bool:
        _ = contract
        return True


class MoveItRuntimeDryRunPlanner:
    planner_backend = "MOVEIT_RUNTIME"

    def __init__(self, *, evidence: dict[str, object]) -> None:
        self._evidence = evidence

    def validate_robot_model(self, contract: TaskContract) -> bool:
        _ = contract
        return bool(self._evidence.get("robot_model_valid", True))

    def validate_planning_group(self, contract: TaskContract) -> bool:
        _ = contract
        return bool(self._evidence.get("planning_group_valid", True))

    def load_planning_scene(self, contract: TaskContract) -> dict[str, object]:
        _ = contract
        scene = self._evidence.get("planning_scene")
        return scene if isinstance(scene, dict) else {"scene_source": "moveit_runtime"}

    def plan_step(self, contract: TaskContract) -> DryRunPlanResult:
        return DryRunPlanResult(
            planner_backend=self.planner_backend,
            moveit_runtime_used=True,
            collision_validation_claimed=True,
            hardware_readiness_claimed=False,
            trajectory_summary=self.compute_trajectory_summary(contract),
            safety_margin=self.compute_collision_clearance(contract),
            joint_limits_valid=self.validate_joint_limits(contract),
            robot_model_valid=self.validate_robot_model(contract),
            planning_group_valid=self.validate_planning_group(contract),
        )

    def compute_trajectory_summary(self, contract: TaskContract) -> PlannerTrajectorySummary:
        _ = contract
        trajectory = self._evidence.get("trajectory_summary")
        if isinstance(trajectory, dict):
            return PlannerTrajectorySummary.model_validate(trajectory)
        return PlannerTrajectorySummary(
            point_count=0,
            path_length_m=0.0,
            planning_time_ms=0,
            max_velocity_scale=0.0,
            max_acceleration_scale=0.0,
        )

    def compute_collision_clearance(self, contract: TaskContract) -> PlannerSafetyMargin:
        _ = contract
        margin = self._evidence.get("safety_margin")
        if isinstance(margin, dict):
            return PlannerSafetyMargin.model_validate(margin)
        return PlannerSafetyMargin(
            minimum_distance_m=0.0,
            workspace_margin_m=0.0,
            limiting_rule="MOVEIT_EVIDENCE_MISSING",
        )

    def validate_joint_limits(self, contract: TaskContract) -> bool:
        _ = contract
        return bool(self._evidence.get("joint_limits_valid", False))


def _target_pose_for_step(index: int) -> Pose:
    return Pose(x=0.05 * index, y=0.0, z=0.18)
