"""中文注释覆盖审计工具。

该脚本只做底线检查：重点代码文件必须至少包含中文说明。是否“合适”仍需要人工
结合业务、安全和并发语义判断。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

HAN_RANGE = ("\u4e00", "\u9fff")


@dataclass(frozen=True)
class CommentAuditResult:
    path: Path
    has_chinese: bool


def main() -> int:
    parser = argparse.ArgumentParser(description="检查重点代码文件是否包含中文说明。")
    parser.add_argument(
        "paths",
        nargs="*",
        default=[
            "src/cloud_edge_robot_arm",
            "dashboard/src/simulation/services",
            "dashboard/src/simulation/components",
            "scripts/verify_phase11_1_simulation_runtime.py",
            "tests/test_phase11_1_simulation_runtime.py",
        ],
        help="需要审计的文件或目录。",
    )
    args = parser.parse_args()

    files = _collect_files([Path(value) for value in args.paths])
    results = [_audit_file(path) for path in files]
    missing = [result.path for result in results if not result.has_chinese]

    for result in results:
        status = "OK" if result.has_chinese else "MISSING"
        print(f"{status} {result.path}")

    if missing:
        print("\n缺少中文说明的文件：")
        for path in missing:
            print(f"- {path}")
        return 1
    return 0


def _collect_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(
                child
                for child in path.rglob("*")
                if child.suffix in {".py", ".ts", ".tsx"} and not child.name.endswith(".d.ts")
            )
        elif path.suffix in {".py", ".ts", ".tsx"}:
            files.append(path)
    return sorted(files)


def _audit_file(path: Path) -> CommentAuditResult:
    text = path.read_text(encoding="utf-8")
    return CommentAuditResult(path=path, has_chinese=_has_chinese(text))


def _has_chinese(text: str) -> bool:
    return any(HAN_RANGE[0] <= char <= HAN_RANGE[1] for char in text)


if __name__ == "__main__":
    raise SystemExit(main())
