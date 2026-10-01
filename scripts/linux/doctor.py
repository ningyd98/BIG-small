#!/usr/bin/env python3
"""只读 Linux 部署 doctor，依赖可用性不等于 runtime 验收。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def probe(name: str, command: list[str], missing: str = "BLOCKED") -> dict[str, Any]:
    """执行有限时长只读探针，保存退出码并区分缺失依赖。"""
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=30, cwd=ROOT)
        return {
            "name": name,
            "status": "PASS" if result.returncode == 0 else missing,
            "scope": "availability only",
            "command": command,
            "exit_code": result.returncode,
            "output": (result.stdout + result.stderr)[-4000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": name, "status": missing, "scope": "availability only", "error": str(exc)}


def main() -> int:
    """报告核心环境、外部 runtime、磁盘和无硬件执行的边界。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    checks = [
        probe("Git", ["git", "status", "--short"], "FAIL"),
        probe("Python", [sys.executable, "--version"], "FAIL"),
        probe(
            "Python env",
            [sys.executable, "-c", "import sys; assert sys.prefix != sys.base_prefix"],
            "FAIL",
        ),
        probe("Package", [sys.executable, "-c", "import cloud_edge_robot_arm"], "FAIL"),
        probe("Dependencies", [sys.executable, "-m", "pip", "check"], "FAIL"),
        probe(
            "MuJoCo",
            [
                sys.executable,
                "-c",
                "import mujoco; "
                "m=mujoco.MjModel.from_xml_path('assets/robots/franka_panda/scene.xml'); "
                "d=mujoco.MjData(m); mujoco.mj_step(m,d); "
                "print(mujoco.__version__,d.time)",
            ],
        ),
        probe(
            "Node",
            [
                "node",
                "-e",
                "const [a,b]=process.versions.node.split('.').map(Number); "
                "if(a<22||(a===22&&b<12))process.exit(1);console.log(process.versions.node)",
            ],
        ),
        probe(
            "Dashboard",
            [
                "node",
                "-e",
                "import('./dashboard/node_modules/vite/package.json',{with:{type:'json'}}).then(x=>console.log(x.default.version))",
            ],
        ),
        probe(
            "NVIDIA",
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
        ),
        probe("ROS2", ["ros2", "--help"]),
        probe("MoveIt", [sys.executable, "-c", "import moveit_configs_utils, rclpy"]),
        probe("Rerun", [sys.executable, "-c", "import rerun; print(rerun.__version__)"]),
        probe("Ollama", ["ollama", "list"]),
        probe("Docker", ["docker", "info", "--format", "{{.ServerVersion}}"]),
        probe("Disk", ["df", "-h", str(ROOT)]),
    ]
    isaac_root = os.environ.get("ISAAC_SIM_ROOT", "")
    checks.append(
        {
            "name": "Isaac",
            "status": "WARN" if isaac_root and Path(isaac_root).exists() else "BLOCKED",
            "scope": "configured path only; run verify_phase9_2_isaac_smoke.py for acceptance",
        }
    )
    directories = ["artifacts", "cache", "logs", "datasets", "results"]
    checks.append(
        {
            "name": "Artifact directories",
            "status": "PASS" if all((ROOT / x).is_dir() for x in directories) else "WARN",
            "directories": directories,
        }
    )
    safety_ok = (
        os.environ.get("RUNTIME_PROFILE") == "simulation"
        and os.environ.get("REAL_MOTION_DISPATCH_ENABLED") == "false"
    )
    checks.append(
        {
            "name": "Safety boundary",
            "status": "PASS" if safety_ok else "FAIL",
            "scope": "launcher configuration; no hardware probe",
            "real_motion_dispatch_enabled": False if safety_ok else "UNKNOWN",
        }
    )
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "python": sys.executable,
        "checks": checks,
        "note": "BLOCKED is never PASS. Availability does not imply runtime acceptance.",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 1 if any(c["status"] == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
