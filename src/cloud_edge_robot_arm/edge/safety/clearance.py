"""Trusted, step-bound vertical escape from a low grasp or release pose."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from typing import ClassVar


@dataclass(frozen=True)
class VerticalClearancePath:
    task_id: str
    step_id: str
    skill: str
    start_m: tuple[float, float, float]
    target_m: tuple[float, float, float]
    minimum_height_m: float

    lateral_tolerance_m: ClassVar[float] = 0.001
    backtrack_tolerance_m: ClassVar[float] = 0.001

    def __post_init__(self) -> None:
        if not self.task_id or not self.step_id or self.skill not in {"LIFT", "RETREAT"}:
            raise ValueError("clearance requires an identified LIFT or RETREAT step")
        for position in (self.start_m, self.target_m):
            if not isinstance(position, tuple) or len(position) != 3 or not all(
                isinstance(value, int | float) and not isinstance(value, bool) and isfinite(value)
                for value in position
            ):
                raise ValueError("clearance positions must be finite XYZ triples")
        if not isfinite(self.minimum_height_m) or self.minimum_height_m < 0.08:
            raise ValueError("clearance cannot lower the 80 mm minimum height")
        if self.target_m[:2] != self.start_m[:2]:
            raise ValueError("clearance target must be vertical from its bound start")
        if self.target_m[2] < self.minimum_height_m or self.target_m[2] <= self.start_m[2]:
            raise ValueError("clearance must rise to at least the minimum height")

    def check_binding(
        self, *, task_id: str, step_id: str, skill: str, target: object,
        minimum_height_m: float,
    ) -> None:
        if (task_id, step_id, skill) != (self.task_id, self.step_id, self.skill):
            raise ValueError("clearance task, step or skill does not match")
        if self.minimum_height_m < minimum_height_m:
            raise ValueError("clearance does not satisfy the active minimum height")
        if not isinstance(target, dict) or any(
            isinstance(target.get(axis), bool)
            or not isinstance(target.get(axis), int | float)
            or target[axis] != self.target_m[index]
            for index, axis in enumerate(("x", "y", "z"))
        ):
            raise ValueError("clearance target differs from the checked motion target")

    def check_position(
        self, position: tuple[float, float, float], *, peak_z: float | None = None,
    ) -> None:
        if not all(isfinite(value) for value in position):
            raise ValueError("clearance feedback is not finite")
        x, y, z = position
        if hypot(x - self.start_m[0], y - self.start_m[1]) > self.lateral_tolerance_m:
            raise ValueError("clearance left its 1 mm lateral corridor")
        if z < max(self.start_m[2], peak_z if peak_z is not None else self.start_m[2]) - (
            self.backtrack_tolerance_m
        ):
            raise ValueError("clearance descended by more than 1 mm")
        if z > self.target_m[2] + 0.005:
            raise ValueError("clearance exceeded its target height tolerance")
