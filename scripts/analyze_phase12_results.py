#!/usr/bin/env python
"""Phase 12 结果分析入口，生成 aggregate、paired 和 statistics artifact。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.final_evaluation.aggregation import (  # noqa: E402
    load_raw_runs,
    write_aggregate,
)
from cloud_edge_robot_arm.final_evaluation.models import Phase12Profile  # noqa: E402
from cloud_edge_robot_arm.final_evaluation.statistics import (  # noqa: E402
    compute_group_statistics,
    paired_difference_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Phase 12 experiment results.")
    parser.add_argument("--profile", choices=[item.value for item in Phase12Profile], required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase12"))
    args = parser.parse_args()
    profile = Phase12Profile(args.profile)
    root = args.output
    aggregate_payload = write_aggregate(root, profile)
    rows = load_raw_runs(root)
    pairs = [
        {
            "pairing_key": f"{row.get('scenario_id')}|{row.get('seed')}|{row.get('control_mode')}",
            "left_value": row.get("total_completion_time_ms", 0),
            "right_value": row.get("total_completion_time_ms", 0),
            "left_status": row.get("status", ""),
            "right_status": row.get("status", ""),
        }
        for row in rows
        if row.get("experiment_id") == "F15_MUJOCO_ISAAC_PAIRED"
    ]
    statistics = {
        "profile": profile.value,
        "group_statistics": compute_group_statistics(
            rows, group_key="control_mode", metric_key="total_completion_time_ms"
        ),
        "backend_statistics": compute_group_statistics(
            rows, group_key="backend", metric_key="total_completion_time_ms"
        ),
        "paired_results": paired_difference_summary(pairs),
        "missing_data_reasons": {
            "BLOCKED_BY_ENV": sum(1 for row in rows if row.get("status") == "BLOCKED_BY_ENV")
        },
        "blocked_by_env_count": sum(1 for row in rows if row.get("status") == "BLOCKED_BY_ENV"),
    }
    stats_dir = root / "statistics"
    stats_dir.mkdir(parents=True, exist_ok=True)
    (stats_dir / "phase12_statistics.json").write_text(
        json.dumps(statistics, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"aggregate": aggregate_payload["aggregate"], "statistics": statistics}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
