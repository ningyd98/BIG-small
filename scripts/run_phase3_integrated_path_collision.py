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

from cloud_edge_robot_arm.edge.runtime.demo_contracts import build_pick_place_contract  # noqa: E402
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor  # noqa: E402
from cloud_edge_robot_arm.edge.safety.models import Obstacle  # noqa: E402
from cloud_edge_robot_arm.edge.safety.providers import MockSceneStateProvider  # noqa: E402
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene  # noqa: E402


def main() -> int:
    # Inject an obstacle directly on the path between HOME (0,-0.2,0.18) and the
    # MOVE_ABOVE target (0.2, 0.0, 0.14).
    obstacle = Obstacle(obstacle_id="wall", x=0.1, y=0.0, z=0.18, radius_m=0.05)
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    scene_provider = MockSceneStateProvider(robot, obstacles=[obstacle])
    contract = build_pick_place_contract(task_id=f"phase32-path-{uuid4().hex[:8]}")

    result = TaskExecutor(
        robot=robot,
        shield=SafetyShield(),
        repository=InMemoryRepository(),
        scene_provider=scene_provider,
    ).submit_contract(contract.model_dump(mode="json"))

    motion_actions = [
        a.action_type
        for a in robot.history
        if a.action_type not in ("CONNECT", "DISCONNECT", "STOP", "EMERGENCY_STOP")
    ]
    payload = {
        "success": result.success,
        "state": result.context.state.value if result.context is not None else None,
        "error_code": None if result.error is None else result.error.code,
        "motion_actions": motion_actions,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    # Must reject with zero motion (first step=HOME might execute, then PATH_COLLISION blocks).
    # Accept either FAILED or SAFETY_STOPPED as long as no MOVE_ABOVE motion.
    dangerous = [a for a in motion_actions if a in ("MOVE_ABOVE", "APPROACH", "LIFT")]
    return 0 if not result.success and not dangerous else 1


if __name__ == "__main__":
    raise SystemExit(main())
