#!/usr/bin/env python
from __future__ import annotations

import sys

from scripts.run_phase9_benchmarks import main

if __name__ == "__main__":
    sys.argv.extend(["--scenario", "S01_NORMAL_STATIC", "--suite", "smoke"])
    raise SystemExit(main())
