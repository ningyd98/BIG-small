#!/usr/bin/env python
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.phase2_helpers import contract  # noqa: E402

from cloud_edge_robot_arm.contracts import RobotState  # noqa: E402
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402


def main() -> int:
    issued = datetime.now(UTC)
    task = contract(task_id=f"phase32-pause-{uuid4().hex[:8]}").model_copy(
        update={
            "timestamp": issued,
            "issued_at": issued,
            "valid_until": issued + timedelta(seconds=30),
        }
    )
    step = task.steps[0]
    shield = SafetyShield()
    ctx = shield.context_builder.build(
        contract=task,
        step=step,
        robot_state=RobotState(connected=True),
        scene_version=1,
        resolved_parameters=step.parameters,
        scene_updated_at=issued,
        telemetry_timestamp=None,
        step_started_at_mono=time.monotonic(),
        task_started_at_mono=time.monotonic(),
        wall_clock_now=issued,
    )
    result = shield.pre_check(ctx)
    payload = {
        "success": result.allowed,
        "state": "PAUSED" if result.decision.value == "PAUSE" else "FAILED",
        "error_code": result.limiting_rule.reason_code if result.limiting_rule else None,
        "motion_actions": [],
        "is_pause": result.decision.value == "PAUSE",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["is_pause"] and not payload["motion_actions"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
