"""原样复用 R545 运行时覆盖，转交多场景研究入口。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def main() -> int:
    path = Path(__file__).resolve().parents[2] / (
        "round545-molmo-opencv-runtime-overlay-20261110/implementation/launch_molmo_grounded.py"
    )
    spec = importlib.util.spec_from_file_location("r558_original_overlay", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.configure_overlay()
    if sys.argv[1:] == ["--preflight"]:
        print(json.dumps(result, indent=2))
        return 0
    from scripts.probe_molmo_multiscene import main as run

    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
