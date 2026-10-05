#!/usr/bin/env python
"""Phase 12 答辩演示包构建入口，不包含 secret、真实控制器地址或设备序列号。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.final_evaluation.report import export_thesis_assets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase 12 defense demo bundle.")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase12"))
    args = parser.parse_args()
    payload = export_thesis_assets(args.output, profile=args.profile)
    print(json.dumps(payload["demo_bundle"], sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
