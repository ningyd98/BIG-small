from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.contracts import RobotState
from cloud_edge_robot_arm.edge.contract_validator import EdgeContractValidator
from cloud_edge_robot_arm.edge.safety.providers import TelemetrySample
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.real_robot.config import ExecutionMode, RealRobotRuntimeSettings
from cloud_edge_robot_arm.real_robot.planners import (
    MoveItDryRunPlanner,
    PlannerSafetyMargin,
    PlannerTrajectorySummary,
    SyntheticDryRunPlanner,
)


class TrajectorySummary(PlannerTrajectorySummary):
    pass


class SafetyMarginSummary(PlannerSafetyMargin):
    pass


class DryRunValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    validation_claimed: bool
    hardware_execution_status: str
    sent_to_hardware: bool
    trajectory_summary: TrajectorySummary
    safety_margin: SafetyMarginSummary
    planner_backend: str
    moveit_runtime_used: bool
    collision_validation_claimed: bool
    hardware_readiness_claimed: bool
    step_count: int
    audit_events: list[dict[str, object]]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DryRunValidationService:
    def __init__(
        self,
        *,
        shield: SafetyShield,
        runtime_settings: RealRobotRuntimeSettings,
        telemetry_sample: TelemetrySample,
        planner: MoveItDryRunPlanner | None = None,
    ) -> None:
        if runtime_settings.execution_mode != ExecutionMode.DRY_RUN:
            raise ValueError("DryRunValidationService requires DRY_RUN execution mode")
        self._shield = shield
        self._settings = runtime_settings
        self._telemetry = telemetry_sample
        self._planner: MoveItDryRunPlanner = planner or SyntheticDryRunPlanner()

    def validate(self, payload: dict[str, object]) -> DryRunValidationResult:
        accepted = EdgeContractValidator(min_plan_version=1).accept_payload(payload)
        if not accepted.accepted or accepted.contract is None:
            return self._rejected_result("CONTRACT_REJECTED")
        contract = accepted.contract
        robot_state = RobotState(connected=True, stopped=False, estop_engaged=False)
        safety_results: list[str] = []
        for step in contract.steps:
            ctx = self._shield.context_builder.build(
                contract=contract,
                step=step,
                robot_state=robot_state,
                scene_version=contract.scene_version,
                resolved_parameters=dict(step.parameters),
                scene_updated_at=datetime.now(UTC),
                telemetry_timestamp=self._telemetry.timestamp,
                step_started_at_mono=0.0,
                task_started_at_mono=0.0,
                monotonic_now=0.0,
                requested_velocity=self._telemetry.tcp_velocity,
                requested_joint_velocities=list(self._telemetry.joint_velocities),
                requested_acceleration=self._telemetry.acceleration,
                obstacles=[],
                forbidden_zones=[],
                wall_clock_now=datetime.now(UTC),
            )
            result = self._shield.pre_check(ctx)
            safety_results.append(result.decision.value)
            if not result.allowed:
                return self._rejected_result("SAFETY_REJECTED")

        plan_result = self._planner.plan_step(contract)
        return DryRunValidationResult(
            status="DRY_RUN_VALIDATED",
            validation_claimed=True,
            hardware_execution_status="PLANNED_ONLY",
            sent_to_hardware=False,
            trajectory_summary=TrajectorySummary.model_validate(
                plan_result.trajectory_summary.model_dump()
            ),
            safety_margin=SafetyMarginSummary.model_validate(
                plan_result.safety_margin.model_dump()
            ),
            planner_backend=plan_result.planner_backend,
            moveit_runtime_used=plan_result.moveit_runtime_used,
            collision_validation_claimed=plan_result.collision_validation_claimed,
            hardware_readiness_claimed=plan_result.hardware_readiness_claimed,
            step_count=len(contract.steps),
            audit_events=[
                {
                    "event_type": "DRY_RUN_VALIDATED",
                    "hardware_motion_observed": False,
                    "safety_decisions": safety_results,
                    "execution_mode": self._settings.execution_mode.value,
                    "planner_backend": plan_result.planner_backend,
                }
            ],
        )

    def _rejected_result(self, status: str) -> DryRunValidationResult:
        return DryRunValidationResult(
            status=status,
            validation_claimed=False,
            hardware_execution_status="PLANNED_ONLY",
            sent_to_hardware=False,
            trajectory_summary=TrajectorySummary(
                point_count=0,
                path_length_m=0.0,
                planning_time_ms=0,
                max_velocity_scale=0.0,
                max_acceleration_scale=0.0,
            ),
            safety_margin=SafetyMarginSummary(
                minimum_distance_m=0.0,
                workspace_margin_m=0.0,
                limiting_rule="REJECTED",
            ),
            planner_backend=getattr(self._planner, "planner_backend", "UNKNOWN"),
            moveit_runtime_used=False,
            collision_validation_claimed=False,
            hardware_readiness_claimed=False,
            step_count=0,
            audit_events=[
                {
                    "event_type": status,
                    "hardware_motion_observed": False,
                    "execution_mode": self._settings.execution_mode.value,
                }
            ],
        )
