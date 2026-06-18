#!/usr/bin/env python
"""Dashboard OpenAPI 导出脚本，用真实 FastAPI schema 驱动前端类型检查。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from cloud_edge_robot_arm.cloud.api.app import create_app  # noqa: E402
from cloud_edge_robot_arm.cloud.planning.adapter import MockPlannerAdapter  # noqa: E402
from cloud_edge_robot_arm.cloud.planning.pipeline import PlanningPipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export dashboard OpenAPI schema.")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "dashboard/src/api/generated/openapi.json",
    )
    args = parser.parse_args()
    app = create_app(PlanningPipeline(planner=MockPlannerAdapter()))
    schema = app.openapi()
    paths = schema.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise SystemExit("exported OpenAPI schema has no paths")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(schema, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} with {len(paths)} paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
