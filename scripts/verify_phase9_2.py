#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.phase9_2.verification import (  # noqa: E402
    phase9_2_status,
    verify_phase9_2_acceptance,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 9.2 simulation final acceptance.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase9_2/final"),
        help="Directory for Phase 9.2 final summary.",
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts"),
        help="Repository artifact root containing phase9_1 and phase9_2 outputs.",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    payload = (
        _verify_from_input_file(args.output)
        if (args.output / "phase9_2_inputs.json").exists()
        else verify_phase9_2_acceptance(args.output, artifacts_root=args.artifacts_root)
    )
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0 if payload["status"] == "PHASE9_2_ACCEPTED" else 1


def _verify_from_input_file(output_dir: Path) -> dict[str, object]:
    input_path = output_dir / "phase9_2_inputs.json"
    loaded = json.loads(input_path.read_text(encoding="utf-8"))
    summary = dict(loaded) if isinstance(loaded, dict) else {}
    status = phase9_2_status(summary)
    payload = {"status": status, "validation_claimed": status == "PHASE9_2_ACCEPTED", **summary}
    (output_dir / "phase9_2_summary.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
