#!/usr/bin/env python
"""Phase 10 MoveIt dry-run 和硬件边界验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.real_robot.verification import (  # noqa: E402
    PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED,
    verify_phase10_1,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 10.1 dry-run acceptance.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase10/phase10_1"),
    )
    args = parser.parse_args()
    payload = verify_phase10_1(args.output)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["status"] == PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED else 1


if __name__ == "__main__":
    raise SystemExit(main())
