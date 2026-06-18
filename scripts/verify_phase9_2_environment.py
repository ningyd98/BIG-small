#!/usr/bin/env python
"""Phase 9.2 跨后端和 Isaac 环境验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.phase9_2.verification import (  # noqa: E402
    collect_environment_compatibility,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 9.2 Isaac environment readiness.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase9_2/environment"),
        help="Directory for Phase 9.2 environment artifacts.",
    )
    args = parser.parse_args()

    payload = collect_environment_compatibility(args.output)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
