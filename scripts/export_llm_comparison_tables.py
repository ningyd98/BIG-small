#!/usr/bin/env python
"""导出 LLM-only 对比表模板。"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export LLM-only comparison table template.")
    parser.add_argument("--root", type=Path, default=Path("artifacts/thesis_baselines/llm_only"))
    args = parser.parse_args()
    out = args.root / "tables/llm_only_comparison_template.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "group": "LLM-Only One-Shot",
            "runtime_type": "待真实模型环境补充",
            "model_performance_conclusion": "NOT_AVAILABLE",
        },
        {
            "group": "LLM-Only Reactive",
            "runtime_type": "待真实模型环境补充",
            "model_performance_conclusion": "NOT_AVAILABLE",
        },
        {
            "group": "PCSC/ETEAC/AUTO",
            "runtime_type": "Phase 12 validation",
            "model_performance_conclusion": "云边协同 validation 级软件/仿真证据",
        },
    ]
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
