#!/usr/bin/env python
"""Phase 9 物理仿真和跨后端验证验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_phase9_domain_randomization.py",
            "tests/test_phase9_seed_reproducibility.py",
            "tests/test_phase9_sensor_noise.py",
        ],
        check=False,
    )
    print(json.dumps({"status": "passed" if result.returncode == 0 else "failed"}, sort_keys=True))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
