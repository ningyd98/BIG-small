#!/usr/bin/env python
"""Phase 9.1 ROS2/Isaac/MoveIt 边界验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.phase9_1.verification import verify_cross_backend


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Phase 9.1 MuJoCo/Isaac cross-backend evidence."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase9_1/cross_backend"),
        help="Directory for verifier artifacts.",
    )
    args = parser.parse_args()

    payload = verify_cross_backend(args.output)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
