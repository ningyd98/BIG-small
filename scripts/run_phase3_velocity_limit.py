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

from cloud_edge_robot_arm.edge.runtime.demo_contracts import build_pick_place_contract  # noqa: E402
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor  # noqa: E402
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene  # noqa: E402


def main() -> int:
    robot = MockRobotAdapter(
        scene=MockScene.with_default_pick_place_scene(),
        auto_connect=True,
        default_action_duration_ms=50,
    )
    contract = build_pick_place_contract(
        task_id=f"phase3-velocity-{uuid4().hex[:8]}",
        local_retry_limit=0,
    )
    result = TaskExecutor(robot=robot, repository=InMemoryRepository()).submit_contract(
        contract.model_dump(mode="json")
    )
    payload = {
        "success": result.success,
        "task_id": contract.task_id,
        "state": result.context.state.value if result.context is not None else None,
        "error_code": None if result.error is None else result.error.code,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
