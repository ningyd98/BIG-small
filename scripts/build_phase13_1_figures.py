#!/usr/bin/env python
"""生成 Phase 13.1 图索引；真实模型缺失时只记录 NOT_AVAILABLE。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase 13.1 figure index.")
    parser.add_argument("--root", type=Path, default=Path("artifacts/phase13_1"))
    args = parser.parse_args()
    stats_path = args.root / "statistics/phase13_1_statistics.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    accepted = int(stats.get("accepted_count", 0) or 0)
    figures = []
    for name in (
        "valid_contract_rate",
        "task_success_rate",
        "provider_latency",
        "model_request_count",
    ):
        figures.append(
            {
                "name": name,
                "status": "NOT_AVAILABLE" if accepted == 0 else "AVAILABLE",
                "formal_allowed": accepted > 0,
                "reason": "real model runtime not accepted" if accepted == 0 else "",
            }
        )
    out = args.root / "figures/figure_index.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(figures, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"figure_count": len(figures), "accepted_model_rows": accepted}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
