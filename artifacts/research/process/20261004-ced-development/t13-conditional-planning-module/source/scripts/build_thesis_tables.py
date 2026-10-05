#!/usr/bin/env python
"""构建论文表格索引并复制 validation 表格。"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build thesis table assets.")
    parser.add_argument(
        "--validation-root",
        type=Path,
        default=Path("artifacts/phase12_2_clean/validation"),
    )
    parser.add_argument("--output", type=Path, default=Path("thesis/tables"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for subdir in ("csv", "markdown", "latex"):
        source = args.validation_root / "tables" / subdir
        target = args.output / subdir
        target.mkdir(parents=True, exist_ok=True)
        if source.exists():
            for item in sorted(source.glob("*")):
                if item.is_file():
                    shutil.copy2(item, target / item.name)
                    copied.append(str(target / item.name))
    index = {"table_file_count": len(copied), "tables": copied}
    (args.output / "table_index.json").write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
