#!/usr/bin/env python
"""Phase 9.2 跨后端和 Isaac 环境演示或实验入口，用固定参数运行受控流程并输出可追溯结果。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.phase9_2.verification import (  # noqa: E402
    run_phase9_2_paired_experiments,
    runtime_config_from_env,
    verify_cross_backend_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 9.2 MuJoCo-Isaac paired artifacts.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase9_2/cross_backend"),
        help="Directory containing Phase 9.2 cross-backend artifacts.",
    )
    parser.add_argument(
        "--run-experiments",
        action="store_true",
        help="Run real MuJoCo and Isaac paired experiments before verification.",
    )
    args = parser.parse_args()

    config = runtime_config_from_env(
        repo_root=Path("."), output_dir=Path("artifacts/phase9_2/isaac")
    )
    payload = (
        run_phase9_2_paired_experiments(args.output, config=config)
        if args.run_experiments and config is not None
        else verify_cross_backend_artifacts(args.output)
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["status"] == "CROSS_BACKEND_VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
