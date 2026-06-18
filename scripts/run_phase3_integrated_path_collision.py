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

from tests.phase2_helpers import contract, step  # noqa: E402

from cloud_edge_robot_arm.contracts import Pose, RobotState, SkillName  # noqa: E402
from cloud_edge_robot_arm.edge.safety.models import Obstacle  # noqa: E402
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402


def main() -> int:
    issued = datetime.now(UTC)
    task_step = step(
        "step-move-above",
        SkillName.MOVE_ABOVE,
        parameters={"object_id": "red_cube", "z_offset_m": 0.12},
        retry_limit=0,
    )
    task = contract(task_id=f"phase32-path-{uuid4().hex[:8]}", steps=[task_step]).model_copy(
        update={
            "timestamp": issued,
            "issued_at": issued,
            "valid_until": issued + timedelta(seconds=30),
        }
    )
    shield = SafetyShield()
    obstacle = Obstacle(obstacle_id="wall", x=0.1, y=-0.1, z=0.18, radius_m=0.08)
    ctx = shield.context_builder.build(
        contract=task,
        step=task_step,
        robot_state=RobotState(connected=True, tcp_pose=Pose(x=0.0, y=-0.2, z=0.18)),
        scene_version=1,
        resolved_parameters={"target_pose": {"x": 0.2, "y": 0.0, "z": 0.14}},
        scene_updated_at=issued,
        telemetry_timestamp=issued,
        step_started_at_mono=0.0,
        task_started_at_mono=0.0,
        obstacles=[obstacle],
        wall_clock_now=issued,
    )
    result = shield.pre_check(ctx)
    path_rules = [r for r in result.evaluated_rules if r.rule_id == "PATH_COLLISION"]
    payload: dict[str, object] = {
        "success": result.allowed,
        "state": "FAILED" if not result.allowed else "COMPLETED",
        "error_code": path_rules[0].reason_code if path_rules else None,
        "motion_actions": [],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not result.allowed and payload["error_code"] == "PATH_COLLISION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
