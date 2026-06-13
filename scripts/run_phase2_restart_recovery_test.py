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
from cloud_edge_robot_arm.edge.runtime.recovery import recover_interrupted_tasks  # noqa: E402
from cloud_edge_robot_arm.repositories.sqlite import SQLiteRepository  # noqa: E402


def main() -> int:
    db_path = ROOT / "data" / "phase2_recovery.sqlite3"
    db_path.unlink(missing_ok=True)
    repository = SQLiteRepository(db_path)
    contract = build_pick_place_contract(task_id="phase2-recovery-demo")
    repository.create_task_from_contract(contract)
    repository.record_state_transition(
        task_id=contract.task_id,
        from_state="READY",
        to_state="EXECUTING",
        reason="simulated interruption",
    )
    repository.close()

    restarted_repository = SQLiteRepository(db_path)
    recovered = recover_interrupted_tasks(restarted_repository)
    task = restarted_repository.get_task(contract.task_id)
    events = restarted_repository.list_audit_events(contract.task_id)
    output = {
        "success": recovered == [contract.task_id] and task is not None and task.state == "PAUSED",
        "recovered_task_ids": recovered,
        "state": None if task is None else task.state,
        "last_audit_event": None if not events else events[-1].event_type,
        "db_path": str(db_path),
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    restarted_repository.close()
    return 0 if output["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
