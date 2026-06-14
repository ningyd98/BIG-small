#!/usr/bin/env python
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

from cloud_edge_robot_arm.contracts import (  # noqa: E402
    ControlMode,
    FailurePolicy,
    Pose,
    RobotState,
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402


def main() -> int:
    issued = datetime.now(UTC)
    step = TaskStep(
        step_id="step-move",
        skill=SkillName.MOVE_ABOVE,
        parameters={"object_id": "red_cube", "z_offset_m": 0.12},
        expected_duration_ms=10,
        timeout_ms=1_000,
        retry_limit=0,
    )
    contract = TaskContract(
        task_id=f"phase32-ws-{uuid4().hex[:8]}",
        plan_version=1,
        command_seq=1,
        timestamp=issued,
        control_mode=ControlMode.EVENT_TRIGGERED_EDGE_AUTONOMY,
        issued_at=issued,
        valid_until=issued + timedelta(seconds=30),
        user_instruction="move above out-of-bounds object",
        scene_version=1,
        expected_scene_version=1,
        task_target=TaskTarget(object_id="red_cube", object_class="cube", target_region_id="bin_a"),
        steps=[step],
        safety_constraints=SafetyConstraints(
            max_joint_velocity=0.5,
            max_tcp_velocity=0.15,
            minimum_safe_height=0.08,
            workspace_id="workspace_a",
            collision_check_required=True,
        ),
        failure_policy=FailurePolicy(
            local_retry_limit=0,
            on_timeout="SAFE_STOP",
            on_safety_rejection="PAUSE_AND_REPORT",
            on_network_loss="SAFE_STOP",
        ),
        completion_criteria=["tcp_above_target"],
    )
    shield = SafetyShield()
    ctx = shield.context_builder.build(
        contract=contract,
        step=step,
        robot_state=RobotState(connected=True, tcp_pose=Pose(x=0.0, y=0.0, z=0.18)),
        scene_version=1,
        resolved_parameters={"target_pose": {"x": 1.0, "y": 0.0, "z": 0.14}},
        scene_updated_at=issued,
        telemetry_timestamp=issued,
        step_started_at_mono=0.0,
        task_started_at_mono=0.0,
        wall_clock_now=issued,
    )
    result = shield.pre_check(ctx)
    workspace = [r for r in result.evaluated_rules if r.rule_id == "WORKSPACE"]
    payload = {
        "success": result.allowed,
        "state": "FAILED" if not result.allowed else "COMPLETED",
        "error_code": workspace[0].reason_code if workspace else None,
        "motion_actions": [],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not result.allowed and payload["error_code"] == "WORKSPACE_VIOLATION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
