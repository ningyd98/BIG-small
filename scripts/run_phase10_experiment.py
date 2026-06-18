#!/usr/bin/env python
"""Phase 10 MoveIt dry-run 和硬件边界演示或实验入口，用固定参数运行受控流程并输出可追溯结果。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.real_robot.verification import experiment_dry_run_payload  # noqa: E402

EXPERIMENT_IDS = {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a Phase 10 real robot experiment run.")
    parser.add_argument("--experiment", required=True, choices=sorted(EXPERIMENT_IDS))
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10/experiments"))
    args = parser.parse_args()
    payload = experiment_dry_run_payload(args.output, experiment_id=args.experiment)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["status"] == "DRY_RUN_VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
