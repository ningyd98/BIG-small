#!/usr/bin/env python
"""构建毕业论文证据索引。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.thesis.evidence import build_thesis_evidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build thesis evidence index.")
    parser.add_argument(
        "--validation-root",
        type=Path,
        default=Path("artifacts/phase12_2_clean/validation"),
    )
    parser.add_argument(
        "--llm-root",
        type=Path,
        default=Path("artifacts/thesis_baselines/llm_only"),
    )
    parser.add_argument("--output", type=Path, default=Path("thesis/generated"))
    args = parser.parse_args()
    payload = build_thesis_evidence(
        validation_root=args.validation_root,
        llm_root=args.llm_root,
        output_root=args.output,
    )
    print(
        json.dumps(
            {
                "metrics": str(args.output / "thesis_metrics.json"),
                "claim_evidence": str(args.output / "claim_evidence.json"),
                "figure_count": len(payload["figure_index"]),
                "table_count": len(payload["table_index"]),
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
