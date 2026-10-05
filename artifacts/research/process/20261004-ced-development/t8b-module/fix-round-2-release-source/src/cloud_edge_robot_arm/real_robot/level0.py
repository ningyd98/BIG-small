"""Level 0 只读真实硬件框架。

Level 0 仅允许连接、断开和读取控制器/关节/TCP/e-stop/fault/mode/identity 状态。
任何可能产生位移的厂商 SDK 调用都不得出现在这里。
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cloud_edge_robot_arm.contracts import ActionResult
from cloud_edge_robot_arm.edge.robot_adapter import build_action_result

READ_ONLY_ALLOWED_METHODS = (
    "connect",
    "disconnect",
    "health",
    "get_robot_identity",
    "get_controller_state",
    "get_joint_state",
    "get_tcp_pose",
    "get_emergency_stop_state",
    "get_fault_state",
    "get_operation_mode",
)

FORBIDDEN_MOTION_METHODS = (
    "execute",
    "move",
    "command",
    "send_trajectory",
    "enable_controller",
    "servo_enable",
    "release_brake",
    "home",
    "safe_stop",
    "gripper_command",
)


class Level0Freshness(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class Level0ReadStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class Level0BaseReadout(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Level0ReadStatus = Level0ReadStatus.AVAILABLE
    ok: bool = True
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    monotonic_age_ms: int = Field(default=0, ge=0)
    max_allowed_age_ms: int = Field(default=500, gt=0)
    freshness: Level0Freshness = Level0Freshness.FRESH
    source: str = "fake_read_only"
    sample_sequence: int = Field(default=0, ge=0)
    raw_vendor_state: dict[str, Any] = Field(default_factory=dict)
    error_code: str = ""
    message: str = ""


class RobotIdentityReadout(Level0BaseReadout):
    vendor: str = ""
    model: str = ""
    controller_type: str = ""
    driver: str = ""
    firmware: str = ""
    robot_identity_hash: str = ""


class ControllerStateReadout(Level0BaseReadout):
    controller_state: str = "UNKNOWN"


class JointStateReadout(Level0BaseReadout):
    joint_names: list[str] = Field(default_factory=list)
    positions: list[float] = Field(default_factory=list)
    velocities: list[float] = Field(default_factory=list)

    @field_validator("positions", "velocities")
    @classmethod
    def values_must_be_finite(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) for value in values):
            raise ValueError("joint values must be finite")
        return values


class TcpPoseReadout(Level0BaseReadout):
    pose_xyzrpy: list[float] = Field(default_factory=list)

    @field_validator("pose_xyzrpy")
    @classmethod
    def pose_must_be_finite(cls, values: list[float]) -> list[float]:
        if any(not math.isfinite(value) for value in values):
            raise ValueError("tcp pose values must be finite")
        return values


class EmergencyStopReadout(Level0BaseReadout):
    state: Literal["ACTIVE", "INACTIVE", "UNKNOWN"] = "UNKNOWN"


class FaultStateReadout(Level0BaseReadout):
    state: Literal["FAULTED", "CLEAR", "UNKNOWN"] = "UNKNOWN"
    fault_codes: list[str] = Field(default_factory=list)


class OperationModeReadout(Level0BaseReadout):
    operation_mode: str = "UNKNOWN"


class ReadOnlyRobotAdapterProtocol(Protocol):
    def connect(self, *, timeout_ms: int | None = None) -> Any: ...

    def disconnect(self, *, timeout_ms: int | None = None) -> Any: ...

    def health(self, *, timeout_ms: int | None = None) -> Level0BaseReadout: ...

    def get_robot_identity(self, *, timeout_ms: int | None = None) -> RobotIdentityReadout: ...

    def get_controller_state(self, *, timeout_ms: int | None = None) -> ControllerStateReadout: ...

    def get_joint_state(self, *, timeout_ms: int | None = None) -> JointStateReadout: ...

    def get_tcp_pose(self, *, timeout_ms: int | None = None) -> TcpPoseReadout: ...

    def get_emergency_stop_state(
        self, *, timeout_ms: int | None = None
    ) -> EmergencyStopReadout: ...

    def get_fault_state(self, *, timeout_ms: int | None = None) -> FaultStateReadout: ...

    def get_operation_mode(self, *, timeout_ms: int | None = None) -> OperationModeReadout: ...


class SiteReadOnlySession(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)
    robot_identity_hash: str = Field(min_length=1)
    config_hash: str = Field(min_length=1)
    software_commit: str = Field(min_length=1)
    source_tree_hash: str = Field(min_length=1)
    operator_ids: list[str]
    safety_reviewer: str = Field(min_length=1)
    site_checklist: dict[str, bool] = Field(default_factory=dict)
    started_at: datetime
    expires_at: datetime
    isolated_workspace_confirmed: bool
    estop_reachable_confirmed: bool
    no_motion_mode_confirmed: bool
    physical_power_state: str = Field(min_length=1)
    notes: str = ""

    @field_validator("operator_ids")
    @classmethod
    def require_two_people(cls, values: list[str]) -> list[str]:
        if len(values) < 2:
            raise ValueError("site session requires at least two distinct operator ids")
        if len(set(values)) < 2:
            raise ValueError("site session requires at least two distinct operator ids")
        return values

    def is_valid(
        self,
        *,
        now: datetime,
        robot_identity_hash: str | None = None,
        config_hash: str | None = None,
    ) -> bool:
        if now >= self.expires_at:
            return False
        if robot_identity_hash is not None and robot_identity_hash != self.robot_identity_hash:
            return False
        if config_hash is not None and config_hash != self.config_hash:
            return False
        return (
            self.isolated_workspace_confirmed
            and self.estop_reachable_confirmed
            and self.no_motion_mode_confirmed
        )


class Level0AcceptanceInput(BaseModel):
    checks: dict[str, bool]
    evidence_complete: bool
    robot_identity_hash_matches: bool
    config_hash_matches: bool
    site_session_valid: bool
    safety_reviewer_approved: bool
    write_operation_count: int = Field(ge=0)
    hardware_motion_observed: bool
    worktree_clean: bool
    source_tree_hash_matches: bool


class Level0AcceptanceDecision(BaseModel):
    status: str
    highest_acceptance_level: str
    level1_allowed: bool = False
    blockers: list[str] = Field(default_factory=list)


class FakeReadOnlyAdapter:
    def __init__(self) -> None:
        self._connected = False
        self._sequence = 0
        self.write_operation_count = 0

    def connect(self, *, timeout_ms: int | None = None) -> ActionResult:
        _validate_timeout(timeout_ms)
        self._connected = True
        return build_action_result(
            action_type="REAL_ROBOT_READ_ONLY_CONNECT",
            success=True,
            state_before={"connected": False},
            state_after={"connected": True},
            duration_ms=0,
            details={"hardware_motion_observed": False},
        )

    def disconnect(self, *, timeout_ms: int | None = None) -> ActionResult:
        _validate_timeout(timeout_ms)
        was_connected = self._connected
        self._connected = False
        return build_action_result(
            action_type="REAL_ROBOT_READ_ONLY_DISCONNECT",
            success=True,
            state_before={"connected": was_connected},
            state_after={"connected": False},
            duration_ms=0,
            details={"hardware_motion_observed": False},
        )

    def health(self, *, timeout_ms: int | None = None) -> Level0BaseReadout:
        _validate_timeout(timeout_ms)
        if not self._connected:
            return unavailable_readout("read-only adapter is disconnected")
        return self._base(raw_vendor_state={"health": "OK"})

    def get_robot_identity(self, *, timeout_ms: int | None = None) -> RobotIdentityReadout:
        _validate_timeout(timeout_ms)
        if not self._connected:
            return RobotIdentityReadout(**_unavailable_payload("read-only adapter is disconnected"))
        payload: dict[str, object] = {
            "vendor": "FAKE_VENDOR",
            "model": "FAKE_LEVEL0_ARM",
            "controller_type": "FAKE_READ_ONLY_CONTROLLER",
            "driver": "fake-readonly-driver",
            "firmware": "fake-fw-0",
        }
        return RobotIdentityReadout(
            **self._base_payload(raw_vendor_state=payload),
            vendor=str(payload["vendor"]),
            model=str(payload["model"]),
            controller_type=str(payload["controller_type"]),
            driver=str(payload["driver"]),
            firmware=str(payload["firmware"]),
            robot_identity_hash=robot_identity_hash(payload),
        )

    def get_controller_state(self, *, timeout_ms: int | None = None) -> ControllerStateReadout:
        _validate_timeout(timeout_ms)
        if not self._connected:
            return ControllerStateReadout(
                **_unavailable_payload("read-only adapter is disconnected")
            )
        return ControllerStateReadout(
            **self._base_payload(raw_vendor_state={"controller_state": "READ_ONLY"}),
            controller_state="READ_ONLY",
        )

    def get_joint_state(self, *, timeout_ms: int | None = None) -> JointStateReadout:
        _validate_timeout(timeout_ms)
        if not self._connected:
            return JointStateReadout(**_unavailable_payload("read-only adapter is disconnected"))
        return JointStateReadout(
            **self._base_payload(raw_vendor_state={"joint_state": "sampled"}),
            joint_names=[f"joint_{index}" for index in range(1, 7)],
            positions=[0.0, 0.1, -0.1, 0.2, -0.2, 0.0],
            velocities=[0.0] * 6,
        )

    def get_tcp_pose(self, *, timeout_ms: int | None = None) -> TcpPoseReadout:
        _validate_timeout(timeout_ms)
        if not self._connected:
            return TcpPoseReadout(**_unavailable_payload("read-only adapter is disconnected"))
        return TcpPoseReadout(
            **self._base_payload(raw_vendor_state={"tcp_pose": "sampled"}),
            pose_xyzrpy=[0.3, 0.0, 0.2, 0.0, 1.57, 0.0],
        )

    def get_emergency_stop_state(self, *, timeout_ms: int | None = None) -> EmergencyStopReadout:
        _validate_timeout(timeout_ms)
        if not self._connected:
            return EmergencyStopReadout(**_unavailable_payload("read-only adapter is disconnected"))
        return EmergencyStopReadout(
            **self._base_payload(raw_vendor_state={"estop": "INACTIVE"}),
            state="INACTIVE",
        )

    def get_fault_state(self, *, timeout_ms: int | None = None) -> FaultStateReadout:
        _validate_timeout(timeout_ms)
        if not self._connected:
            return FaultStateReadout(**_unavailable_payload("read-only adapter is disconnected"))
        return FaultStateReadout(
            **self._base_payload(raw_vendor_state={"fault": "CLEAR"}),
            state="CLEAR",
            fault_codes=[],
        )

    def get_operation_mode(self, *, timeout_ms: int | None = None) -> OperationModeReadout:
        _validate_timeout(timeout_ms)
        if not self._connected:
            return OperationModeReadout(**_unavailable_payload("read-only adapter is disconnected"))
        return OperationModeReadout(
            **self._base_payload(raw_vendor_state={"operation_mode": "READ_ONLY"}),
            operation_mode="READ_ONLY",
        )

    def _base(self, *, raw_vendor_state: dict[str, Any]) -> Level0BaseReadout:
        return Level0BaseReadout(**self._base_payload(raw_vendor_state=raw_vendor_state))

    def _base_payload(self, *, raw_vendor_state: dict[str, Any]) -> dict[str, Any]:
        self._sequence += 1
        return {
            "status": Level0ReadStatus.AVAILABLE,
            "ok": self._connected,
            "timestamp": datetime.now(UTC),
            "monotonic_age_ms": 0,
            "max_allowed_age_ms": 500,
            "freshness": Level0Freshness.FRESH,
            "source": "fake_read_only",
            "sample_sequence": self._sequence,
            "raw_vendor_state": dict(raw_vendor_state),
        }


class VendorRealRobotReadOnlyAdapter:
    """Base placeholder for site-specific read-only SDK bindings.

    Production deployments must subclass this and only map confirmed read-only SDK calls.
    """

    write_operation_count = 0

    def connect(self, *, timeout_ms: int | None = None) -> Any:
        _validate_timeout(timeout_ms)
        raise NotImplementedError("site-specific read-only controller binding is not configured")

    def disconnect(self, *, timeout_ms: int | None = None) -> Any:
        _validate_timeout(timeout_ms)
        raise NotImplementedError("site-specific read-only controller binding is not configured")

    def health(self, *, timeout_ms: int | None = None) -> Level0BaseReadout:
        _validate_timeout(timeout_ms)
        return unavailable_readout("site-specific read-only controller binding is not configured")

    def get_robot_identity(self, *, timeout_ms: int | None = None) -> RobotIdentityReadout:
        _validate_timeout(timeout_ms)
        return RobotIdentityReadout(
            **unavailable_readout(
                "site-specific read-only controller binding is not configured"
            ).model_dump()
        )

    def get_controller_state(self, *, timeout_ms: int | None = None) -> ControllerStateReadout:
        _validate_timeout(timeout_ms)
        return ControllerStateReadout(
            **unavailable_readout(
                "site-specific read-only controller binding is not configured"
            ).model_dump()
        )

    def get_joint_state(self, *, timeout_ms: int | None = None) -> JointStateReadout:
        _validate_timeout(timeout_ms)
        return JointStateReadout(
            **unavailable_readout(
                "site-specific read-only controller binding is not configured"
            ).model_dump()
        )

    def get_tcp_pose(self, *, timeout_ms: int | None = None) -> TcpPoseReadout:
        _validate_timeout(timeout_ms)
        return TcpPoseReadout(
            **unavailable_readout(
                "site-specific read-only controller binding is not configured"
            ).model_dump()
        )

    def get_emergency_stop_state(self, *, timeout_ms: int | None = None) -> EmergencyStopReadout:
        _validate_timeout(timeout_ms)
        return EmergencyStopReadout(
            **unavailable_readout(
                "site-specific read-only controller binding is not configured"
            ).model_dump()
        )

    def get_fault_state(self, *, timeout_ms: int | None = None) -> FaultStateReadout:
        _validate_timeout(timeout_ms)
        return FaultStateReadout(
            **unavailable_readout(
                "site-specific read-only controller binding is not configured"
            ).model_dump()
        )

    def get_operation_mode(self, *, timeout_ms: int | None = None) -> OperationModeReadout:
        _validate_timeout(timeout_ms)
        return OperationModeReadout(
            **unavailable_readout(
                "site-specific read-only controller binding is not configured"
            ).model_dump()
        )


def robot_identity_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def evaluate_level0_acceptance(input_payload: Level0AcceptanceInput) -> Level0AcceptanceDecision:
    blockers: list[str] = []
    required_checks = {f"L0-{index:02d}" for index in range(1, 21)}
    passed_checks = {key for key, passed in input_payload.checks.items() if passed}
    missing = sorted(required_checks - passed_checks)
    if missing:
        blockers.append("missing level0 checks: " + ",".join(missing))
    if not input_payload.evidence_complete:
        blockers.append("evidence incomplete")
    if not input_payload.robot_identity_hash_matches:
        blockers.append("robot identity hash mismatch")
    if not input_payload.config_hash_matches:
        blockers.append("config hash mismatch")
    if not input_payload.site_session_valid:
        blockers.append("site session invalid")
    if not input_payload.safety_reviewer_approved:
        blockers.append("safety reviewer approval missing")
    if input_payload.write_operation_count != 0:
        blockers.append("write operation count is not zero")
    if input_payload.hardware_motion_observed:
        blockers.append("hardware motion observed")
    if not input_payload.worktree_clean:
        blockers.append("worktree is not clean")
    if not input_payload.source_tree_hash_matches:
        blockers.append("source tree hash mismatch")
    if blockers:
        return Level0AcceptanceDecision(
            status="PHASE10_LEVEL0_REJECTED",
            highest_acceptance_level="NONE",
            blockers=blockers,
        )
    return Level0AcceptanceDecision(
        status="PHASE10_HARDWARE_READ_ONLY_ACCEPTED",
        highest_acceptance_level="LEVEL_0",
        level1_allowed=False,
    )


def unavailable_readout(message: str) -> Level0BaseReadout:
    return Level0BaseReadout(
        status=Level0ReadStatus.UNAVAILABLE,
        ok=False,
        freshness=Level0Freshness.UNAVAILABLE,
        source="hardware_read_only",
        error_code="LEVEL0_UNAVAILABLE",
        message=message,
    )


def is_fresh_readout(readout: Level0BaseReadout) -> bool:
    return (
        readout.ok
        and readout.status == Level0ReadStatus.AVAILABLE
        and readout.freshness == Level0Freshness.FRESH
        and readout.monotonic_age_ms <= readout.max_allowed_age_ms
    )


def emergency_stop_is_inactive(readout: EmergencyStopReadout) -> bool:
    return is_fresh_readout(readout) and readout.state == "INACTIVE"


def _unavailable_payload(message: str) -> dict[str, Any]:
    return unavailable_readout(message).model_dump()


def _validate_timeout(timeout_ms: int | None) -> None:
    if timeout_ms is not None and timeout_ms <= 0:
        raise TimeoutError("timeout_ms must be positive")
    if timeout_ms is not None:
        time.sleep(0)
