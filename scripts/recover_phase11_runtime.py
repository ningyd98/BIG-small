#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from cloud_edge_robot_arm.simulation_runtime.artifact_recovery import recover_artifacts
from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
    SQLiteSimulationJobRepository,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover Phase 11 simulation runtime history.")
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--database", type=Path, default=Path("data/simulation_runtime.db"))
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dry_run = not args.apply
    repository = SQLiteSimulationJobRepository(args.database)
    response = recover_artifacts(
        repository=repository,
        artifact_root=args.artifact_root,
        dry_run=dry_run,
    )
    print(json.dumps(response.model_dump(mode="json"), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
