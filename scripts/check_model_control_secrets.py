#!/usr/bin/env python
"""扫描模型控制中心相关文件中的 secret 泄露风险。"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

SECRET_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{8,}"),
    re.compile(r"(?i)authorization\s*[:=]"),
]
PLACEHOLDER_PATTERN = re.compile(r"TEST_SECRET_VALUE_[A-Z0-9_]+")

DEFAULT_ROOTS = [
    "src/cloud_edge_robot_arm/model_control",
    "src/cloud_edge_robot_arm/cloud/api/model_control.py",
    "src/cloud_edge_robot_arm/cloud/api/console_app.py",
    "dashboard/src/modelControl",
    "dashboard/tests/e2e",
    "tests/test_phase11_2_model_control_backend.py",
    "configs/models/small_model_catalog.yaml",
    "scripts/bootstrap_bigsmall_console.py",
    "scripts/start_bigsmall_console.py",
    "scripts/check_model_runtime.py",
    "artifacts/phase11_2",
    "artifacts/phase12",
    "artifacts/phase12_1",
    "artifacts/phase12_2",
    "artifacts/phase12_2_clean",
    "docs/thesis",
    "thesis",
    "artifacts/thesis_report",
    "artifacts/thesis_baselines",
]

IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "playwright-report",
    "test-results",
}

IGNORED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".so",
    ".sqlite",
    ".sqlite3",
    ".db-journal",
    ".db-wal",
    ".db-shm",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check model-control secret leakage.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--strict-placeholders", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    root = args.root.resolve()
    targets = args.paths or DEFAULT_ROOTS
    failures: list[str] = []
    for target in targets:
        path = root / target
        if not path.exists():
            continue
        for file_path in _files(path):
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    failures.append(str(file_path.relative_to(root)))
                    break
            if _placeholder_forbidden(file_path, args.strict_placeholders) and (
                PLACEHOLDER_PATTERN.search(text)
            ):
                failures.append(str(file_path.relative_to(root)))
    if failures:
        for failure in sorted(set(failures)):
            print(f"secret-pattern-detected: {failure}")
        return 1
    print("model control secret scan passed")
    return 0


def _files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return [
        item
        for item in path.rglob("*")
        if item.is_file()
        and not any(part in IGNORED_PARTS for part in item.parts)
        and item.suffix not in IGNORED_SUFFIXES
    ]


def _placeholder_forbidden(path: Path, strict: bool) -> bool:
    if strict:
        return True
    parts = set(path.parts)
    return bool({"artifacts", "dist", "logs"} & parts) or path.suffix in {".db", ".sqlite"}


if __name__ == "__main__":
    raise SystemExit(main())
