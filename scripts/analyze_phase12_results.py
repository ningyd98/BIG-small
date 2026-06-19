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
    authoritative_rows = [row for row in rows if row.get("authoritative_for_thesis") is True]
    statistics = {
        "profile": profile.value,
        "synthetic_sample_count": sum(
            1 for row in rows if row.get("execution_source") == "SYNTHETIC_PIPELINE_SAMPLE"
        ),
        "actual_run_count": sum(1 for row in rows if row.get("actual_runner_invoked") is True),
        "adapter_attempt_count": sum(1 for row in rows if row.get("adapter_attempted") is True),
        "runtime_invocation_count": sum(1 for row in rows if row.get("runtime_invoked") is True),
        "runtime_completion_count": sum(1 for row in rows if row.get("runtime_completed") is True),
        "blocked_before_runtime_count": sum(
            1
            for row in rows
            if row.get("status") == "BLOCKED_BY_ENV"
            and row.get("environment_check_completed") is True
            and row.get("runtime_invoked") is not True
        ),
        "authoritative_thesis_run_count": len(authoritative_rows),
        "group_statistics": compute_group_statistics(
            authoritative_rows, group_key="control_mode", metric_key="total_completion_time_ms"
        ),
        "backend_statistics": compute_group_statistics(
            authoritative_rows, group_key="backend", metric_key="total_completion_time_ms"
        ),
        "paired_results": aggregate_payload["paired"],
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
