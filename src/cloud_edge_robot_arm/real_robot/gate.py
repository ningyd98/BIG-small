"""硬件执行门控。

HardwareExecutionGate 是真实动作前的 fail-closed 边界；当前最高硬件等级为 NONE 时，
hardware_motion_authorized 必须保持 false。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.real_robot.config import ExecutionMode, RealRobotRuntimeSettings


class HardwareTelemetryStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_time: datetime
    monotonic_age_ms: int = Field(ge=0)
    max_allowed_age_ms: int = Field(gt=0)

    @property
    def fresh(self) -> bool:
        return self.monotonic_age_ms <= self.max_allowed_age_ms


class HardwareGateInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    controller_connected: bool
    emergency_stop_active: bool
    safety_shield_healthy: bool
    telemetry: HardwareTelemetryStatus | None
    requested_velocity_scale: float = Field(ge=0)
    requested_acceleration_scale: float = Field(ge=0)
    acceptance_level: str
    required_acceptance_level: str


class HardwareGateDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason_codes: list[str]
    execution_mode: str
    hardware_motion_authorized: bool
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class HardwareAuditEvent:
    event_type: str
    details: dict[str, object]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class HardwareExecutionGate:
    def __init__(self, *, settings: RealRobotRuntimeSettings) -> None:
        self._settings = settings
        self.audit_events: list[HardwareAuditEvent] = []

    @property
    def settings(self) -> RealRobotRuntimeSettings:
        return self._settings

    def evaluate(self, request: HardwareGateInput) -> HardwareGateDecision:
        reasons: list[str] = []
        if self._settings.execution_mode in {ExecutionMode.SIMULATION, ExecutionMode.DRY_RUN}:
            reasons.append("MOTION_NOT_AUTHORIZED_IN_NON_HARDWARE_MODE")
        if (
            self._settings.execution_mode
            in {
                ExecutionMode.HARDWARE_READ_ONLY,
                ExecutionMode.HARDWARE_LOW_SPEED,
                ExecutionMode.HARDWARE_OPERATIONAL,
            }
            and not self._settings.enable_real_robot
        ):
            reasons.append("ENABLE_REAL_ROBOT_FALSE")
        if self._settings.config is None and self._settings.execution_mode != ExecutionMode.DRY_RUN:
            reasons.append("REAL_ROBOT_CONFIG_MISSING")
        if not request.controller_connected:
            reasons.append("CONTROLLER_NOT_CONNECTED")
        if request.emergency_stop_active:
            reasons.append("EMERGENCY_STOP_ACTIVE")
        if not request.safety_shield_healthy:
            reasons.append("SAFETY_SHIELD_UNHEALTHY")
        if request.telemetry is None:
            reasons.append("TELEMETRY_MISSING")
        elif not request.telemetry.fresh:
            reasons.append("TELEMETRY_STALE")
        config = self._settings.config
        if config is not None:
            if request.requested_velocity_scale > config.velocity_scale:
                reasons.append("VELOCITY_SCALE_EXCEEDS_REAL_LIMIT")
            if request.requested_acceleration_scale > config.acceleration_scale:
                reasons.append("ACCELERATION_SCALE_EXCEEDS_REAL_LIMIT")
        if not (
            self._settings.operator_confirmation_token or self._settings.local_start_parameter
        ) and self._settings.execution_mode in {
            ExecutionMode.HARDWARE_LOW_SPEED,
            ExecutionMode.HARDWARE_OPERATIONAL,
        }:
            reasons.append("OPERATOR_CONFIRMATION_MISSING")
        if not _level_satisfies(request.acceptance_level, request.required_acceptance_level):
            reasons.append("ACCEPTANCE_LEVEL_INSUFFICIENT")

        allowed = not reasons and self._settings.execution_mode in {
            ExecutionMode.HARDWARE_LOW_SPEED,
            ExecutionMode.HARDWARE_OPERATIONAL,
        }
        decision = HardwareGateDecision(
            allowed=allowed,
            reason_codes=reasons,
            execution_mode=self._settings.execution_mode.value,
            hardware_motion_authorized=allowed,
        )
        self.audit_events.append(
            HardwareAuditEvent(
                event_type="HARDWARE_GATE_ALLOWED" if allowed else "HARDWARE_GATE_REJECTED",
                details={
                    "reason_codes": list(reasons),
                    "execution_mode": self._settings.execution_mode.value,
                    "hardware_motion_authorized": allowed,
                },
            )
        )
        return decision


def _level_satisfies(actual: str, required: str) -> bool:
    order = {
        "NONE": 0,
        "LEVEL_0": 1,
        "LEVEL_1": 2,
        "LEVEL_2": 3,
        "LEVEL_3": 4,
        "LEVEL_4": 5,
        "LEVEL_5": 6,
        "LEVEL_6": 7,
    }
    return order.get(actual, -1) >= order.get(required, 999)
