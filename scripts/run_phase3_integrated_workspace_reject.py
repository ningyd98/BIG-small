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
    SafetyConstraints,
    SkillName,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor  # noqa: E402
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import (  # noqa: E402
    MockRobotAdapter,
    MockScene,
    SceneObject,
    TargetRegion,
)


def main() -> int:
    # Place the object outside the workspace so the resolved target violates bounds.
    scene = MockScene(
        objects={
            "red_cube": SceneObject(
                object_id="red_cube",
                object_class="cube",
                pose=Pose(x=1.0, y=0.0, z=0.02),
                region_id="table",
            )
        },
        regions={
            "bin_a": TargetRegion(region_id="bin_a", center=Pose(x=-0.2, y=0.18, z=0.02)),
        },
    )
    robot = MockRobotAdapter(scene=scene, auto_connect=True)
    issued = datetime.now(UTC)
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
        steps=[
            TaskStep(
                step_id="step-move",
                skill=SkillName.MOVE_ABOVE,
                parameters={"object_id": "red_cube", "z_offset_m": 0.12},
                expected_duration_ms=10,
                timeout_ms=1_000,
                retry_limit=0,
            ),
        ],
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

    result = TaskExecutor(
        robot=robot,
        shield=SafetyShield(),
        repository=InMemoryRepository(),
    ).submit_contract(contract.model_dump(mode="json"))

    motion_actions = [
        a.action_type
        for a in robot.history
        if a.action_type not in ("CONNECT", "DISCONNECT", "STOP", "EMERGENCY_STOP")
    ]
    payload = {
        "success": result.success,
        "state": result.context.state.value if result.context is not None else None,
        "error_code": None if result.error is None else result.error.code,
        "motion_actions": motion_actions,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    # Must reject with FAILED and zero motion.
    return 0 if not result.success and payload["state"] == "FAILED" and not motion_actions else 1


if __name__ == "__main__":
    raise SystemExit(main())
