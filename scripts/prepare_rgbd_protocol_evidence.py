"""Prepare or independently verify offline formal evidence; never run experiments."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.research.protocol_evidence import (
    prepare_protocol_evidence,
    verify_protocol_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pools", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--consumer-role", default="offline_evaluation")
    args = parser.parse_args()
    if args.consumer_role != "offline_evaluation":
        parser.exit(3, "formal evidence access denied for development or online consumers\n")
    if not args.verify and args.pools is None:
        parser.error("--pools is required when preparing evidence")
    try:
        report = (
            verify_protocol_evidence(args.output)
            if args.verify
            else prepare_protocol_evidence(
                json.loads(args.pools.read_text()),
                args.output,
            )
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(3, f"offline protocol evidence rejected: {exc}\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "COMPLETE" else 3


if __name__ == "__main__":
    raise SystemExit(main())
