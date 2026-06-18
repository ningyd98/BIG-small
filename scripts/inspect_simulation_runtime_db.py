#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect simulation runtime SQLite database.")
    parser.add_argument("--database", type=Path, default=Path("data/simulation_runtime.db"))
    args = parser.parse_args()
    uri = f"file:{args.database.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        tables = [
            "simulation_jobs",
            "simulation_job_events",
            "simulation_job_leases",
            "simulation_job_attempts",
            "simulation_metrics",
            "simulation_artifacts",
            "simulation_batches",
            "schema_migrations",
        ]
        payload = {}
        for table in tables:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
            payload[table] = int(row["count"])
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
