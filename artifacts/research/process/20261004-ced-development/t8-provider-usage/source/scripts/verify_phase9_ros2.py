#!/usr/bin/env python
"""Phase 9 物理仿真和跨后端验证验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.ros2.bridge_client import Ros2BridgeClient


def main() -> int:
    tests = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_phase9_ros2_conversion.py",
            "tests/test_phase9_ros2_qos.py",
        ],
        check=False,
    )
    bridge = Ros2BridgeClient().check_status()
    status = (
        "ROS_READY" if bridge.status == "ROS_READY" and tests.returncode == 0 else "BLOCKED_BY_ENV"
    )
    print(json.dumps({"status": status, "blockers": bridge.blockers}, sort_keys=True, indent=2))
    return 0 if tests.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
