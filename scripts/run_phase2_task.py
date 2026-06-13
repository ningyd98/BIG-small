#!/usr/bin/env python
from __future__ import annotations

import argparse
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
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository  # noqa: E402
from cloud_edge_robot_arm.repositories.sqlite import SQLiteRepository  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", choices=["memory", "sqlite"], default="memory")
    parser.add_argument("--db-path", default=str(ROOT / "data" / "phase2_task.sqlite3"))
    args = parser.parse_args()

    repository = (
        SQLiteRepository(args.db_path) if args.repository == "sqlite" else InMemoryRepository()
    )
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    contract = build_pick_place_contract(task_id=f"phase2-task-{uuid4().hex[:8]}")
    result = TaskExecutor(
        robot=robot, shield=SafetyShield(), repository=repository
    ).submit_contract(contract.model_dump(mode="json"))
    payload = {
        "success": result.success,
        "repository": args.repository,
        "task_id": contract.task_id,
        "state": result.context.state.value if result.context is not None else None,
        "completed_step_count": len(result.context.completed_step_ids)
        if result.context is not None
        else 0,
        "final_region": robot.object_region("red_cube"),
        "step_attempts": result.context.step_attempts if result.context is not None else {},
        "error_code": None if result.error is None else result.error.code,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    repository.close()
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
