#!/usr/bin/env python
"""Phase 2 任务运行时和恢复演示或实验入口，用固定参数运行受控流程并输出可追溯结果。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.edge.runtime.demo_contracts import build_pick_place_contract  # noqa: E402
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor  # noqa: E402
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import (  # noqa: E402
    FaultCode,
    MockRobotAdapter,
    MockScene,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fault", choices=[fault.value for fault in FaultCode], required=True)
    args = parser.parse_args()

    fault = FaultCode(args.fault)
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    robot.inject_fault(fault)
    contract = build_pick_place_contract(
        task_id=f"phase2-failure-{uuid4().hex[:8]}",
        local_retry_limit=0,
    )
    result = TaskExecutor(
        robot=robot, shield=SafetyShield(), repository=InMemoryRepository()
    ).submit_contract(contract.model_dump(mode="json"))
    payload = {
        "success": result.success,
        "fault": fault.value,
        "state": result.context.state.value if result.context is not None else None,
        "failed_step_id": result.context.failed_step_id if result.context is not None else None,
        "error_code": None if result.error is None else result.error.code,
        "executed_actions": [entry.action_type for entry in robot.history],
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not result.success and result.error is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
