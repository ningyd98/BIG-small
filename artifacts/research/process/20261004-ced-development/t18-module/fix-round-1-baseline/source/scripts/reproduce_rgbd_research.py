#!/usr/bin/env python3
"""Verify a local bundle or rebuild its analysis without running stored commands."""

import argparse
import json
from pathlib import Path

from cloud_edge_robot_arm.research.reproducibility import (
    rebuild_analysis,
    verify_reproduction_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--software-only", action="store_true")
    arguments = parser.parse_args()
    verification = dict(verify_reproduction_bundle(arguments.bundle))
    if arguments.output.exists():
        print(json.dumps({"status": "INVALID", "reason": "output already exists"}))
        return 2
    if verification["integrity_valid"] is not True:
        arguments.output.mkdir(parents=True)
        (arguments.output / "verification.json").write_text(
            json.dumps(verification, indent=2) + "\n")
        print(json.dumps({"status": "INVALID", "errors": verification["errors"]}))
        return 2
    if arguments.verify_only:
        arguments.output.mkdir(parents=True)
        (arguments.output / "verification.json").write_text(
            json.dumps(verification, indent=2) + "\n")
        print(json.dumps({"status": "VERIFIED_INTEGRITY", **verification}))
        return 0
    try:
        rebuild_analysis(arguments.bundle, arguments.output, software_only=arguments.software_only)
        result = json.loads((arguments.output / "reproduction.json").read_text())
        print(json.dumps(result))
        return 0 if result["numeric_rebuild"] == "SOFTWARE_ONLY" else 4
    except (ValueError, TypeError, KeyError, OSError) as error:
        arguments.output.mkdir(parents=True, exist_ok=True)
        (arguments.output / "reproduction-error.json").write_text(json.dumps({
            "status": "NOT_RUN", "reason": str(error), "research_accepted": False,
        }, indent=2) + "\n")
        print(json.dumps({"status": "NOT_RUN", "reason": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
