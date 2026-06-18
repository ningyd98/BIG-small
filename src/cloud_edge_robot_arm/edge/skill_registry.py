"""旧版技能注册表。

将受控 SkillName 绑定到机器人方法，不能注册任意用户提供的 callable。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from cloud_edge_robot_arm.contracts import ActionResult, SkillName


class SkillRobot(Protocol):
    def home(self) -> ActionResult: ...

    def observe(self) -> ActionResult: ...

    def locate_object(self, object_id: str) -> ActionResult: ...

    def move_above(self, object_id: str, z_offset_m: float = 0.12) -> ActionResult: ...

    def approach(self, object_id: str) -> ActionResult: ...

    def grasp(self, object_id: str) -> ActionResult: ...

    def lift(self, height_m: float = 0.15) -> ActionResult: ...

    def move_to_region(self, region_id: str) -> ActionResult: ...

    def place(self, region_id: str) -> ActionResult: ...

    def release(self) -> ActionResult: ...

    def retreat(self, distance_m: float = 0.1) -> ActionResult: ...

    def verify_result(self, object_id: str, region_id: str) -> ActionResult: ...

    def safe_stop(self) -> ActionResult: ...


SkillHandler = Callable[[SkillRobot, Mapping[str, Any]], ActionResult]


class SkillRegistry:
    def __init__(self, handlers: Mapping[SkillName, SkillHandler]) -> None:
        self._handlers = dict(handlers)

    @classmethod
    def default(cls) -> SkillRegistry:
        return cls(
            {
                SkillName.HOME: lambda robot, params: robot.home(),
                SkillName.OBSERVE: lambda robot, params: robot.observe(),
                SkillName.LOCATE_OBJECT: lambda robot, params: robot.locate_object(
                    str(params["object_id"])
                ),
                SkillName.MOVE_ABOVE: lambda robot, params: robot.move_above(
                    str(params["object_id"]), float(params.get("z_offset_m", 0.12))
                ),
                SkillName.APPROACH: lambda robot, params: robot.approach(str(params["object_id"])),
                SkillName.GRASP: lambda robot, params: robot.grasp(str(params["object_id"])),
                SkillName.LIFT: lambda robot, params: robot.lift(
                    float(params.get("height_m", 0.15))
                ),
                SkillName.MOVE_TO_REGION: lambda robot, params: robot.move_to_region(
                    str(params["region_id"])
                ),
                SkillName.PLACE: lambda robot, params: robot.place(str(params["region_id"])),
                SkillName.RELEASE: lambda robot, params: robot.release(),
                SkillName.RETREAT: lambda robot, params: robot.retreat(
                    float(params.get("distance_m", 0.1))
                ),
                SkillName.VERIFY_RESULT: lambda robot, params: robot.verify_result(
                    str(params["object_id"]), str(params["region_id"])
                ),
                SkillName.SAFE_STOP: lambda robot, params: robot.safe_stop(),
            }
        )

    def skills(self) -> tuple[SkillName, ...]:
        return tuple(self._handlers)

    def handler_for(self, skill: SkillName | str) -> SkillHandler | None:
        if isinstance(skill, str):
            try:
                skill = SkillName(skill)
            except ValueError:
                return None
        return self._handlers.get(skill)
