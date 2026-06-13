#!/usr/bin/env python
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.edge.runtime.demo_contracts import build_pick_place_contract  # noqa: E402
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor  # noqa: E402
from cloud_edge_robot_arm.repositories.sqlite import SQLiteRepository  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene  # noqa: E402


def main() -> int:
    db_path = ROOT / "data" / "phase2_replay.sqlite3"
    db_path.unlink(missing_ok=True)
    repository = SQLiteRepository(db_path)
    contract = build_pick_place_contract(task_id="phase2-replay-demo")
    payload = contract.model_dump(mode="json")
    first = TaskExecutor(
        robot=MockRobotAdapter(scene=MockScene.with_default_pick_place_scene()),
        repository=repository,
    ).submit_contract(payload)
    replay = TaskExecutor(
        robot=MockRobotAdapter(scene=MockScene.with_default_pick_place_scene()),
        repository=repository,
    ).submit_contract(payload)
    conflict_payload = dict(payload)
    conflict_payload["user_instruction"] = "changed payload with same command_seq"
    conflict = TaskExecutor(
        robot=MockRobotAdapter(scene=MockScene.with_default_pick_place_scene()),
        repository=repository,
    ).submit_contract(conflict_payload)

    output = {
        "first_success": first.success,
        "replay_success": replay.success,
        "replay_error_code": None if replay.error is None else replay.error.code,
        "conflict_success": conflict.success,
        "conflict_error_code": None if conflict.error is None else conflict.error.code,
        "db_path": str(db_path),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    repository.close()
    return (
        0
        if (
            first.success
            and not replay.success
            and replay.error is not None
            and replay.error.code == "COMMAND_SEQ_REPLAYED"
            and not conflict.success
            and conflict.error is not None
            and conflict.error.code == "COMMAND_SEQ_CONFLICT"
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
