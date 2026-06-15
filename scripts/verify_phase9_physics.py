#!/usr/bin/env python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    args = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_phase9_mujoco_physics_step.py",
        "tests/test_phase9_no_pose_teleport.py",
        "tests/test_phase9_gripper_contact.py",
        "tests/test_phase9_object_slip.py",
        "tests/test_phase9_physics_sensitivity.py",
        "tests/test_phase9_sim_time.py",
    ]
    result = subprocess.run(args, check=False)
    print(json.dumps({"status": "passed" if result.returncode == 0 else "failed"}, sort_keys=True))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
