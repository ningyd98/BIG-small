#!/usr/bin/env python
"""Phase 12 论文图表、表格、报告和答辩包导出入口。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.final_evaluation.models import Phase12Profile  # noqa: E402
from cloud_edge_robot_arm.final_evaluation.report import export_thesis_assets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Phase 12 thesis assets.")
    parser.add_argument("--profile", choices=[item.value for item in Phase12Profile], required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase12"))
    args = parser.parse_args()
    payload = export_thesis_assets(args.output, profile=args.profile)
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
