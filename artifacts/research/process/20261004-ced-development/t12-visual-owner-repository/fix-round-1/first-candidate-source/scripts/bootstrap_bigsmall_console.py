#!/usr/bin/env python
"""Bootstrap BIG-small Console dependencies without writing secrets.

默认只检查环境；只有显式传入 ``--install`` 才会执行可重复的本地安装步骤。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap BIG-small Console.")
    parser.add_argument(
        "--install",
        action="store_true",
        help="Run editable pip install and npm ci.",
    )
    args = parser.parse_args()
    blockers: list[str] = []
    print(f"Python: {sys.version.split()[0]}")
    if shutil.which("node") is None:
        blockers.append("node not found")
    if shutil.which("npm") is None:
        blockers.append("npm not found")
    if blockers:
        for blocker in blockers:
            print(f"BLOCKED: {blocker}")
        return 1
    if args.install:
        _run([sys.executable, "-m", "pip", "install", "-e", ".[dev]"], REPO_ROOT)
        _run(["npm", "ci"], REPO_ROOT / "dashboard")
    _run(["npm", "run", "build"], REPO_ROOT / "dashboard")
    _run([sys.executable, "scripts/init_simulation_runtime_db.py"], REPO_ROOT)
    print("BIG-small Console bootstrap completed")
    return 0


def _run(argv: list[str], cwd: Path) -> None:
    subprocess.run(argv, cwd=cwd, check=True)


if __name__ == "__main__":
    raise SystemExit(main())
