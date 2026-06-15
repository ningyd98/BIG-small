#!/usr/bin/env python
from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    root = os.environ.get("ISAAC_SIM_ROOT", "")
    blocked = not root or not Path(root).exists()
    payload = {
        "status": "BLOCKED_BY_ENV" if blocked else "READY_TO_SMOKE",
        "isaac_sim_root": root,
        "blockers": ["ISAAC_SIM_ROOT is unset or missing"] if blocked else [],
    }
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
