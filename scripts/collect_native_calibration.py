#!/usr/bin/env python3
"""Three exclusive, bounded development collection entry points; no batch or retries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cloud_edge_robot_arm.research.native_calibration_collection import (
    collect_native_calibration_once,
    prepare_native_calibration,
    verify_native_calibration_collection,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--collect-once", action="store_true")
    modes.add_argument("--verify", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--assignment-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.prepare_only:
        if args.config is None or args.protocol is not None or args.assignment_id is not None:
            parser.error("prepare requires only config and output")
        result = prepare_native_calibration(args.config, output=args.output)
    else:
        if args.protocol is None or args.config is not None:
            parser.error("collect/verify require protocol and no config")
        if args.collect_once:
            if args.assignment_id is None:
                parser.error("collect requires exactly one assignment")
            result = collect_native_calibration_once(
                args.protocol, assignment_id=args.assignment_id, output=args.output
            )
        else:
            if args.assignment_id is not None:
                parser.error("verify retains all preassigned groups in its denominator")
            result = verify_native_calibration_collection(args.protocol, output=args.output)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    if result.get("status") == "COLLECTION_PARTIAL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
