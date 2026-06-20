#!/usr/bin/env python
"""汇总 Phase 13.1 LLM-only 基线产物，且不把阻塞样本写成性能结果。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Phase 13.1 artifacts.")
    parser.add_argument("--root", type=Path, default=Path("artifacts/phase13_1"))
    args = parser.parse_args()
    rows_path = args.root / "runs/llm_only_runs.jsonl"
    rows = (
        [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line]
        if rows_path.exists()
        else []
    )
    accepted_rows = [row for row in rows if row.get("model_runtime_accepted") is True]
    latencies = [
        float(row["latency_ms"])
        for row in accepted_rows
        if isinstance(row.get("latency_ms"), int | float)
    ]
    payload = {
        "run_count": len(rows),
        "accepted_count": len(accepted_rows),
        "blocked_count": len(rows) - len(accepted_rows),
        "model_request_count": sum(int(row.get("model_request_count", 0)) for row in rows),
        "task_success_count": sum(1 for row in accepted_rows if row.get("task_success") is True),
        "valid_contract_rate": (
            mean(float(row.get("valid_contract_rate", 0.0)) for row in accepted_rows)
            if accepted_rows
            else "NOT_AVAILABLE"
        ),
        "latency_ms_mean": mean(latencies) if latencies else "NOT_AVAILABLE",
        "unsafe_proposed_action_count": sum(
            int(row.get("unsafe_proposed_action_count", 0)) for row in rows
        ),
        "unsafe_command_execution_count": sum(
            int(row.get("unsafe_command_execution_count", 0)) for row in rows
        ),
        "authoritative_for_model_performance": bool(accepted_rows),
    }
    out = args.root / "statistics/phase13_1_statistics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
