from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.contracts import ActionResult, Pose
from cloud_edge_robot_arm.edge.robot_adapter import build_action_result


class ReadOnlyStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    ok: bool = False
    error_code: str = ""
    message: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JointStateReadout(ReadOnlyStatus):
    joint_names: list[str] = Field(default_factory=list)
    positions: list[float] = Field(default_factory=list)
    velocities: list[float] = Field(default_factory=list)


class TcpPoseReadout(ReadOnlyStatus):
    pose: Pose | None = None


class ControllerStateReadout(ReadOnlyStatus):
    controller_name: str = ""


class EmergencyStopReadout(ReadOnlyStatus):
    active: bool | None = None


class FaultStateReadout(ReadOnlyStatus):
    faulted: bool = False
    fault_codes: list[str] = Field(default_factory=list)


@runtime_checkable
class RealRobotReadOnlyAdapter(Protocol):
    def connect(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def disconnect(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def health(self) -> ReadOnlyStatus: ...

    def get_joint_state(self) -> JointStateReadout: ...

    def get_tcp_pose(self) -> TcpPoseReadout: ...

    def get_controller_state(self) -> ControllerStateReadout: ...

    def get_emergency_stop_state(self) -> EmergencyStopReadout: ...

    def get_fault_state(self) -> FaultStateReadout: ...


class EnvironmentBlockedRealRobotAdapter:
    def __init__(self, *, blocker: str) -> None:
        self._blocker = blocker

    def connect(self, *, timeout_ms: int | None = None) -> ActionResult:
        _ = timeout_ms
        return build_action_result(
            action_type="REAL_ROBOT_CONNECT",
            success=False,
            state_before={"status": "ENVIRONMENT_BLOCKED"},
            state_after={"status": "ENVIRONMENT_BLOCKED"},
            duration_ms=0,
            error_code="REAL_ROBOT_ENVIRONMENT_BLOCKED",
            error_message=self._blocker,
            details={"hardware_motion_observed": False},
        )

    def disconnect(self, *, timeout_ms: int | None = None) -> ActionResult:
        _ = timeout_ms
        return build_action_result(
            action_type="REAL_ROBOT_DISCONNECT",
            success=True,
            state_before={"status": "ENVIRONMENT_BLOCKED"},
            state_after={"status": "DISCONNECTED"},
            duration_ms=0,
            details={"hardware_motion_observed": False},
        )

    def health(self) -> ReadOnlyStatus:
        return ReadOnlyStatus(
            status="ENVIRONMENT_BLOCKED",
            ok=False,
            error_code="REAL_ROBOT_ENVIRONMENT_BLOCKED",
            message=self._blocker,
        )

    def get_joint_state(self) -> JointStateReadout:
        return JointStateReadout(
            status="ENVIRONMENT_BLOCKED",
            ok=False,
            error_code="REAL_ROBOT_ENVIRONMENT_BLOCKED",
            message=self._blocker,
        )

    def get_tcp_pose(self) -> TcpPoseReadout:
        return TcpPoseReadout(
            status="ENVIRONMENT_BLOCKED",
            ok=False,
            error_code="REAL_ROBOT_ENVIRONMENT_BLOCKED",
            message=self._blocker,
        )

    def get_controller_state(self) -> ControllerStateReadout:
        return ControllerStateReadout(
            status="ENVIRONMENT_BLOCKED",
            ok=False,
            error_code="REAL_ROBOT_ENVIRONMENT_BLOCKED",
            message=self._blocker,
        )

    def get_emergency_stop_state(self) -> EmergencyStopReadout:
        return EmergencyStopReadout(
            status="UNKNOWN",
            ok=False,
            error_code="REAL_ROBOT_ENVIRONMENT_BLOCKED",
            message=self._blocker,
            active=None,
        )

    def get_fault_state(self) -> FaultStateReadout:
        return FaultStateReadout(
            status="ENVIRONMENT_BLOCKED",
            ok=False,
            error_code="REAL_ROBOT_ENVIRONMENT_BLOCKED",
            message=self._blocker,
            faulted=True,
            fault_codes=["REAL_ROBOT_ENVIRONMENT_BLOCKED"],
        )
