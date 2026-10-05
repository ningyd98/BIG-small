#!/usr/bin/env python
"""Phase 9 物理仿真和跨后端验证验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.evaluation.metrics import run_mujoco_physical_trial


def main() -> int:
    trials = [
        run_mujoco_physical_trial("S01_NORMAL_STATIC", seed=i, randomization_level="NONE")
        for i in range(20)
    ]
    success_rate = sum(
        1 for trial in trials if trial.metrics["illegal_collision_count"] == 0
    ) / len(trials)
    tests = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_phase9_mujoco_load.py",
            "tests/test_phase9_mujoco_physics_step.py",
            "tests/test_phase9_no_pose_teleport.py",
            "tests/test_phase9_joint_control.py",
        ],
        check=False,
    )
    payload = {
        "status": "passed" if success_rate == 1.0 and tests.returncode == 0 else "failed",
        "normal_static_trials": len(trials),
        "normal_static_success_rate": success_rate,
        "result_hashes": [trial.result_hash for trial in trials],
    }
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
