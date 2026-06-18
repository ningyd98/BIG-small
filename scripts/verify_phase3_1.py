#!/usr/bin/env python
"""Phase 3.1 集成安全路径验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def main() -> int:
    commands = [
        [sys.executable, "scripts/run_phase3_integrated_safe_task.py"],
        [sys.executable, "scripts/run_phase3_integrated_workspace_reject.py"],
        [sys.executable, "scripts/run_phase3_integrated_path_collision.py"],
        [sys.executable, "scripts/run_phase3_integrated_pause.py"],
        [sys.executable, "scripts/run_phase3_integrated_emergency_stop.py"],
    ]
    results = [_run(command) for command in commands]
    success = all(result["returncode"] == 0 for result in results)
    print(json.dumps({"success": success, "results": results}, indent=2, ensure_ascii=False))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
