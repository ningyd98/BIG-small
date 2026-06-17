from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.contracts import Pose, RobotState, TaskContract
from cloud_edge_robot_arm.edge.contract_validator import EdgeContractValidator
from cloud_edge_robot_arm.edge.safety.providers import TelemetrySample
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield
from cloud_edge_robot_arm.real_robot.config import ExecutionMode, RealRobotRuntimeSettings


class TrajectorySummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    point_count: int
    path_length_m: float
    planning_time_ms: int
    max_velocity_scale: float
    max_acceleration_scale: float


class SafetyMarginSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    minimum_distance_m: float
    workspace_margin_m: float
    limiting_rule: str


class DryRunValidationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    validation_claimed: bool
    hardware_execution_status: str
    sent_to_hardware: bool
    trajectory_summary: TrajectorySummary
    safety_margin: SafetyMarginSummary
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
    ) -> None:
        if runtime_settings.execution_mode != ExecutionMode.DRY_RUN:
            raise ValueError("DryRunValidationService requires DRY_RUN execution mode")
        self._shield = shield
        self._settings = runtime_settings
        self._telemetry = telemetry_sample

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

        trajectory = self._trajectory_summary(contract)
        return DryRunValidationResult(
            status="DRY_RUN_VALIDATED",
            validation_claimed=True,
            hardware_execution_status="PLANNED_ONLY",
            sent_to_hardware=False,
            trajectory_summary=trajectory,
            safety_margin=SafetyMarginSummary(
                minimum_distance_m=0.05,
                workspace_margin_m=0.05,
                limiting_rule="SUMMARY",
            ),
            step_count=len(contract.steps),
            audit_events=[
                {
                    "event_type": "DRY_RUN_VALIDATED",
                    "hardware_motion_observed": False,
                    "safety_decisions": safety_results,
                    "execution_mode": self._settings.execution_mode.value,
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
            step_count=0,
            audit_events=[
                {
                    "event_type": status,
                    "hardware_motion_observed": False,
                    "execution_mode": self._settings.execution_mode.value,
                }
            ],
        )

    def _trajectory_summary(self, contract: TaskContract) -> TrajectorySummary:
        poses = [_target_pose_for_step(index) for index, _ in enumerate(contract.steps)]
        path_length = sum(
            poses[index].distance_xy_to(poses[index - 1]) for index in range(1, len(poses))
        )
        return TrajectorySummary(
            point_count=max(1, len(contract.steps)),
            path_length_m=round(path_length, 6),
            planning_time_ms=max(1, len(contract.steps) * 3),
            max_velocity_scale=0.05,
            max_acceleration_scale=0.05,
        )


def _target_pose_for_step(index: int) -> Pose:
    return Pose(x=0.05 * index, y=0.0, z=0.18)
