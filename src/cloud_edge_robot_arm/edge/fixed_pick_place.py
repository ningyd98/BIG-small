from __future__ import annotations

from dataclasses import dataclass

from cloud_edge_robot_arm.contracts import ActionResult
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter


@dataclass(frozen=True)
class PickPlaceSummary:
    success: bool
    adapter: str
    history: list[str]
    final_region: str | None
    results: list[ActionResult]

    @property
    def failure_count(self) -> int:
        return sum(1 for result in self.results if not result.success)


def run_fixed_pick_place(
    robot: MockRobotAdapter,
    *,
    object_id: str = "red_cube",
    target_region_id: str = "bin_a",
    timeout_ms: int = 1_000,
) -> PickPlaceSummary:
    results = [
        robot.home(timeout_ms=timeout_ms),
        robot.move_above(object_id, timeout_ms=timeout_ms),
        robot.approach(object_id, timeout_ms=timeout_ms),
        robot.grasp(object_id, timeout_ms=timeout_ms),
        robot.lift(0.16, timeout_ms=timeout_ms),
        robot.move_to_region(target_region_id, timeout_ms=timeout_ms),
        robot.place(target_region_id, timeout_ms=timeout_ms),
        robot.release(timeout_ms=timeout_ms),
        robot.retreat(0.1, timeout_ms=timeout_ms),
        robot.home(timeout_ms=timeout_ms),
    ]
    success = all(result.success for result in results)
    return PickPlaceSummary(
        success=success,
        adapter=robot.__class__.__name__,
        history=[result.action_type for result in results],
        final_region=robot.object_region(object_id),
        results=results,
    )
