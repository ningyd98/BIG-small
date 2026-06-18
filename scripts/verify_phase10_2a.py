#!/usr/bin/env python
"""Phase 10.2A 安全契约验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

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
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="Treat MoveIt runtime dry-run as environment-blocked for CI-safe checks.",
    )
    args = parser.parse_args()
    if args.skip_runtime:
        with TemporaryDirectory(prefix="phase10_2a_moveit_block_") as temp_dir:
            moveit_dir = Path(temp_dir)
            (moveit_dir / "moveit_dry_run_verification.json").write_text(
                json.dumps(
                    {
                        "status": "MOVEIT_DRY_RUN_BLOCKED_BY_ENV",
                        "validation_claimed": False,
                        "moveit_runtime_used": False,
                        "sent_to_hardware": False,
                        "hardware_motion_observed": False,
                        "blockers": ["MoveIt runtime dry-run skipped by CI-safe profile"],
                    },
                    sort_keys=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            payload = verify_phase10_2a(
                args.output,
                phase10_0_dir=args.phase10_0_dir,
                phase10_1_dir=args.phase10_1_dir,
                moveit_dry_run_dir=moveit_dir,
            )
    else:
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
