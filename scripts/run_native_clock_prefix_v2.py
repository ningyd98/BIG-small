"""Validate prefix originals, or explicitly run one excluded source-only job.

Default validation does not create an application, output directory, job, lease,
backend or exchange. A completed prefix never establishes calibrated native UTC.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from cloud_edge_robot_arm.research.native_clock_publication_v2 import (
    NativeClockPrefixApplicationV2,
    validate_startup_inputs_v2,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/research/native_clock_authority_v2.json"),
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-once", action="store_true")
    args = parser.parse_args(argv)
    scope = "EXCLUDED_SOURCE_ONLY_PREFIX" if args.execute_once else "INPUTS_ONLY"
    try:
        if args.execute_once:
            application = NativeClockPrefixApplicationV2.from_startup(
                args.config, output=args.output
            )
            receipt = application.execute_once()
            result = {
                "scope": scope,
                "native_utc": "UNAVAILABLE",
                "receipt": receipt,
            }
            exit_code = 0 if receipt.get("prefix_complete") is True else 1
        else:
            result = {
                "scope": scope,
                "actual_execution": "NOT_RUN",
                "inputs": validate_startup_inputs_v2(args.config),
            }
            exit_code = 0
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return exit_code
    except (OSError, ValueError, RuntimeError, TypeError) as error:
        print(
            json.dumps(
                {"scope": scope, "error_type": type(error).__name__, "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
