#!/usr/bin/env python
"""Phase 9 物理仿真和跨后端验证验证入口，按固定检查流程生成验收证据，不执行未授权硬件动作。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.evaluation.collector import Phase9ArtifactCollector


def main() -> int:
    output = Path("artifacts/phase9/artifact_smoke")
    collector = Phase9ArtifactCollector(output)
    collector.write_minimal_run(
        run_id="artifact-smoke",
        backend="mujoco",
        scenario="S01_NORMAL_STATIC",
        seed=0,
        metrics={"physics_steps": 10, "illegal_collision_count": 0},
    )
    missing = sorted(
        name for name in Phase9ArtifactCollector.REQUIRED_FILES if not (output / name).exists()
    )
    print(
        json.dumps(
            {"status": "passed" if not missing else "failed", "missing": missing},
            sort_keys=True,
            indent=2,
        )
    )
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
