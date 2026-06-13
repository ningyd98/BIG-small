from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.edge.safety.models import HardSafetyLimits, Obstacle, WorkspaceDefinition


class OperationalSafetyPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str = "1.0.0"
    max_tcp_velocity: float | None = Field(default=None, gt=0)
    max_joint_velocity: float | None = Field(default=None, gt=0)
    max_acceleration: float | None = Field(default=None, gt=0)
    minimum_safe_height: float | None = Field(default=None, ge=0)
    workspace: WorkspaceDefinition | None = None
    max_reach_m: float | None = Field(default=None, gt=0)
    obstacle_safety_distance: float | None = Field(default=None, ge=0)
    carry_safety_margin: float | None = Field(default=None, ge=0)
    obstacles: list[Obstacle] = Field(default_factory=list)
    forbidden_zones: list[WorkspaceDefinition] = Field(default_factory=list)
    step_timeout_safety_margin_ms: int | None = Field(default=None, ge=0)
    task_deadline_safety_margin_ms: int | None = Field(default=None, ge=0)
    scene_staleness_ms: int | None = Field(default=None, ge=0)
    telemetry_staleness_ms: int | None = Field(default=None, ge=0)
    command_ttl_ms: int | None = Field(default=None, gt=0)
    watchdog_timeout_ms: int | None = Field(default=None, gt=0)
    low_height_exception_skills: frozenset[str] | None = None


@dataclass(frozen=True)
class MergedSafetyConstraints:
    max_tcp_velocity: float
    max_joint_velocity: float
    max_acceleration: float
    minimum_safe_height: float
    workspace: WorkspaceDefinition
    max_reach_m: float
    obstacle_safety_distance: float
    carry_safety_margin: float
    obstacles: list[Obstacle]
    forbidden_zones: list[WorkspaceDefinition]
    step_timeout_safety_margin_ms: int
    task_deadline_safety_margin_ms: int
    scene_staleness_ms: int
    telemetry_staleness_ms: int
    command_ttl_ms: int
    watchdog_timeout_ms: int
    low_height_exception_skills: frozenset[str]


def merge_constraints(
    hard: HardSafetyLimits,
    operational: OperationalSafetyPolicy,
    contract_limits: dict[str, Any] | None = None,
    device_limits: dict[str, Any] | None = None,
) -> MergedSafetyConstraints:
    """Effective limits = min(hard, operational, contract, device)."""
    cl = contract_limits or {}
    dl = device_limits or {}

    def _min_float(
        hard_val: float,
        op_val: float | None,
        contract_val: Any,
        device_val: Any,
    ) -> float:
        candidates = [hard_val]
        if op_val is not None:
            candidates.append(op_val)
        if isinstance(contract_val, (int, float)) and contract_val > 0:
            candidates.append(float(contract_val))
        if isinstance(device_val, (int, float)) and device_val > 0:
            candidates.append(float(device_val))
        return min(candidates)

    def _min_int(
        hard_val: int,
        op_val: int | None,
        contract_val: Any,
        device_val: Any,
    ) -> int:
        candidates = [hard_val]
        if op_val is not None:
            candidates.append(op_val)
        if isinstance(contract_val, int) and contract_val > 0:
            candidates.append(contract_val)
        if isinstance(device_val, int) and device_val > 0:
            candidates.append(device_val)
        return min(candidates)

    if operational.workspace is not None:
        workspace_def = WorkspaceDefinition(
            workspace_id=operational.workspace.workspace_id,
            x_min=max(hard.workspace_x_min, operational.workspace.x_min),
            x_max=min(hard.workspace_x_max, operational.workspace.x_max),
            y_min=max(hard.workspace_y_min, operational.workspace.y_min),
            y_max=min(hard.workspace_y_max, operational.workspace.y_max),
            z_min=max(hard.workspace_z_min, operational.workspace.z_min),
            z_max=min(hard.workspace_z_max, operational.workspace.z_max),
        )
    else:
        workspace_def = WorkspaceDefinition(
            workspace_id="default",
            x_min=hard.workspace_x_min,
            x_max=hard.workspace_x_max,
            y_min=hard.workspace_y_min,
            y_max=hard.workspace_y_max,
            z_min=hard.workspace_z_min,
            z_max=hard.workspace_z_max,
        )

    op_lhes = operational.low_height_exception_skills
    hard_lhes = hard.low_height_exception_skills
    lhes = op_lhes if op_lhes is not None else hard_lhes

    obstacles = operational.obstacles if operational.obstacles else []
    forbidden = operational.forbidden_zones if operational.forbidden_zones else []

    return MergedSafetyConstraints(
        max_tcp_velocity=_min_float(
            hard.max_tcp_velocity,
            operational.max_tcp_velocity,
            cl.get("max_tcp_velocity"),
            dl.get("max_tcp_velocity"),
        ),
        max_joint_velocity=_min_float(
            hard.max_joint_velocity,
            operational.max_joint_velocity,
            cl.get("max_joint_velocity"),
            dl.get("max_joint_velocity"),
        ),
        max_acceleration=_min_float(
            hard.max_acceleration,
            operational.max_acceleration,
            cl.get("max_acceleration"),
            dl.get("max_acceleration"),
        ),
        minimum_safe_height=_min_float(
            hard.minimum_safe_height,
            operational.minimum_safe_height,
            cl.get("minimum_safe_height"),
            dl.get("minimum_safe_height"),
        ),
        workspace=workspace_def,
        max_reach_m=_min_float(
            hard.max_reach_m,
            operational.max_reach_m,
            cl.get("max_reach_m"),
            dl.get("max_reach_m"),
        ),
        obstacle_safety_distance=_min_float(
            hard.obstacle_safety_distance,
            operational.obstacle_safety_distance,
            cl.get("obstacle_safety_distance"),
            dl.get("obstacle_safety_distance"),
        ),
        carry_safety_margin=_min_float(
            hard.carry_safety_margin,
            operational.carry_safety_margin,
            cl.get("carry_safety_margin"),
            dl.get("carry_safety_margin"),
        ),
        obstacles=obstacles,
        forbidden_zones=forbidden,
        step_timeout_safety_margin_ms=_min_int(
            hard.step_timeout_safety_margin_ms,
            operational.step_timeout_safety_margin_ms,
            cl.get("step_timeout_safety_margin_ms"),
            dl.get("step_timeout_safety_margin_ms"),
        ),
        task_deadline_safety_margin_ms=_min_int(
            hard.task_deadline_safety_margin_ms,
            operational.task_deadline_safety_margin_ms,
            cl.get("task_deadline_safety_margin_ms"),
            dl.get("task_deadline_safety_margin_ms"),
        ),
        scene_staleness_ms=_min_int(
            hard.scene_staleness_ms,
            operational.scene_staleness_ms,
            cl.get("scene_staleness_ms"),
            dl.get("scene_staleness_ms"),
        ),
        telemetry_staleness_ms=_min_int(
            hard.telemetry_staleness_ms,
            operational.telemetry_staleness_ms,
            cl.get("telemetry_staleness_ms"),
            dl.get("telemetry_staleness_ms"),
        ),
        command_ttl_ms=_min_int(
            hard.command_ttl_ms,
            operational.command_ttl_ms,
            cl.get("command_ttl_ms"),
            dl.get("command_ttl_ms"),
        ),
        watchdog_timeout_ms=_min_int(
            hard.watchdog_timeout_ms,
            operational.watchdog_timeout_ms,
            cl.get("watchdog_timeout_ms"),
            dl.get("watchdog_timeout_ms"),
        ),
        low_height_exception_skills=lhes,
    )
