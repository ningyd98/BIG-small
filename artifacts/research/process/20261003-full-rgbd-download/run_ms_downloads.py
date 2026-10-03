"""完整下载显式魔搭清单，复用现有直连传输与全局预算账本。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cloud_edge_robot_arm.datasets.external.transfer import _atomic_json, download_plan


def main() -> None:
    for value in sys.argv[1:]:
        path = Path(value)
        plan = json.loads(path.read_text())
        print(
            f"START {plan['dataset_id']} {sum(f['size'] for f in plan['files'])} bytes", flush=True
        )
        result = download_plan(plan, max_workers=4, retries=3)
        _atomic_json(path.with_name(path.stem + "-download.json"), result)
        print(f"COMPLETE {plan['dataset_id']} {result['download_directory']}", flush=True)


if __name__ == "__main__":
    main()
