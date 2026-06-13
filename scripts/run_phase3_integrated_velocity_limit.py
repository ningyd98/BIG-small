#!/usr/bin/env python
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

from cloud_edge_robot_arm.edge.runtime.demo_contracts import build_pick_place_contract  # noqa: E402
from cloud_edge_robot_arm.edge.runtime.task_executor import TaskExecutor  # noqa: E402
from cloud_edge_robot_arm.edge.safety.providers import MockTelemetryProvider  # noqa: E402
from cloud_edge_robot_arm.edge.safety.shield import SafetyShield  # noqa: E402
from cloud_edge_robot_arm.repositories.memory import InMemoryRepository  # noqa: E402
from cloud_edge_robot_arm.simulation.mock_robot import MockRobotAdapter, MockScene  # noqa: E402


def main() -> int:
    robot = MockRobotAdapter(scene=MockScene.with_default_pick_place_scene(), auto_connect=True)
    contract = build_pick_place_contract(
        task_id=f"phase32-velocity-{uuid4().hex[:8]}",
        local_retry_limit=0,
    )

    # Telemetry reports a velocity (0.4) that exceeds the merged limit (0.15 from contract)
    # but is within the absolute max (1.0 from hard limits) → ALLOW_WITH_LIMITS.
    tel_provider = MockTelemetryProvider(tcp_velocity=0.4)

    result = TaskExecutor(
        robot=robot,
        shield=SafetyShield(),
        repository=InMemoryRepository(),
        telemetry_provider=tel_provider,
    ).submit_contract(contract.model_dump(mode="json"))

    # Check that the executed HOME step recorded the (limited) velocity.
    limited_executed = False
    for entry in robot.history:
        details = entry.details or {}
        if "executed_tcp_velocity" in details:
            limited_executed = True
            break
    payload = {
        "success": result.success,
        "state": result.context.state.value if result.context is not None else None,
        "limited_executed": limited_executed,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if result.success and limited_executed else 1


if __name__ == "__main__":
    raise SystemExit(main())
