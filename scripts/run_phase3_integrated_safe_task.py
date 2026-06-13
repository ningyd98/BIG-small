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
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene  # noqa: E402


def main() -> int:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    repository = InMemoryRepository()
    shield = SafetyShield()
    contract = build_pick_place_contract(task_id=f"phase31-safe-{uuid4().hex[:8]}")
    result = TaskExecutor(robot=robot, shield=shield, repository=repository).submit_contract(
        contract.model_dump(mode="json")
    )
    payload = {
        "success": result.success,
        "task_id": contract.task_id,
        "state": result.context.state.value if result.context is not None else None,
        "completed_step_count": len(result.context.completed_step_ids)
        if result.context is not None
        else 0,
        "error_code": None if result.error is None else result.error.code,
        "shield_injected": shield is not None,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    repository.close()
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
