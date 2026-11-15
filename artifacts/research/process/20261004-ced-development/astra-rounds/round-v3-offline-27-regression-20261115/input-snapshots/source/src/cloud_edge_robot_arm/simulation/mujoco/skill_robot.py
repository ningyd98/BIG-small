"""Runtime skills backed by MuJoCo joint and gripper actuators."""

from __future__ import annotations

import math
from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts import ActionResult, Pose, RobotState
from cloud_edge_robot_arm.edge.robot_adapter import build_action_result
from cloud_edge_robot_arm.simulation.models import GripperCommand
from cloud_edge_robot_arm.simulation.mujoco.backend import MuJoCoPhysicsBackend
from cloud_edge_robot_arm.simulation.mujoco.motion_controller import (
    MotionTarget,
    MuJoCoMotionController,
)

_DOWNWARD = (math.sqrt(0.5), 0.0, math.sqrt(0.5), 0.0)
_IDENTITY = (1.0, 0.0, 0.0, 0.0)


class MuJoCoSkillRobot:
    """Execute the RuntimeSkillRobot protocol without reading object ground truth.

    World-space targets must be resolved by the visual/safety boundary or an
    explicitly identified offline teacher. This robot never derives them from
    MuJoCo's hidden object coordinates.
    """

    def __init__(self, backend: MuJoCoPhysicsBackend) -> None:
        self._backend = backend
        self._motion = MuJoCoMotionController(backend)
        self._holding_object_id: str | None = None
        self._connected = True

    def home(self, *, timeout_ms: int | None = None) -> ActionResult:
        return self._move(
            "HOME", Pose(x=0.625, y=0.0, z=0.485),
            timeout_ms=timeout_ms, tcp_velocity=None, acceleration=None,
            orientation=_IDENTITY,
        )

    def observe(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        started = datetime.now(UTC)
        if self._backend.estop_engaged:
            return self._result("OBSERVE", False, before, started, 0, "EMERGENCY_STOP")
        step = self._backend.step(steps=1)
        frame = step.sensor_frame
        available = frame.rgb is not None and bool(frame.depth) and frame.captured_at is not None
        return self._result(
            "OBSERVE", available, before, started, step.physics_steps,
            None if available else "RGBD_OBSERVATION_UNAVAILABLE",
            details={
                "frame_id": frame.frame_id,
                "episode_id": frame.episode_id,
                "sim_time_s": frame.sim_time_s,
            },
        )

    def locate_object(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult:
        # A VLM/geometry provider must produce a resolved target. The camera
        # frame does not contain trustworthy online object detections itself.
        before = self._snapshot()
        return self._result(
            "LOCATE_OBJECT", False, before, datetime.now(UTC), 0,
            "VISUAL_LOCALIZATION_REQUIRED", details={"object_id": object_id},
        )

    def move_above(
        self,
        object_id: str,
        z_offset_m: float = 0.12,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult:
        return self._move(
            "MOVE_ABOVE", resolved_target, timeout_ms=timeout_ms,
            tcp_velocity=tcp_velocity, acceleration=acceleration,
            details={"object_id": object_id, "requested_z_offset_m": z_offset_m},
        )

    def approach(
        self,
        object_id: str,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult:
        return self._move(
            "APPROACH", resolved_target, timeout_ms=timeout_ms,
            tcp_velocity=tcp_velocity, acceleration=acceleration,
            details={"object_id": object_id},
        )

    def grasp(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        started = datetime.now(UTC)
        if self._backend.estop_engaged:
            return self._result("GRASP", False, before, started, 0, "EMERGENCY_STOP")
        if object_id != "object":
            return self._result(
                "GRASP", False, before, started, 0, "UNKNOWN_OBJECT_GEOMETRY"
            )
        try:
            steps = self._duration_steps(timeout_ms, default_ms=1000)
        except ValueError:
            return self._result("GRASP", False, before, started, 0, "INVALID_TIMEOUT")
        self._backend.apply_gripper_command(GripperCommand(open=False))
        self._backend.step(steps=steps)
        contacts = self._grasp_contacts()
        success = contacts["left"] > 0 and contacts["right"] > 0
        self._holding_object_id = object_id if success else None
        return self._result(
            "GRASP", success, before, started, steps,
            None if success else "NO_GRASP_CONTACT",
            details={
                "object_id": object_id,
                "grasp_contact_count": contacts["left"] + contacts["right"],
                "left_contact_count": contacts["left"],
                "right_contact_count": contacts["right"],
                "physical_evidence": "bilateral_finger_object_contact",
            },
        )

    def lift(
        self,
        height_m: float = 0.15,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult:
        if not math.isfinite(height_m) or height_m < 0.05:
            return self._reject("LIFT", "INVALID_LIFT_HEIGHT")
        current = self._backend.get_tcp_pose()
        if resolved_target is None:
            resolved_target = Pose(x=current.x, y=current.y, z=current.z + height_m)
        if resolved_target.z - current.z < 0.05:
            return self._reject("LIFT", "INVALID_LIFT_HEIGHT")
        if self.get_state().holding_object_id is None:
            return self._reject("LIFT", "NO_GRASP_CONTACT")
        action = self._move(
            "LIFT", resolved_target, timeout_ms=timeout_ms,
            tcp_velocity=tcp_velocity, acceleration=acceleration,
            details={"requested_height_m": height_m},
        )
        if not action.success:
            return action
        config = self._backend._config
        assert config is not None
        requested_hold_steps = math.ceil(0.5 / config.physics_dt_s)
        held_steps = 0
        bilateral_held = True
        while held_steps < requested_hold_steps:
            chunk = min(5, requested_hold_steps - held_steps)
            self._backend.step(steps=chunk)
            held_steps += chunk
            contacts = self._grasp_contacts()
            if contacts["left"] == 0 or contacts["right"] == 0:
                bilateral_held = False
                break
        tcp_lift_m = self._backend.get_tcp_pose().z - current.z
        success = bilateral_held and held_steps >= requested_hold_steps and tcp_lift_m >= 0.05
        error = None if success else (
            "GRASP_LOST" if not bilateral_held else "LIFT_SHORTFALL"
        )
        return self._result(
            "LIFT", success, action.state_before, action.started_at,
            int(action.details["physics_steps"]) + held_steps, error,
            details={
                **{key: value for key, value in action.details.items() if key != "physics_steps"},
                "measured_tcp_lift_m": tcp_lift_m,
                "contact_hold_s": held_steps * config.physics_dt_s,
                "completion_evidence": "TCP_LIFT_AND_BILATERAL_CONTACT_ONLY",
            },
        )

    def move_to_region(
        self,
        region_id: str,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult:
        return self._move_while_holding(
            "MOVE_TO_REGION", resolved_target, timeout_ms=timeout_ms,
            tcp_velocity=tcp_velocity, acceleration=acceleration,
            details={"region_id": region_id},
        )

    def place(
        self,
        region_id: str,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult:
        return self._move_while_holding(
            "PLACE", resolved_target, timeout_ms=timeout_ms,
            tcp_velocity=tcp_velocity, acceleration=acceleration,
            details={"region_id": region_id},
        )

    def release(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        started = datetime.now(UTC)
        if self._backend.estop_engaged:
            return self._result("RELEASE", False, before, started, 0, "EMERGENCY_STOP")
        try:
            steps = self._duration_steps(timeout_ms, default_ms=1000)
        except ValueError:
            return self._result("RELEASE", False, before, started, 0, "INVALID_TIMEOUT")
        self._backend.apply_gripper_command(GripperCommand(open=True))
        self._backend.step(steps=steps)
        self._holding_object_id = None
        opened = self.get_state().gripper_open
        return self._result(
            "RELEASE", opened, before, started, steps,
            None if opened else "GRIPPER_OPEN_TIMEOUT",
        )

    def retreat(
        self,
        distance_m: float = 0.1,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult:
        if resolved_target is None:
            if not math.isfinite(distance_m) or distance_m <= 0:
                return self._reject("RETREAT", "INVALID_RETREAT_DISTANCE")
            current = self._backend.get_tcp_pose()
            resolved_target = Pose(x=current.x, y=current.y, z=current.z + distance_m)
        return self._move(
            "RETREAT", resolved_target, timeout_ms=timeout_ms,
            tcp_velocity=tcp_velocity, acceleration=acceleration,
            details={"requested_distance_m": distance_m},
        )

    def verify_result(
        self, object_id: str, region_id: str, *, timeout_ms: int | None = None
    ) -> ActionResult:
        # Online verification belongs to the T7 RGB-D condition evaluator;
        # this adapter has no access to independent ground-truth outcomes.
        before = self._snapshot()
        return self._result(
            "VERIFY_RESULT", False, before, datetime.now(UTC), 0,
            "ONLINE_VERIFICATION_UNAVAILABLE",
            details={"object_id": object_id, "region_id": region_id},
        )

    def safe_stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        return self.stop(timeout_ms=timeout_ms).model_copy(update={"action_type": "SAFE_STOP"})

    def stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        return self.emergency_stop(timeout_ms=timeout_ms).model_copy(update={"action_type": "STOP"})

    def emergency_stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        started = datetime.now(UTC)
        self._backend.emergency_stop()
        return self._result("EMERGENCY_STOP", True, before, started, 0)

    def get_state(self) -> RobotState:
        model = self._backend._model
        data = self._backend._data
        if model is None or data is None:
            raise RuntimeError("MuJoCo backend is not initialized")
        finger_positions = [
            float(data.qpos[model.jnt_qposadr[model.joint(name).id]])
            for name in ("finger_left_joint", "finger_right_joint")
        ]
        contacts = self._grasp_contacts()
        holding = (
            self._holding_object_id
            if contacts["left"] > 0 and contacts["right"] > 0
            else None
        )
        return RobotState(
            tcp_pose=self._backend.get_tcp_pose(),
            gripper_open=min(finger_positions) >= 0.035,
            holding_object_id=holding,
            connected=self._connected,
            stopped=self._backend.estop_engaged,
            estop_engaged=self._backend.estop_engaged,
            collision_detected=any(c.illegal for c in self._backend.get_contacts()),
        )

    def object_region(self, object_id: str) -> str | None:
        return None

    def resolve_target_pose(self, skill: str, parameters: dict[str, object]) -> Pose | None:
        return None

    def _move(
        self,
        action_type: str,
        target: Pose | None,
        *,
        timeout_ms: int | None,
        tcp_velocity: float | None,
        acceleration: float | None,
        orientation: tuple[float, float, float, float] = _DOWNWARD,
        details: dict[str, object] | None = None,
    ) -> ActionResult:
        before = self._snapshot()
        started = datetime.now(UTC)
        if self._backend.estop_engaged:
            return self._result(action_type, False, before, started, 0, "EMERGENCY_STOP")
        if target is None:
            return self._result(
                action_type, False, before, started, 0, "TARGET_NOT_RESOLVED"
            )
        velocity = 1.5 if tcp_velocity is None else tcp_velocity / 0.3
        accel = 4.0 if acceleration is None else acceleration / 0.3
        try:
            outcome = self._motion.move_tcp(
                MotionTarget(position=target, orientation_wxyz=orientation),
                timeout_s=(timeout_ms if timeout_ms is not None else 8000) / 1000.0,
                max_joint_velocity_rad_s=velocity,
                max_joint_acceleration_rad_s2=accel,
            )
        except ValueError as exc:
            return self._result(
                action_type, False, before, started, 0, "INVALID_MOTION_REQUEST",
                details={"reason": str(exc)},
            )
        movement_details: dict[str, object] = {
            **(details or {}),
            "target_pose": target.model_dump(),
            "position_error_m": outcome.position_error_m,
            "orientation_error_deg": outcome.orientation_error_deg,
            "motion_status": outcome.status,
            "max_load_compensation_rad": outcome.max_load_compensation_rad,
        }
        return self._result(
            action_type, outcome.status == "SUCCEEDED", before, started,
            outcome.physics_steps,
            None if outcome.status == "SUCCEEDED" else outcome.status,
            details=movement_details,
        )

    def _move_while_holding(
        self,
        action_type: str,
        target: Pose | None,
        *,
        timeout_ms: int | None,
        tcp_velocity: float | None,
        acceleration: float | None,
        details: dict[str, object],
    ) -> ActionResult:
        if self.get_state().holding_object_id is None:
            return self._reject(action_type, "NO_GRASP_CONTACT")
        action = self._move(
            action_type, target, timeout_ms=timeout_ms,
            tcp_velocity=tcp_velocity, acceleration=acceleration, details=details,
        )
        if not action.success or self.get_state().holding_object_id is not None:
            return action
        return self._result(
            action_type, False, action.state_before, action.started_at,
            int(action.details["physics_steps"]), "GRASP_LOST",
            details={
                key: value for key, value in action.details.items() if key != "physics_steps"
            },
        )

    def _grasp_contacts(self) -> dict[str, int]:
        counts = {"left": 0, "right": 0}
        for contact in self._backend.get_contacts():
            pair = {contact.geom1, contact.geom2}
            if pair == {"left_finger_geom", "object_geom"}:
                counts["left"] += 1
            elif pair == {"right_finger_geom", "object_geom"}:
                counts["right"] += 1
        return counts

    def _duration_steps(self, timeout_ms: int | None, *, default_ms: int) -> int:
        config = self._backend._config
        if config is None:
            raise RuntimeError("MuJoCo backend is not initialized")
        budget = timeout_ms if timeout_ms is not None else default_ms
        steps = int((budget / 1000.0) / config.physics_dt_s)
        if steps < 1:
            raise ValueError("timeout must allow at least one physics step")
        return steps

    def _snapshot(self) -> dict[str, object]:
        return self.get_state().model_dump(mode="json")

    def _reject(self, action_type: str, code: str) -> ActionResult:
        before = self._snapshot()
        return self._result(action_type, False, before, datetime.now(UTC), 0, code)

    def _result(
        self,
        action_type: str,
        success: bool,
        before: dict[str, object],
        started: datetime,
        physics_steps: int,
        error_code: str | None = None,
        *,
        details: dict[str, object] | None = None,
    ) -> ActionResult:
        config = self._backend._config
        assert config is not None
        return build_action_result(
            action_type=action_type,
            success=success,
            state_before=before,
            state_after=self._snapshot(),
            duration_ms=int(round(physics_steps * config.physics_dt_s * 1000)),
            error_code=error_code,
            details={"physics_steps": physics_steps, **(details or {})},
            started_at=started,
        )
