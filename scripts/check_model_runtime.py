#!/usr/bin/env python
"""Check model runtime prerequisites without contacting hardware."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check BIG-small model runtime.")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    payload = {
        "api_server": _probe_json(args.api + "/api/v1/model-control/capabilities"),
        "ollama": _probe_json("http://127.0.0.1:11434/api/version"),
        "installed_model_count": _installed_model_count(),
        "active_planner": _probe_json(args.api + "/api/v1/model-control/runtime"),
        "secret_store": "SESSION_ONLY",
        "database": _database_status(),
        "dashboard_build": (REPO_ROOT / "dashboard/dist/index.html").exists(),
        "real_controller_contacted": False,
        "hardware_motion_observed": False,
        "hardware_write_operations": [],
    }
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


def _probe_json(url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return {"reachable": True, "payload": json.loads(response.read(1_000_000))}
    except Exception as exc:
        return {"reachable": False, "error_code": type(exc).__name__}


def _installed_model_count() -> int:
    payload = _probe_json("http://127.0.0.1:11434/api/tags")
    if not payload.get("reachable"):
        return 0
    return len(payload.get("payload", {}).get("models", []))


def _database_status() -> dict[str, Any]:
    path = Path(os.environ.get("MODEL_CONTROL_DB", REPO_ROOT / "data/model_control.db"))
    if not path.exists():
        return {"exists": False, "path": "data/model_control.db"}
    try:
        with sqlite3.connect(path) as conn:
            tables = [
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            ]
    except sqlite3.DatabaseError as exc:
        return {"exists": True, "error_code": type(exc).__name__}
    return {"exists": True, "tables": sorted(tables)}


if __name__ == "__main__":
    raise SystemExit(main())
