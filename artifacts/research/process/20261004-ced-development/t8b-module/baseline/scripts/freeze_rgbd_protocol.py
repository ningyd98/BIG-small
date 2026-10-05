"""Freeze a verified initial protocol; reject missing pilot or undeveloped final methods."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloud_edge_robot_arm.research.freeze_evidence import initial_spec_from_evidence
from cloud_edge_robot_arm.research.protocol import ProtocolSpec, freeze_protocol


def initial_spec_from_pilot(directory: Path) -> ProtocolSpec:
    return initial_spec_from_evidence(directory)


def apply_settings(spec: ProtocolSpec, settings: dict) -> ProtocolSpec:
    allowed = {"schema_version", "bootstrap_iterations", "statistics_seed"}
    if set(settings) - allowed:
        raise ValueError("config cannot override frozen design or pilot-derived evidence")
    return ProtocolSpec.model_validate({**spec.model_dump(), **settings})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["initial", "final"], required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.stage == "final":
        parser.exit(3, "final freeze BLOCKED: method freeze and power pilot not accepted\n")
    try:
        settings = yaml.safe_load(args.config.read_text())
        spec = initial_spec_from_pilot(args.pilot)
        spec = apply_settings(spec, settings)
        frozen = freeze_protocol(spec, args.output, "INITIAL", evidence_directory=args.pilot)
    except (ValueError, OSError) as exc:
        parser.exit(3, f"initial freeze BLOCKED: {exc}\n")
    print(frozen.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
