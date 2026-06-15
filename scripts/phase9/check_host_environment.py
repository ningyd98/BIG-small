#!/usr/bin/env python
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from cloud_edge_robot_arm.simulation.environment import detect_environment


def main() -> int:
    report = detect_environment()
    report.write(Path("artifacts/phase9/environment"))
    print(report.to_jsonable())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
