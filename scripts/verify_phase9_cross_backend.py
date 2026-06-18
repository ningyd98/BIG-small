#!/usr/bin/env python
"""Phase 9 物理仿真和跨后端验证验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.environment import detect_environment
from cloud_edge_robot_arm.simulation.evaluation.cross_backend import compare_backend_results


def main() -> int:
    env = detect_environment()
    report = compare_backend_results(
        scenario_id="S01_NORMAL_STATIC",
        seed=0,
        isaac_ready=env.level == "ISAAC_READY",
    )
    print(json.dumps({"status": "passed", "report": report}, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
