#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cloud_edge_robot_arm.experiments.batch_runner import run_suite  # noqa: E402


def _parse_seeds(raw: str | None) -> list[int] | None:
    if raw is None:
        return None
    if ":" in raw:
        start_s, end_s = raw.split(":", 1)
        start = int(start_s)
        end = int(end_s)
        if start < 0 or end < start:
            raise argparse.ArgumentTypeError("seed range must be non-negative start:end")
        return list(range(start, end + 1))
    values = [int(part) for part in raw.split(",") if part]
    if any(seed < 0 for seed in values):
        raise argparse.ArgumentTypeError("seeds must be non-negative")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 8 reproducible experiments")
    parser.add_argument("--suite", choices=["smoke", "full"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=str, default=None, help="seed list like 0,1 or range 0:9")
    parser.add_argument("--networks", type=str, default=None, help="comma-separated network names")
    args = parser.parse_args()
    seeds = _parse_seeds(args.seeds)
    networks = [item for item in args.networks.split(",") if item] if args.networks else None
    try:
        summary = run_suite(args.suite, output_dir=args.output, seeds=seeds, network_names=networks)
    except Exception as exc:
        print(f"phase8 experiment failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"run_count={summary.run_count}")
    print(f"success_count={summary.success_count}")
    print(f"output={summary.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
