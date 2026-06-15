#!/usr/bin/env python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.environment import detect_environment

CORE_CHECKS = [
    [sys.executable, "scripts/verify_phase8_2.py"],
    [sys.executable, "scripts/verify_phase9_env.py"],
    [sys.executable, "scripts/verify_phase9_mujoco.py"],
    [sys.executable, "scripts/verify_phase9_physics.py"],
    [sys.executable, "scripts/verify_phase9_safety.py"],
    [sys.executable, "scripts/verify_phase9_randomization.py"],
    [sys.executable, "scripts/verify_phase9_cross_backend.py"],
    [sys.executable, "scripts/verify_phase9_artifacts.py"],
]


def main() -> int:
    checks: list[dict[str, object]] = []
    summary: dict[str, object] = {"checks": checks}
    failed = False
    for command in CORE_CHECKS:
        result = subprocess.run(command, check=False, text=True, capture_output=True)
        item = {
            "command": " ".join(command),
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:],
        }
        checks.append(item)
        if result.returncode != 0:
            failed = True
    env = detect_environment()
    ros = subprocess.run(
        [sys.executable, "scripts/verify_phase9_ros2.py"],
        check=False,
        text=True,
        capture_output=True,
    )
    isaac = subprocess.run(
        [sys.executable, "scripts/verify_phase9_isaac.py"],
        check=False,
        text=True,
        capture_output=True,
    )
    summary["environment_level"] = env.level
    summary["ros2"] = {"returncode": ros.returncode, "stdout": ros.stdout[-2000:]}
    summary["isaac"] = {"returncode": isaac.returncode, "stdout": isaac.stdout[-2000:]}
    summary["acceptance_status"] = (
        "PHASE9_FULL_ACCEPTED"
        if not failed
        and env.level == "ISAAC_READY"
        and ros.returncode == 0
        and isaac.returncode == 0
        else "PHASE9_CORE_ACCEPTED_ISAAC_VALIDATION_BLOCKED_BY_ENV"
        if not failed
        else "FAILED"
    )
    output = Path("artifacts/phase9/verify_phase9_summary.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
