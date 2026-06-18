#!/usr/bin/env python
"""Phase 9.2 跨后端和 Isaac 环境验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.phase9_2.verification import (  # noqa: E402
    run_isaac_smoke_runtime,
    runtime_config_from_env,
    verify_isaac_smoke_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 9.2 real Isaac smoke evidence.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase9_2/isaac"),
        help="Directory containing Phase 9.2 Isaac smoke artifacts.",
    )
    args = parser.parse_args()

    config = runtime_config_from_env(repo_root=Path("."), output_dir=args.output)
    payload = (
        run_isaac_smoke_runtime(args.output, config=config)
        if config is not None and not (args.output / "isaac_smoke_evidence.json").exists()
        else verify_isaac_smoke_evidence(args.output)
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["status"] == "ISAAC_SMOKE_VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
