#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.real_robot.acceptance import RealRobotAcceptanceLevel  # noqa: E402
from cloud_edge_robot_arm.real_robot.verification import (
    acceptance_level_blocked_payload,  # noqa: E402
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Phase 10 real robot acceptance level.")
    parser.add_argument(
        "--level", required=True, choices=[level.value for level in RealRobotAcceptanceLevel]
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10/acceptance"))
    args = parser.parse_args()
    payload = acceptance_level_blocked_payload(
        args.output,
        requested_level=RealRobotAcceptanceLevel(args.level),
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
