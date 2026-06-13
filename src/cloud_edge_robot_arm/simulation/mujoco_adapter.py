from __future__ import annotations

from importlib.util import find_spec

from cloud_edge_robot_arm.contracts import ActionResult, Pose, RobotState
from cloud_edge_robot_arm.edge.robot_adapter import build_action_result


class MuJoCoRobotAdapter:
    """Phase 1 simulation adapter with explicit dependency guidance."""

    def __init__(self) -> None:
        self._connected = False
        self._state = RobotState(connected=False)

    def connect(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        duration = min(10, timeout_ms or 1_000)
        if find_spec("mujoco") is None:
            after = self._snapshot()
            return build_action_result(
                action_type="CONNECT",
                success=False,
                state_before=before,
                state_after=after,
                duration_ms=duration,
                error_code="MUJOCO_NOT_INSTALLED",
                error_message=(
                    "MuJoCo is not installed. Install with: python -m pip install -e '.[sim]'"
                ),
            )
        self._connected = True
        self._state.connected = True
        return build_action_result(
            action_type="CONNECT",
            success=True,
            state_before=before,
            state_after=self._snapshot(),
            duration_ms=duration,
        )

    def disconnect(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._connected = False
        self._state.connected = False
        return build_action_result(
            action_type="DISCONNECT",
            success=True,
            state_before=before,
            state_after=self._snapshot(),
            duration_ms=min(10, timeout_ms or 1_000),
        )

    def home(self, *, timeout_ms: int | None = None) -> ActionResult:
        return self.move_to_pose(Pose(x=0.0, y=-0.2, z=0.18), timeout_ms=timeout_ms)

    def move_to_pose(self, pose: Pose, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        duration = min(10, timeout_ms or 1_000)
        if not self._connected:
            return build_action_result(
                action_type="MOVE_TO_POSE",
                success=False,
                state_before=before,
                state_after=self._snapshot(),
                duration_ms=duration,
                error_code="ROBOT_DISCONNECTED",
                error_message="MuJoCo adapter is not connected",
            )
        self._state.tcp_pose = pose
        return build_action_result(
            action_type="MOVE_TO_POSE",
            success=True,
            state_before=before,
            state_after=self._snapshot(),
            duration_ms=duration,
        )

    def open_gripper(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._state.gripper_open = True
        return build_action_result(
            action_type="OPEN_GRIPPER",
            success=True,
            state_before=before,
            state_after=self._snapshot(),
            duration_ms=min(10, timeout_ms or 1_000),
        )

    def close_gripper(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._state.gripper_open = False
        return build_action_result(
            action_type="CLOSE_GRIPPER",
            success=True,
            state_before=before,
            state_after=self._snapshot(),
            duration_ms=min(10, timeout_ms or 1_000),
        )

    def get_state(self) -> RobotState:
        return self._state.model_copy(deep=True)

    def stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._state.stopped = True
        return build_action_result(
            action_type="STOP",
            success=True,
            state_before=before,
            state_after=self._snapshot(),
            duration_ms=min(10, timeout_ms or 1_000),
        )

    def emergency_stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._state.estop_engaged = True
        self._state.stopped = True
        return build_action_result(
            action_type="EMERGENCY_STOP",
            success=True,
            state_before=before,
            state_after=self._snapshot(),
            duration_ms=min(10, timeout_ms or 1_000),
        )

    def _snapshot(self) -> dict[str, object]:
        return self._state.model_dump(mode="json")
