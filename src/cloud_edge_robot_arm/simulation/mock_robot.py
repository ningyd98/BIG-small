from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from cloud_edge_robot_arm.contracts import ActionResult, Pose, RobotState
from cloud_edge_robot_arm.edge.robot_adapter import build_action_result


class FaultCode(StrEnum):
    ACTION_TIMEOUT = "ACTION_TIMEOUT"
    TARGET_UNREACHABLE = "TARGET_UNREACHABLE"
    GRASP_FAILED = "GRASP_FAILED"
    OBJECT_DROPPED = "OBJECT_DROPPED"
    ROBOT_DISCONNECTED = "ROBOT_DISCONNECTED"
    EMERGENCY_STOP_ACTIVE = "EMERGENCY_STOP_ACTIVE"
    COLLISION_DETECTED = "COLLISION_DETECTED"
    INVALID_TARGET_POSE = "INVALID_TARGET_POSE"


@dataclass(frozen=True)
class WorkspaceBounds:
    x_min: float = -0.5
    x_max: float = 0.5
    y_min: float = -0.5
    y_max: float = 0.5
    z_min: float = 0.0
    z_max: float = 0.6

    def contains(self, pose: Pose) -> bool:
        return (
            self.x_min <= pose.x <= self.x_max
            and self.y_min <= pose.y <= self.y_max
            and self.z_min <= pose.z <= self.z_max
        )


@dataclass
class SceneObject:
    object_id: str
    object_class: str
    pose: Pose
    region_id: str | None = None
    attached: bool = False


@dataclass(frozen=True)
class TargetRegion:
    region_id: str
    center: Pose
    radius_m: float = 0.08


@dataclass
class MockScene:
    objects: dict[str, SceneObject]
    regions: dict[str, TargetRegion]
    workspace: WorkspaceBounds = field(default_factory=WorkspaceBounds)
    minimum_safe_height_m: float = 0.08
    scene_version: int = 1

    @classmethod
    def with_default_pick_place_scene(cls) -> MockScene:
        return cls(
            objects={
                "red_cube": SceneObject(
                    object_id="red_cube",
                    object_class="cube",
                    pose=Pose(x=0.2, y=0.0, z=0.02),
                    region_id="table",
                )
            },
            regions={
                "bin_a": TargetRegion(region_id="bin_a", center=Pose(x=-0.2, y=0.18, z=0.02)),
                "table": TargetRegion(region_id="table", center=Pose(x=0.2, y=0.0, z=0.02)),
            },
        )

    def bump_version(self) -> None:
        self.scene_version += 1


Mutation = Callable[[], dict[str, object]]


