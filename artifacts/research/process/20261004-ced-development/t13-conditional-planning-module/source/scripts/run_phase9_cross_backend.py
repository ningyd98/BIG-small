#!/usr/bin/env python
"""Phase 9 物理仿真和跨后端验证演示或实验入口，用固定参数运行受控流程并输出可追溯结果。"""

from __future__ import annotations

import json

from cloud_edge_robot_arm.simulation.environment import detect_environment
from cloud_edge_robot_arm.simulation.evaluation.cross_backend import compare_backend_results


def main() -> int:
    env = detect_environment()
    print(
        json.dumps(
            compare_backend_results(
                scenario_id="S01_NORMAL_STATIC", seed=0, isaac_ready=env.level == "ISAAC_READY"
            ),
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
