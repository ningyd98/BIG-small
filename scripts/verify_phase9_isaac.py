#!/usr/bin/env python
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cloud_edge_robot_arm.simulation.isaac.client import IsaacSimClient


def main() -> int:
    status = IsaacSimClient().check_status()
    payload = {
        "status": status.status,
        "message": status.message,
        "validation": "not_run" if status.status == "BLOCKED_BY_ENV" else "ready_to_smoke",
    }
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
