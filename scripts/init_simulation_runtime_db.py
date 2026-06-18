#!/usr/bin/env python
from __future__ import annotations

import argparse
from pathlib import Path

from cloud_edge_robot_arm.simulation_runtime.sqlite_repository import (
    SQLiteSimulationJobRepository,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize simulation runtime SQLite database.")
    parser.add_argument("--database", type=Path, default=Path("data/simulation_runtime.db"))
    args = parser.parse_args()
    SQLiteSimulationJobRepository(args.database)
    print(f"initialized {args.database.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
