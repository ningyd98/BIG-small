"""Validate saved payloads, provenance, quality, and group split boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args(argv)
    from cloud_edge_robot_arm.datasets.rgbd.quality import validate_dataset

    try:
        result = validate_dataset(args.dataset)
        print(result.model_dump_json(indent=2))
        return 0 if result.valid else 4
    except (OSError, ValueError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
