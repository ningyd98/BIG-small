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

from cloud_edge_robot_arm.edge.safety.models import Obstacle, SafetyContext  # noqa: E402
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402


def main() -> int:
    shield = SafetyShield()
    c = contract(task_id=f"phase31-path-{uuid4().hex[:8]}")
    now = datetime.now(UTC)
    obs = Obstacle(obstacle_id="wall", x=0.1, y=0.0, z=0.18, radius_m=0.05)
    ctx = SafetyContext(
        task_id=c.task_id,
        plan_version=c.plan_version,
        command_seq=c.command_seq,
        step_id="step-move",
        skill="MOVE_ABOVE",
        contract=c,
        robot_connected=True,
        tcp_x=0.0,
        tcp_y=0.0,
        tcp_z=0.18,
        scene_version=1,
        scene_updated_at=now,
        telemetry_timestamp=now,
        command_issued_at=c.issued_at,
        command_valid_until=c.valid_until,
        wall_clock_now=now,
        task_deadline_utc=c.valid_until,
        obstacles=[obs],
        parameters={"object_id": "red_cube", "target_pose": {"x": 0.2, "y": 0.0, "z": 0.3}},
        step_started_at=time.monotonic(),
        task_started_at_mono=time.monotonic(),
    )
    result = shield.pre_check(ctx)
    path_rules = [r for r in result.evaluated_rules if r.rule_id == "PATH_COLLISION"]
    payload = {
        "allowed": result.allowed,
        "decision": result.decision.value,
        "path_collision_blocked": any(r.decision.value == "REJECT" for r in path_rules),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not result.allowed and payload["path_collision_blocked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
