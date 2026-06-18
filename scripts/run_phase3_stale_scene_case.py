#!/usr/bin/env python
"""Phase 3 安全屏障和故障场景演示或实验入口，用固定参数运行受控流程并输出可追溯结果。"""

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

from datetime import UTC, datetime, timedelta  # noqa: E402

from tests.phase2_helpers import contract  # noqa: E402

from cloud_edge_robot_arm.edge.safety.models import SafetyContext  # noqa: E402
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402


def main() -> int:
    shield = SafetyShield()
    c = contract(task_id=f"phase3-stale-{uuid4().hex[:8]}")
    now = datetime.now(UTC)
    stale_time = now - timedelta(seconds=10)
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-home",
        skill="HOME",
        contract=c,
        robot_connected=True,
        scene_version=1,
        scene_updated_at=stale_time,
        telemetry_timestamp=stale_time,
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=now,
        task_deadline_utc=c.valid_until,
    )

    result = shield.pre_check(ctx)
    payload = {
        "allowed": result.allowed,
        "decision": result.decision.value,
        "stale_rules": [
            r.rule_id
            for r in result.evaluated_rules
            if r.decision.value not in ("ALLOW", "ALLOW_WITH_LIMITS")
        ],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not result.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
