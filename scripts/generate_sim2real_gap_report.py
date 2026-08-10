#!/usr/bin/env python
"""Generate JSON/Markdown gap artifacts and an optional Rerun recording."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cloud_edge_robot_arm.simulation.sim2real import (  # noqa: E402
    GapReportRequest,
    generate_gap_report,
)
from cloud_edge_robot_arm.simulation.sim2real.rerun_viewer import (  # noqa: E402
    write_rerun_recording,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate aligned Sim/Real gap evidence")
    parser.add_argument("request", type=Path, help="GapReportRequest JSON")
    parser.add_argument("--output", type=Path, default=Path("artifacts/sim2real/gap-report"))
    parser.add_argument("--rerun", action="store_true", help="also generate sim2real-alignment.rrd")
    args = parser.parse_args()

    request = GapReportRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    report = generate_gap_report(request)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "sim_real_gap_report.json").write_text(
        report.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (args.output / "sim_real_gap_report.md").write_text(report.markdown, encoding="utf-8")
    if args.rerun:
        write_rerun_recording(request, output_path=args.output / "sim2real-alignment.rrd")
    print(report.model_dump_json(indent=2))
    return 0 if report.status.value != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
