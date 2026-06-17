#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.real_robot.verification import verify_phase10_2a  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 10.2A dry-run evidence chain.")
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase10/phase10_2a"))
    parser.add_argument("--phase10-0-dir", type=Path, default=Path("artifacts/phase10/phase10_0"))
    parser.add_argument("--phase10-1-dir", type=Path, default=Path("artifacts/phase10/phase10_1"))
    parser.add_argument(
        "--moveit-dry-run-dir", type=Path, default=Path("artifacts/phase10/moveit_dry_run")
    )
    args = parser.parse_args()
    payload = verify_phase10_2a(
        args.output,
        phase10_0_dir=args.phase10_0_dir,
        phase10_1_dir=args.phase10_1_dir,
        moveit_dry_run_dir=args.moveit_dry_run_dir,
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["validation_claimed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
