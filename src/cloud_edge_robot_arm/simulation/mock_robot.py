from __future__ import annotations

from dataclasses import dataclass, field

from cloud_edge_robot_arm.contracts import ActionResult, Pose, RobotState
from cloud_edge_robot_arm.errors import StructuredError


@dataclass
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


@dataclass
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


class MockRobotAdapter:
    def __init__(
        self,
        *,
        scene: MockScene,
        grasp_failures_remaining: int = 0,
        max_reach_m: float = 0.65,
    ) -> None:
        self.scene = scene
        self.state = RobotState()
        self.history: list[ActionResult] = []
        self.grasp_failures_remaining = grasp_failures_remaining
        self.max_reach_m = max_reach_m

    @property
    def scene_version(self) -> int:
        return self.scene.scene_version

    def home(self) -> ActionResult:
        self.state.tcp_pose = Pose(x=0.0, y=-0.2, z=0.18)
        self.state.gripper_open = True
        return self._record("HOME", True, details={"robot_state": self._robot_state_details()})

    def observe(self) -> ActionResult:
        objects = {
            object_id: {
                "object_class": obj.object_class,
                "pose": obj.pose.model_dump(mode="json"),
                "region_id": obj.region_id,
                "attached": obj.attached,
            }
            for object_id, obj in self.scene.objects.items()
        }
        return self._record(
            "OBSERVE",
            True,
            details={
                "scene_version": self.scene.scene_version,
                "objects": objects,
                "robot_state": self._robot_state_details(),
            },
        )

    def locate_object(self, object_id: str) -> ActionResult:
        obj = self.scene.objects.get(object_id)
        if obj is None:
            return self._record_failure(
                "LOCATE_OBJECT",
                "OBJECT_NOT_FOUND",
                f"object {object_id!r} is not present in the scene",
                {"object_id": object_id},
            )
        return self._record(
            "LOCATE_OBJECT",
            True,
            details={"object_id": object_id, "pose": obj.pose.model_dump(mode="json")},
        )

    def move_above(self, object_id: str, z_offset_m: float = 0.12) -> ActionResult:
        obj = self.scene.objects.get(object_id)
        if obj is None:
            return self._record_failure(
                "MOVE_ABOVE",
                "OBJECT_NOT_FOUND",
                f"object {object_id!r} is not present in the scene",
                {"object_id": object_id},
            )
        target_pose = Pose(x=obj.pose.x, y=obj.pose.y, z=obj.pose.z + z_offset_m)
        if not self._is_reachable(target_pose):
            return self._record_failure(
                "MOVE_ABOVE",
                "TARGET_UNREACHABLE",
                "target pose is outside mock workspace or reach radius",
                {"object_id": object_id, "target_pose": target_pose.model_dump(mode="json")},
            )
        self.state.tcp_pose = target_pose
        return self._record(
            "MOVE_ABOVE",
            True,
            details={"object_id": object_id, "target_pose": target_pose.model_dump(mode="json")},
        )

    def approach(self, object_id: str) -> ActionResult:
        obj = self.scene.objects.get(object_id)
        if obj is None:
            return self._record_failure(
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
        if not self._is_reachable(target_pose):
            return self._record_failure(
                "APPROACH",
                "TARGET_UNREACHABLE",
                "approach pose is outside mock workspace or reach radius",
                {"object_id": object_id, "target_pose": target_pose.model_dump(mode="json")},
            )
        self.state.tcp_pose = target_pose
        return self._record(
            "APPROACH",
            True,
            details={"object_id": object_id, "target_pose": target_pose.model_dump(mode="json")},
        )

    def grasp(self, object_id: str) -> ActionResult:
        if self.grasp_failures_remaining > 0:
            self.grasp_failures_remaining -= 1
            return self._record_failure(
                "GRASP",
                "GRASP_FAILED",
                "configured mock grasp failure was injected",
                {"object_id": object_id},
            )
        obj = self.scene.objects.get(object_id)
        if obj is None:
            return self._record_failure(
                "GRASP",
                "OBJECT_NOT_FOUND",
                f"object {object_id!r} is not present in the scene",
                {"object_id": object_id},
            )
        if self.state.tcp_pose.distance_xy_to(obj.pose) > 0.03:
            return self._record_failure(
                "GRASP",
                "TCP_NOT_AT_TARGET",
                "tcp is not close enough to object for grasp",
                {"object_id": object_id},
            )
        obj.attached = True
        obj.region_id = None
        self.state.gripper_open = False
        self.state.holding_object_id = object_id
        self.scene.bump_version()
        return self._record("GRASP", True, details={"object_id": object_id})

    def lift(self, height_m: float = 0.15) -> ActionResult:
        lifted_pose = Pose(
            x=self.state.tcp_pose.x,
            y=self.state.tcp_pose.y,
            z=min(self.scene.workspace.z_max, self.state.tcp_pose.z + height_m),
        )
        if not self._is_reachable(lifted_pose):
            return self._record_failure(
                "LIFT",
                "TARGET_UNREACHABLE",
                "lift target exceeds workspace",
                {"target_pose": lifted_pose.model_dump(mode="json")},
            )
        self.state.tcp_pose = lifted_pose
        self._sync_held_object_pose()
        return self._record(
            "LIFT",
            True,
            details={"target_pose": lifted_pose.model_dump(mode="json")},
        )

    def move_to_region(self, region_id: str) -> ActionResult:
        region = self.scene.regions.get(region_id)
        if region is None:
            return self._record_failure(
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
        if not self._is_reachable(target_pose):
            return self._record_failure(
                "MOVE_TO_REGION",
                "TARGET_UNREACHABLE",
                "region approach pose is outside mock workspace or reach radius",
                {"region_id": region_id, "target_pose": target_pose.model_dump(mode="json")},
            )
        self.state.tcp_pose = target_pose
        self._sync_held_object_pose()
        return self._record(
            "MOVE_TO_REGION",
            True,
            details={"region_id": region_id, "target_pose": target_pose.model_dump(mode="json")},
        )

    def place(self, region_id: str) -> ActionResult:
        region = self.scene.regions.get(region_id)
        if region is None:
            return self._record_failure(
                "PLACE",
                "REGION_NOT_FOUND",
                f"region {region_id!r} is not present in the scene",
                {"region_id": region_id},
            )
        held = self._held_object()
        if held is None:
            return self._record_failure(
                "PLACE",
                "NO_OBJECT_ATTACHED",
                "cannot place because gripper is not holding an object",
                {"region_id": region_id},
            )
        held.pose = Pose(x=region.center.x, y=region.center.y, z=region.center.z)
        held.region_id = region_id
        self.state.tcp_pose = Pose(
            x=region.center.x,
            y=region.center.y,
            z=max(self.scene.minimum_safe_height_m, region.center.z + 0.03),
        )
        self.scene.bump_version()
        return self._record(
            "PLACE",
            True,
            details={"region_id": region_id, "object_id": held.object_id},
        )

    def release(self) -> ActionResult:
        held = self._held_object()
        if held is not None:
            held.attached = False
        self.state.gripper_open = True
        self.state.holding_object_id = None
        self.scene.bump_version()
        return self._record("RELEASE", True, details={"robot_state": self._robot_state_details()})

    def retreat(self, distance_m: float = 0.1) -> ActionResult:
        target_pose = Pose(
            x=self.state.tcp_pose.x,
            y=self.state.tcp_pose.y,
            z=min(self.scene.workspace.z_max, self.state.tcp_pose.z + distance_m),
        )
        if not self._is_reachable(target_pose):
            return self._record_failure(
                "RETREAT",
                "TARGET_UNREACHABLE",
                "retreat target exceeds workspace",
                {"target_pose": target_pose.model_dump(mode="json")},
            )
        self.state.tcp_pose = target_pose
        return self._record(
            "RETREAT",
            True,
            details={"target_pose": target_pose.model_dump(mode="json")},
        )

    def verify_result(self, object_id: str, region_id: str) -> ActionResult:
        obj = self.scene.objects.get(object_id)
        verified = obj is not None and obj.region_id == region_id and not obj.attached
        if not verified:
            return self._record_failure(
                "VERIFY_RESULT",
                "RESULT_NOT_VERIFIED",
                "object is not in the expected target region",
                {"object_id": object_id, "region_id": region_id},
            )
        return self._record(
            "VERIFY_RESULT",
            True,
            details={"object_id": object_id, "region_id": region_id, "verified": True},
        )

    def safe_stop(self) -> ActionResult:
        self.state.estop_engaged = True
        return self._record("SAFE_STOP", True, details={"robot_state": self._robot_state_details()})

    def object_region(self, object_id: str) -> str | None:
        obj = self.scene.objects.get(object_id)
        return None if obj is None else obj.region_id

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

    def _robot_state_details(self) -> dict[str, object]:
        return self.state.model_dump(mode="json")

    def _record(
        self,
        skill: str,
        success: bool,
        *,
        details: dict[str, object],
        error: StructuredError | None = None,
    ) -> ActionResult:
        result = ActionResult(skill=skill, success=success, error=error, details=details)
        self.history.append(result)
        return result

    def _record_failure(
        self,
        skill: str,
        code: str,
        message: str,
        details: dict[str, object],
    ) -> ActionResult:
        return self._record(
            skill,
            False,
            details=details,
            error=StructuredError(
                code=code,
                message=message,
                category="MOCK_ROBOT",
                details=details,
            ),
        )
