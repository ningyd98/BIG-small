#!/usr/bin/env python
"""仓库回归演示或实验入口，用固定参数运行受控流程并输出可追溯结果。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.contracts import Pose  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import (  # noqa: E402
    FaultCode,
    MockRobotAdapter,
    MockScene,
)


def _execute_fault(fault: FaultCode) -> dict[str, object]:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.inject_fault(fault)
    if fault in {FaultCode.GRASP_FAILED, FaultCode.OBJECT_DROPPED}:
        robot.move_above("red_cube")
        robot.approach("red_cube")
    if fault == FaultCode.OBJECT_DROPPED:
        robot.grasp("red_cube")
    if fault == FaultCode.TARGET_UNREACHABLE:
        result = robot.move_above("red_cube")
    elif fault == FaultCode.GRASP_FAILED:
        result = robot.grasp("red_cube")
    elif fault == FaultCode.OBJECT_DROPPED:
        result = robot.lift(0.1)
    elif fault == FaultCode.INVALID_TARGET_POSE:
        result = robot.move_to_pose(Pose(x=0.1, y=0.0, z=0.1))
    else:
        result = robot.home()
    return {
        "fault": fault.value,
        "successfully_rejected": result.success is False,
        "error_code": result.error_code,
        "action_type": result.action_type,
    }


def main() -> int:
    results = [_execute_fault(fault) for fault in FaultCode]
    success = all(
        item["successfully_rejected"] and item["error_code"] == item["fault"] for item in results
    )
    print(json.dumps({"success": success, "results": results}, indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
