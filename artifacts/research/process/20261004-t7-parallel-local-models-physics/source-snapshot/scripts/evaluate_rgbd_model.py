"""Evaluate frozen RGB-D model grounding on independent selection/test records."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud_edge_robot_arm.vision.evaluation import evaluate_model
from cloud_edge_robot_arm.vision.frozen_model import load_frozen_planner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--split", choices=["selection", "test"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--frozen-dir",
        type=Path,
        default=Path(
            "artifacts/research/process/20261003-t7-visual-closed-loop/model-probe",
        ),
    )
    args = parser.parse_args()
    report = evaluate_model(
        args.dataset, args.split, load_frozen_planner(args.frozen_dir), args.output
    )
    print(json.dumps({k: v for k, v in asdict(report).items() if k != "records"}, indent=2))
    return 0 if report.blocked == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
