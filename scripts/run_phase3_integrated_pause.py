#!/usr/bin/env python
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import time  # noqa: E402

from tests.phase2_helpers import contract  # noqa: E402

from cloud_edge_robot_arm.edge.safety.models import SafetyContext  # noqa: E402
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402


def main() -> int:
    shield = SafetyShield()
    c = contract(task_id=f"phase31-pause-{uuid4().hex[:8]}")
    now = datetime.now(UTC)
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-home",
        skill="HOME",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=-0.2,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=None,
        telemetry_timestamp=None,
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=now,
        task_deadline_utc=c.valid_until,
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    payload = {
        "allowed": result.allowed,
        "decision": result.decision.value,
        "is_pause": result.decision.value == "PAUSE",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not result.allowed and payload["is_pause"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
