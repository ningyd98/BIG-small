"""Pure default OC2 input validation; explicit execution is gated pending Task2."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from cloud_edge_robot_arm.research.operational_prefix_v1 import (
    OperationalPrefixApplicationV1,
    validate_operational_prefix_inputs_v1,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, default=Path("configs/research/operational_prefix_v1.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-once", action="store_true")
    args = parser.parse_args(argv)
    scope = "EXCLUDED_SOURCE_ONLY_PREFIX" if args.execute_once else "INPUTS_ONLY"
    try:
        if args.execute_once:
            application = OperationalPrefixApplicationV1.from_startup(
                args.config, output=args.output
            )
            receipt = application.execute_once()
            result = {"scope": scope, "receipt": receipt}
            code = 0 if receipt.get("source_prefix_complete") is True else 1
        else:
            result = {
                "scope": scope,
                "actual_execution": "NOT_RUN",
                "inputs": validate_operational_prefix_inputs_v1(args.config),
            }
            code = 0
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return code
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
