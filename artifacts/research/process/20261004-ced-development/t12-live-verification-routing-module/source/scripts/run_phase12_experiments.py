#!/usr/bin/env python
"""Phase 12 最终实验运行入口。

该脚本只调用固定 Phase 12 软件/仿真评估管线，不接受任意脚本、shell、URL、控制器地址
或真实硬件 runner。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.final_evaluation.models import Phase12Profile  # noqa: E402
from cloud_edge_robot_arm.final_evaluation.runner import run_phase12_experiments  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 12 final experiment suite.")
    parser.add_argument("--profile", choices=[item.value for item in Phase12Profile], required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase12"))
    args = parser.parse_args()
    payload = run_phase12_experiments(Phase12Profile(args.profile), args.output)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
