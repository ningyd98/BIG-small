#!/usr/bin/env python
"""Phase 10 MoveIt dry-run 和硬件边界验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.real_robot.verification import verify_phase10_0  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 10.0 real robot gate readiness.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase10/phase10_0"),
    )
    args = parser.parse_args()
    payload = verify_phase10_0(args.output)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
