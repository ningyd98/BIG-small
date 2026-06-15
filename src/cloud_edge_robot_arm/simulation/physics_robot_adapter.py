from __future__ import annotations

from datetime import UTC, datetime

from cloud_edge_robot_arm.contracts import ActionResult, Pose, RobotState
from cloud_edge_robot_arm.edge.robot_adapter import build_action_result
from cloud_edge_robot_arm.simulation.backend import SimulatorBackend
from cloud_edge_robot_arm.simulation.models import GripperCommand, JointCommand
from cloud_edge_robot_arm.simulation.mujoco.backend import joint_targets_for_pose


class PhysicsRobotAdapter:
    def __init__(self, backend: SimulatorBackend) -> None:
        self._backend = backend
        self._connected = False
        self._holding_object_id: str | None = None
        self._object_regions: dict[str, str] = {"object": "source"}

    def connect(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._connected = True
        return self._result("CONNECT", True, before, self._snapshot(), 0)

    def disconnect(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._connected = False
        return self._result("DISCONNECT", True, before, self._snapshot(), 0)

    def home(self, *, timeout_ms: int | None = None) -> ActionResult:
        return self.move_to_pose(Pose(x=0.35, y=0.0, z=0.35), timeout_ms=timeout_ms)

    def move_to_pose(self, pose: Pose, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        guard = self._guard_motion(before, "MOVE_TO_POSE")
        if guard is not None:
            return guard
        start = self._backend.get_sim_time()
        self._backend.apply_joint_targets(JointCommand(positions=joint_targets_for_pose(pose)))
        steps = max(1, int(((timeout_ms or 1000) / 1000.0) / 0.02))
        total_steps = 0
        for _ in range(steps):
            step = self._backend.step(steps=5)
            total_steps += step.physics_steps
            if self._backend.get_tcp_pose().distance_xy_to(pose) < 0.02:
                break
        duration_ms = int(round((self._backend.get_sim_time() - start) * 1000.0))
        return self._result(
            "MOVE_TO_POSE",
            True,
            before,
            self._snapshot(),
            duration_ms,
            details={"physics_steps": total_steps, "target_pose": pose.model_dump()},
        )

    def open_gripper(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._backend.apply_gripper_command(GripperCommand(open=True))
        step = self._backend.step(steps=20)
        self._holding_object_id = None
        return self._result(
            "OPEN_GRIPPER",
            True,
            before,
            self._snapshot(),
            int(step.sim_time_s * 1000)
            - int((step.sim_time_s - step.physics_steps * 0.0041666667) * 1000),
            details={"physics_steps": step.physics_steps},
        )

    def close_gripper(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._backend.apply_gripper_command(GripperCommand(open=False))
        step = self._backend.step(steps=80)
        contacts = self._backend.get_contacts()
        grasp_contacts = [contact for contact in contacts if contact.expected]
        success = bool(grasp_contacts)
        if success:
            self._holding_object_id = "object"
        return self._result(
            "CLOSE_GRIPPER",
            success,
            before,
            self._snapshot(),
            int(round(step.physics_steps * 4.1666667)),
            error_code=None if success else "NO_GRASP_CONTACT",
            details={
                "physics_steps": step.physics_steps,
                "grasp_contact_count": len(grasp_contacts),
            },
        )

    def observe(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        step = self._backend.step(steps=8)
        return self._result(
            "OBSERVE",
            True,
            before,
            self._snapshot(),
            int(round(step.physics_steps * 4.1666667)),
            details={"sensor_frame_time_s": step.sensor_frame.sim_time_s},
        )

    def locate_object(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        frame = self._backend.get_sensor_frame()
        found = any(item.get("object_id") == object_id for item in frame.object_detections)
        return self._result(
            "LOCATE_OBJECT",
            found,
            before,
            self._snapshot(),
            0,
            error_code=None if found else "OBJECT_NOT_DETECTED",
            details={"sensor_latency_ms": frame.latency_ms},
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
        target = resolved_target or Pose(x=0.45, y=0.0, z=0.04 + z_offset_m)
        return self.move_to_pose(target, timeout_ms=timeout_ms)

    def approach(
        self,
        object_id: str,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult:
        target = resolved_target or Pose(x=0.45, y=0.0, z=0.06)
        return self.move_to_pose(target, timeout_ms=timeout_ms)

    def grasp(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult:
        result = self.close_gripper(timeout_ms=timeout_ms)
        details = dict(result.details)
        details["physical_evidence"] = "gripper_contact_required"
        return result.model_copy(update={"action_type": "GRASP", "details": details})

    def lift(
        self,
        height_m: float = 0.15,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult:
        current = self._backend.get_tcp_pose()
        return self.move_to_pose(
            Pose(x=current.x, y=current.y, z=current.z + height_m), timeout_ms=timeout_ms
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
        target = resolved_target or Pose(x=0.2, y=0.25, z=0.2)
        return self.move_to_pose(target, timeout_ms=timeout_ms)

    def place(
        self,
        region_id: str,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult:
        target = resolved_target or Pose(x=0.2, y=0.25, z=0.07)
        result = self.move_to_pose(target, timeout_ms=timeout_ms)
        if result.success and self._holding_object_id is not None:
            self._object_regions[self._holding_object_id] = region_id
        return result.model_copy(update={"action_type": "PLACE"})

    def release(self, *, timeout_ms: int | None = None) -> ActionResult:
        return self.open_gripper(timeout_ms=timeout_ms).model_copy(
            update={"action_type": "RELEASE"}
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
        current = self._backend.get_tcp_pose()
        return self.move_to_pose(
            Pose(x=current.x - distance_m, y=current.y, z=current.z + 0.03), timeout_ms=timeout_ms
        )

    def verify_result(
        self, object_id: str, region_id: str, *, timeout_ms: int | None = None
    ) -> ActionResult:
        before = self._snapshot()
        success = self._object_regions.get(object_id) == region_id
        return self._result(
            "VERIFY_RESULT",
            success,
            before,
            self._snapshot(),
            0,
            error_code=None if success else "OBJECT_NOT_IN_REGION",
        )

    def safe_stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        return self.stop(timeout_ms=timeout_ms).model_copy(update={"action_type": "SAFE_STOP"})

    def stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._backend.emergency_stop()
        return self._result("STOP", True, before, self._snapshot(), 0)

    def emergency_stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        before = self._snapshot()
        self._backend.emergency_stop()
        return self._result("EMERGENCY_STOP", True, before, self._snapshot(), 0)

    def get_state(self) -> RobotState:
        tcp = self._backend.get_tcp_pose()
        return RobotState(
            tcp_pose=tcp,
            gripper_open=self._backend.get_joint_state().positions[-1] >= 0.0,
            holding_object_id=self._holding_object_id,
            connected=self._connected,
            stopped=self._backend.estop_engaged
            if hasattr(self._backend, "estop_engaged")
            else False,
            estop_engaged=self._backend.estop_engaged
            if hasattr(self._backend, "estop_engaged")
            else False,
            collision_detected=any(contact.illegal for contact in self._backend.get_contacts()),
        )

    def object_region(self, object_id: str) -> str | None:
        return self._object_regions.get(object_id)

    def resolve_target_pose(self, skill: str, parameters: dict[str, object]) -> Pose | None:
        return None

    def _guard_motion(self, before: dict[str, object], action_type: str) -> ActionResult | None:
        if not self._connected:
            return self._result(
                action_type, False, before, self._snapshot(), 0, error_code="ROBOT_DISCONNECTED"
            )
        if getattr(self._backend, "estop_engaged", False):
            return self._result(
                action_type, False, before, self._snapshot(), 0, error_code="EMERGENCY_STOP_ENGAGED"
            )
        return None

    def _snapshot(self) -> dict[str, object]:
        return self.get_state().model_dump(mode="json")

    def _result(
        self,
        action_type: str,
        success: bool,
        before: dict[str, object],
        after: dict[str, object],
        duration_ms: int,
        *,
        error_code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> ActionResult:
        return build_action_result(
            action_type=action_type,
            success=success,
            state_before=before,
            state_after=after,
            duration_ms=max(0, duration_ms),
            error_code=error_code,
            error_message=error_code,
            details=details or {},
            started_at=datetime.now(UTC),
        )
