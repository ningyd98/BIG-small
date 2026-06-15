#!/usr/bin/env python
from __future__ import annotations

import sys

from scripts.run_phase9_benchmarks import main

if __name__ == "__main__":
    sys.argv.extend(["--backend", "isaac", "--suite", "smoke"])
    raise SystemExit(main())
