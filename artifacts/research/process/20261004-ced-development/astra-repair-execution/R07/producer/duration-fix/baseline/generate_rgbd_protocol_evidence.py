"""Prepare/preflight offline recovery; actual execution requires --execute-once."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.research.protocol_generation import (
    execute_recovery_once,
    preflight_generation,
    prepare_generation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--history-source", type=Path, action="append", default=[])
    parser.add_argument("--history-catalog", type=Path)
    parser.add_argument("--seed", type=int, default=2026100507)
    parser.add_argument("--assignment", default="recovery-0001")
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--execute-once", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--expected-protocol-hash")
    args = parser.parse_args()
    try:
        if args.prepare:
            if args.execute_once:
                raise ValueError("prepare cannot execute")
            sources = args.history_source
            if args.history_catalog is not None:
                sources += [
                    Path(p) for p in json.loads(args.history_catalog.read_text())["sources"]
                ]
            report = prepare_generation(sources, args.protocol, args.seed)
        elif args.execute_once:
            if args.output is None or not args.expected_protocol_hash:
                raise ValueError("execute-once requires fresh output and reviewed protocol hash")
            report = execute_recovery_once(
                args.protocol,
                args.assignment,
                args.output,
                attempt=args.attempt,
                expected_protocol_hash=args.expected_protocol_hash,
            )
        else:
            report = preflight_generation(args.protocol, args.assignment, args.attempt)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] in {"READY_FOR_REVIEW", "PREFLIGHT_ONLY", "PROVEN"} else 3
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc), "actual_calls": 0}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
