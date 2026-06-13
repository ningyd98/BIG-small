#!/usr/bin/env python3
"""Phase 4 comprehensive verification script.

Runs all Phase 4 acceptance scenarios and reports pass/fail for each.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPTS = [
    "run_phase4_api_smoke.py",
    "run_phase4_mock_plan.py",
    "run_phase4_rule_based_plan.py",
    "run_phase4_request_more_observation.py",
    "run_phase4_malformed_output_repair.py",
    "run_phase4_idempotency.py",
    "run_phase4_edge_dispatch.py",
]


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    results: dict[str, bool] = {}
    overall = True

    for name in SCRIPTS:
        path = script_dir / name
        if not path.exists():
            print(f"  {name}: SKIP (file not found)")
            results[name] = False
            overall = False
            continue

        proc = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            cwd=str(script_dir.parent),
        )
        passed = proc.returncode == 0 and "success=true" in proc.stdout
        results[name] = passed
        if not passed:
            overall = False
        status = "PASS" if passed else "FAIL"
        print(f"  {name}: {status}")
        if not passed:
            for line in proc.stderr.strip().split("\n")[-5:]:
                if line.strip():
                    print(f"    stderr: {line.strip()}")
            for line in proc.stdout.strip().split("\n")[-5:]:
                if line.strip():
                    print(f"    stdout: {line.strip()}")

    passed_count = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  Total: {passed_count}/{total} passed")

    if overall:
        print("\nPASS: Phase 4 acceptance suite passed")
        print("success=true")
        sys.exit(0)
    else:
        print("\nFAIL: Some Phase 4 acceptance scripts failed")
        print("success=false")
        sys.exit(1)


if __name__ == "__main__":
    main()
