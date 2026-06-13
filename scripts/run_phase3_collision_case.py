#!/usr/bin/env python
from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.phase2_helpers import contract  # noqa: E402

from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor  # noqa: E402
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import (  # noqa: E402
    FaultCode,
    MockRobotAdapter,
    MockScene,
)


def main() -> int:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.inject_fault(FaultCode.COLLISION_DETECTED)

    result = TaskExecutor(robot=robot, repository=InMemoryRepository()).submit_contract(
        contract(task_id=f"phase3-collision-{uuid4().hex[:8]}").model_dump(mode="json")
    )

    payload = {
        "success": result.success,
        "task_id": result.context.task_id if result.context is not None else None,
        "state": result.context.state.value if result.context is not None else None,
        "error_code": None if result.error is None else result.error.code,
        "estop_active": robot.get_state().estop_engaged,
        "robot_stopped": robot.get_state().stopped,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return (
        0
        if not result.success
        and result.context is not None
        and result.context.state == "SAFETY_STOPPED"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
