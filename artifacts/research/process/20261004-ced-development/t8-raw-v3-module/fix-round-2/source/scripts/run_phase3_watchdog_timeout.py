#!/usr/bin/env python
"""Phase 3 安全屏障和故障场景演示或实验入口，用固定参数运行受控流程并输出可追溯结果。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datetime import UTC, datetime  # noqa: E402

from tests.phase2_helpers import contract  # noqa: E402

from cloud_edge_robot_arm.contracts import SafetyDecision  # noqa: E402
from cloud_edge_robot_arm.edge.safety.models import SafetyContext  # noqa: E402
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402


def main() -> int:
    shield = SafetyShield()
    c = contract(task_id=f"phase3-watchdog-{uuid4().hex[:8]}")
    now = datetime.now(UTC)
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-home",
        skill="HOME",
        contract=c,
        robot_connected=True,
        scene_version=1,
        scene_updated_at=now,
        telemetry_timestamp=now,
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=now,
        task_deadline_utc=c.valid_until,
        task_started_at_mono=time.monotonic() - 60,
    )

    result = shield.pre_check(ctx)
    watchdog_rules = [r for r in result.evaluated_rules if r.rule_id == "WATCHDOG"]
    payload = {
        "allowed": result.allowed,
        "decision": result.decision.value,
        "watchdog_triggered": any(
            r.decision == SafetyDecision.EMERGENCY_STOP for r in watchdog_rules
        ),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not result.allowed and payload["watchdog_triggered"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
