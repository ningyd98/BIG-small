"""调用生产研究分析函数；不从历史命令字段执行脚本或调用模型。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.datasets.rgbd.models import canonical_json
from cloud_edge_robot_arm.research.acceptance import analyze_research_runs


def main(argv: list[str] | None = None) -> int:
    """保存完整机器可读/CSV诊断，正式来源不齐时返回 NOT_RUN 和exit3。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--software-only", action="store_true")
    args = parser.parse_args(argv)
    result = analyze_research_runs(
        args.runs, args.protocol, args.output, software_only=args.software_only
    )
    print(canonical_json(result))
    return 0 if result["status"] == "SOFTWARE_ONLY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
