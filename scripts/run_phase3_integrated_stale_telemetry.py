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
    contract = build_pick_place_contract(task_id=f"phase32-stale-{uuid4().hex[:8]}")

    # Telemetry is stale (older than the 5000ms default staleness limit).
    tel_provider = MockTelemetryProvider(stale_ms=10_000)

    result = TaskExecutor(
        robot=robot,
        shield=SafetyShield(),
        repository=InMemoryRepository(),
        telemetry_provider=tel_provider,
    ).submit_contract(contract.model_dump(mode="json"))

    payload = {
        "success": result.success,
        "state": result.context.state.value if result.context is not None else None,
        "error_code": None if result.error is None else result.error.code,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    # Stale telemetry → PAUSE.
    return 0 if not result.success and payload["state"] == "PAUSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
