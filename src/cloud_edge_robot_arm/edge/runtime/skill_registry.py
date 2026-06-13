from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from cloud_edge_robot_arm.contracts import ActionResult, Pose, RobotState, SkillName


class RuntimeSkillRobot(Protocol):
    def home(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def observe(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def locate_object(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult: ...

    def move_above(
        self,
        object_id: str,
        z_offset_m: float = 0.12,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult: ...

    def approach(
        self,
        object_id: str,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult: ...

    def grasp(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult: ...

    def lift(
        self,
        height_m: float = 0.15,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult: ...

    def move_to_region(
        self,
        region_id: str,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult: ...

    def place(
        self,
        region_id: str,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult: ...

    def release(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def retreat(
        self,
        distance_m: float = 0.1,
        *,
        timeout_ms: int | None = None,
        resolved_target: Pose | None = None,
        tcp_velocity: float | None = None,
        acceleration: float | None = None,
    ) -> ActionResult: ...

    def verify_result(
        self,
        object_id: str,
        region_id: str,
        *,
        timeout_ms: int | None = None,
    ) -> ActionResult: ...

    def safe_stop(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def stop(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def emergency_stop(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def get_state(self) -> RobotState: ...

    def object_region(self, object_id: str) -> str | None: ...

    def resolve_target_pose(self, skill: str, parameters: dict[str, object]) -> Pose | None: ...


class SkillParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MotionParams(SkillParams):
    """Optional kinematics + resolved target injected by the safety pipeline."""

    tcp_velocity: float | None = None
    acceleration: float | None = None
    target_pose: dict[str, float] | None = None


class EmptyParams(SkillParams):
    model_config = ConfigDict(extra="forbid")


class HomeParams(MotionParams):
    pass


class ObjectParams(MotionParams):
    object_id: str = Field(min_length=1)


class MoveAboveParams(ObjectParams):
    z_offset_m: float = 0.12


class LiftParams(MotionParams):
    height_m: float = 0.15


class RegionParams(MotionParams):
    region_id: str = Field(min_length=1)


class RetreatParams(MotionParams):
    distance_m: float = 0.1


class ReleaseParams(MotionParams):
    pass


class VerifyParams(SkillParams):
    object_id: str = Field(min_length=1)
    region_id: str = Field(min_length=1)


def _resolved_pose(params: MotionParams) -> Pose | None:
    if params.target_pose is None:
        return None
    return Pose(
        x=params.target_pose["x"],
        y=params.target_pose["y"],
        z=params.target_pose["z"],
    )


SkillHandler = Callable[[RuntimeSkillRobot, SkillParams, int], ActionResult]


@dataclass(frozen=True)
class SkillDefinition:
    skill: SkillName
    parameter_model: type[SkillParams]
    handler: SkillHandler

    def validate(self, payload: Mapping[str, object]) -> SkillParams:
        return self.parameter_model.model_validate(payload)


def _home(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    return robot.home(timeout_ms=timeout_ms)


def _observe(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    return robot.observe(timeout_ms=timeout_ms)


def _locate_object(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    typed = cast(ObjectParams, params)
    return robot.locate_object(typed.object_id, timeout_ms=timeout_ms)


def _move_above(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    typed = cast(MoveAboveParams, params)
    return robot.move_above(
        typed.object_id,
        typed.z_offset_m,
        timeout_ms=timeout_ms,
        resolved_target=_resolved_pose(typed),
        tcp_velocity=typed.tcp_velocity,
        acceleration=typed.acceleration,
    )


def _approach(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    typed = cast(ObjectParams, params)
    return robot.approach(
        typed.object_id,
        timeout_ms=timeout_ms,
        resolved_target=_resolved_pose(typed),
        tcp_velocity=typed.tcp_velocity,
        acceleration=typed.acceleration,
    )


def _grasp(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    typed = cast(ObjectParams, params)
    return robot.grasp(typed.object_id, timeout_ms=timeout_ms)


def _lift(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    typed = cast(LiftParams, params)
    return robot.lift(
        typed.height_m,
        timeout_ms=timeout_ms,
        resolved_target=_resolved_pose(typed),
        tcp_velocity=typed.tcp_velocity,
        acceleration=typed.acceleration,
    )


def _move_to_region(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    typed = cast(RegionParams, params)
    return robot.move_to_region(
        typed.region_id,
        timeout_ms=timeout_ms,
        resolved_target=_resolved_pose(typed),
        tcp_velocity=typed.tcp_velocity,
        acceleration=typed.acceleration,
    )


def _place(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    typed = cast(RegionParams, params)
    return robot.place(
        typed.region_id,
        timeout_ms=timeout_ms,
        resolved_target=_resolved_pose(typed),
        tcp_velocity=typed.tcp_velocity,
        acceleration=typed.acceleration,
    )


def _release(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    return robot.release(timeout_ms=timeout_ms)


def _retreat(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    typed = cast(RetreatParams, params)
    return robot.retreat(
        typed.distance_m,
        timeout_ms=timeout_ms,
        resolved_target=_resolved_pose(typed),
        tcp_velocity=typed.tcp_velocity,
        acceleration=typed.acceleration,
    )


def _verify_result(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    typed = cast(VerifyParams, params)
    return robot.verify_result(typed.object_id, typed.region_id, timeout_ms=timeout_ms)


def _safe_stop(robot: RuntimeSkillRobot, params: SkillParams, timeout_ms: int) -> ActionResult:
    return robot.safe_stop(timeout_ms=timeout_ms)


class SkillRegistry:
    def __init__(self, definitions: Mapping[SkillName, SkillDefinition]) -> None:
        self._definitions = dict(definitions)

    @classmethod
    def default(cls) -> SkillRegistry:
        return cls(
            {
                SkillName.HOME: SkillDefinition(SkillName.HOME, HomeParams, _home),
                SkillName.OBSERVE: SkillDefinition(SkillName.OBSERVE, EmptyParams, _observe),
                SkillName.LOCATE_OBJECT: SkillDefinition(
                    SkillName.LOCATE_OBJECT, ObjectParams, _locate_object
                ),
                SkillName.MOVE_ABOVE: SkillDefinition(
                    SkillName.MOVE_ABOVE, MoveAboveParams, _move_above
                ),
                SkillName.APPROACH: SkillDefinition(SkillName.APPROACH, ObjectParams, _approach),
                SkillName.GRASP: SkillDefinition(SkillName.GRASP, ObjectParams, _grasp),
                SkillName.LIFT: SkillDefinition(SkillName.LIFT, LiftParams, _lift),
                SkillName.MOVE_TO_REGION: SkillDefinition(
                    SkillName.MOVE_TO_REGION, RegionParams, _move_to_region
                ),
                SkillName.PLACE: SkillDefinition(SkillName.PLACE, RegionParams, _place),
                SkillName.RELEASE: SkillDefinition(SkillName.RELEASE, ReleaseParams, _release),
                SkillName.RETREAT: SkillDefinition(SkillName.RETREAT, RetreatParams, _retreat),
                SkillName.VERIFY_RESULT: SkillDefinition(
                    SkillName.VERIFY_RESULT, VerifyParams, _verify_result
                ),
                SkillName.SAFE_STOP: SkillDefinition(SkillName.SAFE_STOP, EmptyParams, _safe_stop),
            }
        )

    def definition_for(self, skill: SkillName) -> SkillDefinition | None:
        return self._definitions.get(skill)

    def skills(self) -> tuple[SkillName, ...]:
        return tuple(self._definitions)
