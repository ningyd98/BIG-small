#!/usr/bin/env python
"""Phase 3 安全屏障和故障场景演示或实验入口，用固定参数运行受控流程并输出可追溯结果。"""

from __future__ import annotations

import json
import sys
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
    now = datetime.now(UTC)
    task = contract(task_id=f"phase3-collision-{uuid4().hex[:8]}").model_copy(
        update={"timestamp": now, "issued_at": now, "valid_until": now + timedelta(seconds=60)}
    )
    shield = SafetyShield()
    step = task.steps[0]
    ctx = shield.context_builder.build(
        contract=task,
        step=step,
        robot_state=RobotState(connected=True, collision_detected=True),
        scene_version=task.scene_version,
        resolved_parameters=step.parameters,
        scene_updated_at=now,
        telemetry_timestamp=now,
        step_started_at_mono=0.0,
        task_started_at_mono=0.0,
    )
    result = shield.pre_check(ctx)
    collision_rules = [
        rule
        for rule in result.evaluated_rules
        if rule.rule_id == "COLLISION" and rule.reason_code == "COLLISION_DETECTED"
    ]
    payload = {
        "success": False,
        "task_id": task.task_id,
        "state": "SAFETY_STOPPED" if result.decision.value == "EMERGENCY_STOP" else "FAILED",
        "error_code": collision_rules[0].reason_code if collision_rules else None,
        "estop_active": result.decision.value == "EMERGENCY_STOP",
        "robot_stopped": result.decision.value == "EMERGENCY_STOP",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["state"] == "SAFETY_STOPPED" and payload["error_code"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
