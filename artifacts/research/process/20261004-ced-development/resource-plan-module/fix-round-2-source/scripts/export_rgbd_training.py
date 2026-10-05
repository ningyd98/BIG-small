"""Export grounding examples from permitted splits, preserving negative examples."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "calibration", "selection"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    from cloud_edge_robot_arm.datasets.rgbd.exporters import export_grounding_sft

    try:
        if args.output.resolve().is_relative_to(args.dataset.resolve()):
            raise ValueError("export output must be outside the source dataset")
        count = export_grounding_sft(args.dataset, args.split, args.output)
        print(json.dumps({"status": "COMPLETE", "samples": count, "split": args.split,
                          "output": str(args.output.resolve())}, ensure_ascii=False))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "FAILED", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