class MockRobotAdapter:
    def __init__(
        self,
        *,
        scene: MockScene,
        auto_connect: bool = False,
        grasp_failures_remaining: int = 0,
        max_reach_m: float = 0.65,
        default_action_duration_ms: int = 10,
        default_timeout_ms: int = 1_000,
        fault_injections: dict[FaultCode | str, int] | None = None,
    ) -> None:
        self.scene = scene
        self.state = RobotState(connected=auto_connect)
        self.history: list[ActionResult] = []
        self.grasp_failures_remaining = grasp_failures_remaining
        self.max_reach_m = max_reach_m
        self.default_action_duration_ms = default_action_duration_ms
        self.default_timeout_ms = default_timeout_ms
        self._fault_injections: dict[FaultCode, int] = {}
        for fault, count in dict(fault_injections or {}).items():
            self._fault_injections[FaultCode(fault)] = count

    @property
    def scene_version(self) -> int:
        return self.scene.scene_version

    def inject_fault(self, fault: FaultCode, *, count: int = 1) -> None:
        self._fault_injections[fault] = self._fault_injections.get(fault, 0) + count

    def connect(self, *, timeout_ms: int | None = None) -> ActionResult:
        def mutation() -> dict[str, object]:
            self.state.connected = True
            self.state.stopped = False
            return {"connected": True}

        return self._run_action("CONNECT", mutation, timeout_ms=timeout_ms, allow_disconnected=True)

    def disconnect(self, *, timeout_ms: int | None = None) -> ActionResult:
        def mutation() -> dict[str, object]:
            self.state.connected = False
            return {"connected": False}

        return self._run_action(
            "DISCONNECT", mutation, timeout_ms=timeout_ms, allow_disconnected=True
        )

    def home(self, *, timeout_ms: int | None = None) -> ActionResult:
        def mutation() -> dict[str, object]:
            self.state.tcp_pose = Pose(x=0.0, y=-0.2, z=0.18)
            self.state.gripper_open = True
            self.state.stopped = False
            return {"robot_state": self._state_snapshot()}

        return self._run_action("HOME", mutation, timeout_ms=timeout_ms)

    def move_to_pose(self, pose: Pose, *, timeout_ms: int | None = None) -> ActionResult:
        def mutation() -> dict[str, object]:
            self.state.tcp_pose = pose
            self._sync_held_object_pose()
            return {"target_pose": pose.model_dump(mode="json")}

        return self._run_action(
            "MOVE_TO_POSE",
            mutation,
            timeout_ms=timeout_ms,
            target_pose=pose,
            invalid_pose_code=FaultCode.INVALID_TARGET_POSE,
        )

    def open_gripper(self, *, timeout_ms: int | None = None) -> ActionResult:
        def mutation() -> dict[str, object]:
            held = self._held_object()
            if held is not None:
                held.attached = False
            self.state.gripper_open = True
            self.state.holding_object_id = None
            self.scene.bump_version()
            return {"robot_state": self._state_snapshot()}

        return self._run_action("OPEN_GRIPPER", mutation, timeout_ms=timeout_ms)

    def close_gripper(self, *, timeout_ms: int | None = None) -> ActionResult:
        def mutation() -> dict[str, object]:
            self.state.gripper_open = False
            return {"robot_state": self._state_snapshot()}

        return self._run_action("CLOSE_GRIPPER", mutation, timeout_ms=timeout_ms)

    def get_state(self) -> RobotState:
        return self.state.model_copy(deep=True)

    def stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        def mutation() -> dict[str, object]:
            self.state.stopped = True
            return {"robot_state": self._state_snapshot()}

        return self._run_action("STOP", mutation, timeout_ms=timeout_ms, allow_estop=True)

    def emergency_stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        return self._emergency_stop("EMERGENCY_STOP", timeout_ms=timeout_ms)

    def observe(self, *, timeout_ms: int | None = None) -> ActionResult:
        def mutation() -> dict[str, object]:
            objects = {
                object_id: {
                    "object_class": obj.object_class,
                    "pose": obj.pose.model_dump(mode="json"),
                    "region_id": obj.region_id,
                    "attached": obj.attached,
                }
                for object_id, obj in self.scene.objects.items()
            }
            return {
                "scene_version": self.scene.scene_version,
                "objects": objects,
                "robot_state": self._state_snapshot(),
            }

        return self._run_action("OBSERVE", mutation, timeout_ms=timeout_ms)

    def locate_object(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult:
        def mutation() -> dict[str, object]:
            obj = self.scene.objects[object_id]
            return {"object_id": object_id, "pose": obj.pose.model_dump(mode="json")}

        if object_id not in self.scene.objects:
            return self._failure(
                "LOCATE_OBJECT",
                "OBJECT_NOT_FOUND",
                f"object {object_id!r} is not present in the scene",
                {"object_id": object_id},
            )
        return self._run_action("LOCATE_OBJECT", mutation, timeout_ms=timeout_ms)

    def move_above(
        self,
        object_id: str,
        z_offset_m: float = 0.12,
        *,
        timeout_ms: int | None = None,
    ) -> ActionResult:
        obj = self.scene.objects.get(object_id)
        if obj is None:
            return self._failure(
                "MOVE_ABOVE",
                "OBJECT_NOT_FOUND",
                f"object {object_id!r} is not present in the scene",
                {"object_id": object_id},
            )
        target_pose = Pose(x=obj.pose.x, y=obj.pose.y, z=obj.pose.z + z_offset_m)

        def mutation() -> dict[str, object]:
            self.state.tcp_pose = target_pose
            return {"object_id": object_id, "target_pose": target_pose.model_dump(mode="json")}

        return self._run_action(
            "MOVE_ABOVE",
            mutation,
            timeout_ms=timeout_ms,
            target_pose=target_pose,
            invalid_pose_code=FaultCode.TARGET_UNREACHABLE,
        )

    def approach(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult:
        obj = self.scene.objects.get(object_id)
        if obj is None:
            return self._failure(
                "APPROACH",
                "OBJECT_NOT_FOUND",
                f"object {object_id!r} is not present in the scene",
                {"object_id": object_id},
            )
        target_pose = Pose(
            x=obj.pose.x,
            y=obj.pose.y,
            z=max(obj.pose.z + 0.03, self.scene.minimum_safe_height_m),
        )

        def mutation() -> dict[str, object]:
            self.state.tcp_pose = target_pose
            return {"object_id": object_id, "target_pose": target_pose.model_dump(mode="json")}

        return self._run_action(
            "APPROACH",
            mutation,
            timeout_ms=timeout_ms,
            target_pose=target_pose,
            invalid_pose_code=FaultCode.TARGET_UNREACHABLE,
        )

    def grasp(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult:
        if self.grasp_failures_remaining > 0:
            self.grasp_failures_remaining -= 1
            return self._failure(
                "GRASP",
                FaultCode.GRASP_FAILED.value,
                "configured mock grasp failure was injected",
                {"object_id": object_id},
            )
        obj = self.scene.objects.get(object_id)
        if obj is None:
            return self._failure(
                "GRASP",
                "OBJECT_NOT_FOUND",
                f"object {object_id!r} is not present in the scene",
                {"object_id": object_id},
            )
        if self.state.tcp_pose.distance_xy_to(obj.pose) > 0.03:
            return self._failure(
                "GRASP",
                "TCP_NOT_AT_TARGET",
                "tcp is not close enough to object for grasp",
                {"object_id": object_id},
            )

        def mutation() -> dict[str, object]:
            obj.attached = True
            obj.region_id = None
            self.state.gripper_open = False
            self.state.holding_object_id = object_id
            self.scene.bump_version()
            return {"object_id": object_id}

        return self._run_action("GRASP", mutation, timeout_ms=timeout_ms)

    def lift(self, height_m: float = 0.15, *, timeout_ms: int | None = None) -> ActionResult:
        lifted_pose = Pose(
            x=self.state.tcp_pose.x,
            y=self.state.tcp_pose.y,
            z=min(self.scene.workspace.z_max, self.state.tcp_pose.z + height_m),
        )

        def mutation() -> dict[str, object]:
            self.state.tcp_pose = lifted_pose
            self._sync_held_object_pose()
            return {"target_pose": lifted_pose.model_dump(mode="json")}

        return self._run_action(
            "LIFT",
            mutation,
            timeout_ms=timeout_ms,
            target_pose=lifted_pose,
            invalid_pose_code=FaultCode.TARGET_UNREACHABLE,
        )

    def move_to_region(self, region_id: str, *, timeout_ms: int | None = None) -> ActionResult:
        region = self.scene.regions.get(region_id)
        if region is None:
            return self._failure(
                "MOVE_TO_REGION",
                "REGION_NOT_FOUND",
                f"region {region_id!r} is not present in the scene",
                {"region_id": region_id},
            )
        target_pose = Pose(
            x=region.center.x,
            y=region.center.y,
            z=max(self.scene.minimum_safe_height_m + 0.12, region.center.z + 0.16),
        )

        def mutation() -> dict[str, object]:
            self.state.tcp_pose = target_pose
            self._sync_held_object_pose()
            return {"region_id": region_id, "target_pose": target_pose.model_dump(mode="json")}

        return self._run_action(
            "MOVE_TO_REGION",
            mutation,
            timeout_ms=timeout_ms,
            target_pose=target_pose,
            invalid_pose_code=FaultCode.TARGET_UNREACHABLE,
        )

    def place(self, region_id: str, *, timeout_ms: int | None = None) -> ActionResult:
        region = self.scene.regions.get(region_id)
        if region is None:
            return self._failure(
                "PLACE",
                "REGION_NOT_FOUND",
                f"region {region_id!r} is not present in the scene",
                {"region_id": region_id},
            )
        held = self._held_object()
        if held is None:
            return self._failure(
                "PLACE",
                "NO_OBJECT_ATTACHED",
                "cannot place because gripper is not holding an object",
                {"region_id": region_id},
            )

        def mutation() -> dict[str, object]:
            held.pose = Pose(x=region.center.x, y=region.center.y, z=region.center.z)
            held.region_id = region_id
            self.state.tcp_pose = Pose(
                x=region.center.x,
                y=region.center.y,
                z=max(self.scene.minimum_safe_height_m, region.center.z + 0.03),
            )
            self.scene.bump_version()
            return {"region_id": region_id, "object_id": held.object_id}

        return self._run_action("PLACE", mutation, timeout_ms=timeout_ms)

    def release(self, *, timeout_ms: int | None = None) -> ActionResult:
        def mutation() -> dict[str, object]:
            held = self._held_object()
            if held is not None:
                held.attached = False
            self.state.gripper_open = True
            self.state.holding_object_id = None
            self.scene.bump_version()
            return {"robot_state": self._state_snapshot()}

        return self._run_action("RELEASE", mutation, timeout_ms=timeout_ms)

    def retreat(self, distance_m: float = 0.1, *, timeout_ms: int | None = None) -> ActionResult:
        target_pose = Pose(
            x=self.state.tcp_pose.x,
            y=self.state.tcp_pose.y,
            z=min(self.scene.workspace.z_max, self.state.tcp_pose.z + distance_m),
        )

        def mutation() -> dict[str, object]:
            self.state.tcp_pose = target_pose
            return {"target_pose": target_pose.model_dump(mode="json")}

        return self._run_action(
            "RETREAT",
            mutation,
            timeout_ms=timeout_ms,
            target_pose=target_pose,
            invalid_pose_code=FaultCode.TARGET_UNREACHABLE,
        )

    def verify_result(
        self,
        object_id: str,
        region_id: str,
        *,
        timeout_ms: int | None = None,
    ) -> ActionResult:
        obj = self.scene.objects.get(object_id)
        verified = obj is not None and obj.region_id == region_id and not obj.attached
        if not verified:
            return self._failure(
                "VERIFY_RESULT",
                "RESULT_NOT_VERIFIED",
                "object is not in the expected target region",
                {"object_id": object_id, "region_id": region_id},
            )

        def mutation() -> dict[str, object]:
            return {"object_id": object_id, "region_id": region_id, "verified": True}

        return self._run_action("VERIFY_RESULT", mutation, timeout_ms=timeout_ms)

    def safe_stop(self, *, timeout_ms: int | None = None) -> ActionResult:
        return self._emergency_stop("SAFE_STOP", timeout_ms=timeout_ms)

    def object_region(self, object_id: str) -> str | None:
        obj = self.scene.objects.get(object_id)
        return None if obj is None else obj.region_id

    def _run_action(
        self,
        action_type: str,
        mutation: Mutation,
        *,
        timeout_ms: int | None,
        target_pose: Pose | None = None,
        invalid_pose_code: FaultCode = FaultCode.INVALID_TARGET_POSE,
        allow_disconnected: bool = False,
        allow_estop: bool = False,
    ) -> ActionResult:
        before = self._state_snapshot()
        timeout = timeout_ms if timeout_ms is not None else self.default_timeout_ms
        duration = self.default_action_duration_ms

        fault = self._preflight_fault(
            action_type,
            timeout,
            duration,
            target_pose=target_pose,
            invalid_pose_code=invalid_pose_code,
            allow_disconnected=allow_disconnected,
            allow_estop=allow_estop,
        )
        if fault is not None:
            return self._record_result(fault, before=before)

        details = mutation()
        after = self._state_snapshot()
        return self._record_result(
            build_action_result(
                action_type=action_type,
                success=True,
                state_before=before,
                state_after=after,
                duration_ms=duration,
                details=details,
            )
        )

    def _preflight_fault(
        self,
        action_type: str,
        timeout_ms: int,
        duration_ms: int,
        *,
        target_pose: Pose | None,
        invalid_pose_code: FaultCode,
        allow_disconnected: bool,
        allow_estop: bool,
    ) -> ActionResult | None:
        before = self._state_snapshot()
        if not allow_disconnected and (
            not self.state.connected or self._consume_fault(FaultCode.ROBOT_DISCONNECTED)
        ):
            self.state.connected = False
            return self._fault_result(
                action_type,
                FaultCode.ROBOT_DISCONNECTED,
                "robot adapter is disconnected",
                before,
                duration_ms,
            )
        if not allow_estop and (
            self.state.estop_engaged or self._consume_fault(FaultCode.EMERGENCY_STOP_ACTIVE)
        ):
            self.state.estop_engaged = True
            return self._fault_result(
                action_type,
                FaultCode.EMERGENCY_STOP_ACTIVE,
                "emergency stop is active",
                before,
                duration_ms,
            )
        if self._consume_fault(FaultCode.COLLISION_DETECTED):
            self.state.collision_detected = True
            return self._fault_result(
                action_type,
                FaultCode.COLLISION_DETECTED,
                "collision was detected by the mock simulator",
                before,
                duration_ms,
            )
        if self._consume_fault(FaultCode.ACTION_TIMEOUT) or duration_ms > timeout_ms:
            return self._fault_result(
                action_type,
                FaultCode.ACTION_TIMEOUT,
                "action exceeded its timeout budget",
                before,
                timeout_ms,
            )
        if target_pose is not None and (
            self._consume_fault(invalid_pose_code) or not self._is_reachable(target_pose)
        ):
            return self._fault_result(
                action_type,
                invalid_pose_code,
                "target pose is outside workspace or reach limits",
                before,
                duration_ms,
            )
        if action_type == "GRASP" and self._consume_fault(FaultCode.GRASP_FAILED):
            return self._fault_result(
                action_type,
                FaultCode.GRASP_FAILED,
                "grasp failed due to injected fault",
                before,
                duration_ms,
            )
        if action_type in {"LIFT", "MOVE_TO_REGION"} and self._consume_fault(
            FaultCode.OBJECT_DROPPED
        ):
            held = self._held_object()
            if held is not None:
                held.attached = False
                held.region_id = "table"
            self.state.gripper_open = True
            self.state.holding_object_id = None
            return self._fault_result(
                action_type,
                FaultCode.OBJECT_DROPPED,
                "object was dropped during motion",
                before,
                duration_ms,
            )
        return None

    def _emergency_stop(self, action_type: str, *, timeout_ms: int | None) -> ActionResult:
        before = self._state_snapshot()
        duration = min(self.default_action_duration_ms, timeout_ms or self.default_timeout_ms)
        self.state.estop_engaged = True
        self.state.stopped = True
        after = self._state_snapshot()
        return self._record_result(
            build_action_result(
                action_type=action_type,
                success=True,
                state_before=before,
                state_after=after,
                duration_ms=duration,
                details={"robot_state": after},
            )
        )

    def _failure(
        self,
        action_type: str,
        code: str,
        message: str,
        details: dict[str, object],
    ) -> ActionResult:
        before = self._state_snapshot()
        return self._record_result(
            build_action_result(
                action_type=action_type,
                success=False,
                state_before=before,
                state_after=self._state_snapshot(),
                duration_ms=0,
                error_code=code,
                error_message=message,
                details=details,
            )
        )

    def _fault_result(
        self,
        action_type: str,
        fault: FaultCode,
        message: str,
        before: dict[str, object],
        duration_ms: int,
    ) -> ActionResult:
        return build_action_result(
            action_type=action_type,
            success=False,
            state_before=before,
            state_after=self._state_snapshot(),
            duration_ms=duration_ms,
            error_code=fault.value,
            error_message=message,
            details={"fault": fault.value},
        )

    def _record_result(
        self, result: ActionResult, *, before: dict[str, object] | None = None
    ) -> ActionResult:
        if before is not None:
            updated = result.model_copy(update={"state_before": before})
            self.history.append(updated)
            return updated
        self.history.append(result)
        return result

    def _consume_fault(self, fault: FaultCode) -> bool:
        count = self._fault_injections.get(fault, 0)
        if count <= 0:
            return False
        self._fault_injections[fault] = count - 1
        return True

    def _held_object(self) -> SceneObject | None:
        if self.state.holding_object_id is None:
            return None
        return self.scene.objects.get(self.state.holding_object_id)

    def _sync_held_object_pose(self) -> None:
        held = self._held_object()
        if held is not None:
            held.pose = self.state.tcp_pose
            self.scene.bump_version()

    def _is_reachable(self, pose: Pose) -> bool:
        planar_distance = (pose.x**2 + pose.y**2) ** 0.5
        return self.scene.workspace.contains(pose) and planar_distance <= self.max_reach_m

    def _state_snapshot(self) -> dict[str, object]:
        return self.state.model_dump(mode="json")
