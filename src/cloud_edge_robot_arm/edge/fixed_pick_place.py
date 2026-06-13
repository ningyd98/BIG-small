from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from cloud_edge_robot_arm.contracts import ActionResult


class FixedPickPlaceRobot(Protocol):
    def home(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def move_above(
        self,
        object_id: str,
        z_offset_m: float = 0.12,
        *,
        timeout_ms: int | None = None,
    ) -> ActionResult: ...

    def approach(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult: ...

    def grasp(self, object_id: str, *, timeout_ms: int | None = None) -> ActionResult: ...

    def lift(self, height_m: float = 0.15, *, timeout_ms: int | None = None) -> ActionResult: ...

    def move_to_region(self, region_id: str, *, timeout_ms: int | None = None) -> ActionResult: ...

    def place(self, region_id: str, *, timeout_ms: int | None = None) -> ActionResult: ...

    def release(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def retreat(
        self, distance_m: float = 0.1, *, timeout_ms: int | None = None
    ) -> ActionResult: ...

    def stop(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def emergency_stop(self, *, timeout_ms: int | None = None) -> ActionResult: ...

    def object_region(self, object_id: str) -> str | None: ...


@dataclass(frozen=True)
class PickPlaceSummary:
    success: bool
    adapter: str
    history: list[str]
    final_region: str | None
    results: list[ActionResult]
    failed_step_id: str | None = None
    skipped_steps: list[str] = field(default_factory=list)

    @property
    def failure_count(self) -> int:
        return sum(1 for result in self.results if not result.success)


def run_fixed_pick_place(
    robot: FixedPickPlaceRobot,
    *,
    object_id: str = "red_cube",
    target_region_id: str = "bin_a",
    timeout_ms: int = 1_000,
) -> PickPlaceSummary:
    sequence: list[tuple[str, Callable[[], ActionResult]]] = [
        ("HOME", lambda: robot.home(timeout_ms=timeout_ms)),
        ("MOVE_ABOVE", lambda: robot.move_above(object_id, timeout_ms=timeout_ms)),
        ("APPROACH", lambda: robot.approach(object_id, timeout_ms=timeout_ms)),
        ("GRASP", lambda: robot.grasp(object_id, timeout_ms=timeout_ms)),
        ("LIFT", lambda: robot.lift(0.16, timeout_ms=timeout_ms)),
        ("MOVE_TO_REGION", lambda: robot.move_to_region(target_region_id, timeout_ms=timeout_ms)),
        ("PLACE", lambda: robot.place(target_region_id, timeout_ms=timeout_ms)),
        ("RELEASE", lambda: robot.release(timeout_ms=timeout_ms)),
        ("RETREAT", lambda: robot.retreat(0.1, timeout_ms=timeout_ms)),
        ("HOME", lambda: robot.home(timeout_ms=timeout_ms)),
    ]
    results: list[ActionResult] = []
    failed_step_id: str | None = None
    skipped_steps: list[str] = []

    for index, (step_id, action) in enumerate(sequence):
        result = action()
        results.append(result)
        if result.success:
            continue

        failed_step_id = step_id
        skipped_steps = [remaining_step_id for remaining_step_id, _ in sequence[index + 1 :]]
        stop_result = robot.stop(timeout_ms=timeout_ms)
        results.append(stop_result)
        if not stop_result.success:
            results.append(robot.emergency_stop(timeout_ms=timeout_ms))
        break

    success = failed_step_id is None and all(result.success for result in results)
    return PickPlaceSummary(
        success=success,
        adapter=robot.__class__.__name__,
        history=[result.action_type for result in results],
        final_region=robot.object_region(object_id),
        results=results,
        failed_step_id=failed_step_id,
        skipped_steps=skipped_steps,
    )
