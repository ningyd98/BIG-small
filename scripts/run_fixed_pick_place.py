#!/usr/bin/env python
"""仓库回归演示或实验入口，用固定参数运行受控流程并输出可追溯结果。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.edge.fixed_pick_place import run_fixed_pick_place  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene  # noqa: E402


def run_mock_repeat(repeat: int) -> dict[str, object]:
    successes = 0
    histories: list[list[str]] = []
    lifecycle_histories: list[list[str]] = []
    final_regions: list[str | None] = []
    for _ in range(repeat):
        robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene())
        lifecycle_results = [robot.connect()]
        summary = run_fixed_pick_place(robot) if lifecycle_results[0].success else None
        lifecycle_results.append(robot.disconnect())
        task_success = (
            summary is not None
            and lifecycle_results[0].success
            and summary.success
            and lifecycle_results[-1].success
        )
        successes += int(task_success)
        histories.append(summary.history if summary is not None else [])
        lifecycle_histories.append([result.action_type for result in lifecycle_results])
        final_regions.append(summary.final_region if summary is not None else None)
    return {
        "adapter": "mock",
        "repeat": repeat,
        "successes": successes,
        "failures": repeat - successes,
        "success_rate": successes / repeat if repeat else 0.0,
        "final_regions": final_regions,
        "history": histories[-1] if histories else [],
        "lifecycle_history": lifecycle_histories[-1] if lifecycle_histories else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", choices=["mock"], required=True)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    payload = run_mock_repeat(args.repeat)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["successes"] == args.repeat else 1


if __name__ == "__main__":
    raise SystemExit(main())
