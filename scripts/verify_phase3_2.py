#!/usr/bin/env python
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


def _check_no_manual_safety_context(script: str) -> bool:
    """Verify the script does NOT contain a manual SafetyContext construction."""
    text = (ROOT / script).read_text()
    return "SafetyContext(" not in text


def main() -> int:
    scripts = [
        "run_phase3_integrated_safe_task.py",
        "run_phase3_integrated_workspace_reject.py",
        "run_phase3_integrated_path_collision.py",
        "run_phase3_integrated_pause.py",
        "run_phase3_integrated_emergency_stop.py",
        "run_phase3_integrated_velocity_limit.py",
        "run_phase3_integrated_stale_telemetry.py",
    ]

    # 1) Verify no manual SafetyContext in any integration script.
    all_clean = True
    for script in scripts:
        clean = _check_no_manual_safety_context(f"scripts/{script}")
        if not clean:
            print(f"FAIL: {script} contains manual SafetyContext construction")
            all_clean = False

    # 2) Run all verification scripts.
    commands = [[sys.executable, f"scripts/{s}"] for s in scripts]
    results = [_run(command) for command in commands]
    scripts_ok = all(r["returncode"] == 0 for r in results)

    success = all_clean and scripts_ok
    print(
        json.dumps(
            {
                "success": success,
                "no_manual_safety_context": all_clean,
                "scripts_ok": scripts_ok,
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
