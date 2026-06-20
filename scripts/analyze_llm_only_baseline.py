#!/usr/bin/env python
"""分析 LLM-only 基线输出。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze LLM-only baseline artifacts.")
    parser.add_argument("--root", type=Path, default=Path("artifacts/thesis_baselines/llm_only"))
    args = parser.parse_args()
    rows_path = args.root / "runs/llm_only_runs.jsonl"
    rows = (
        [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line]
        if rows_path.exists()
        else []
    )
    summary = {
        "run_count": len(rows),
        "model_request_count": sum(int(row.get("model_request_count", 0)) for row in rows),
        "unsafe_command_execution_count": sum(
            int(row.get("unsafe_command_execution_count", 0)) for row in rows
        ),
        "model_runtime_types": sorted({str(row.get("model_runtime_type")) for row in rows}),
        "authoritative_for_model_performance": False,
    }
    out = args.root / "statistics/llm_only_statistics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
