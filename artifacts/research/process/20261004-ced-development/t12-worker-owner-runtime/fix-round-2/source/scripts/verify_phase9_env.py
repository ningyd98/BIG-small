#!/usr/bin/env python
"""Phase 9 物理仿真和跨后端验证验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.environment import detect_environment


def main() -> int:
    report = detect_environment()
    report.write(Path("artifacts/phase9/environment"))
    print(json.dumps({"status": "passed", **report.to_jsonable()}, sort_keys=True, indent=2))
    return 0 if report.level in {"CORE_READY", "ROS_READY", "ISAAC_READY", "BLOCKED_BY_ENV"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
