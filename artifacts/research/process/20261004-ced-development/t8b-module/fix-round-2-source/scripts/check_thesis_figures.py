#!/usr/bin/env python
"""检查论文图表索引，防止 placeholder preview 进入正式正文。"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FigureFailure:
    """单个图表门禁失败。"""

    path: str
    message: str


@dataclass(frozen=True)
class FigureCheckResult:
    """图表门禁检查汇总。"""

    passed: bool
    failures: list[FigureFailure]
    formal_figure_count: int
    placeholder_excluded_count: int


def check_thesis_figures(*, root: Path | None = None) -> FigureCheckResult:
    """检查正式正文是否引用了不允许入正文的 placeholder 图。"""

    root = root or Path.cwd()
    figure_index = root / "thesis/figures/figure_index.json"
    if not figure_index.exists():
        return FigureCheckResult(
            passed=False,
            failures=[FigureFailure(str(figure_index), "missing figure index")],
            formal_figure_count=0,
            placeholder_excluded_count=0,
        )
    payload = json.loads(figure_index.read_text(encoding="utf-8"))
    figures = payload.get("figures", []) if isinstance(payload, dict) else []
    manuscript_text = _formal_manuscript_text(root)
    failures: list[FigureFailure] = []
    formal_count = 0
    placeholder_excluded = 0
    for item in figures:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        data_source = str(item.get("data_source", ""))
        formal_allowed = item.get("formal_allowed", data_source != "placeholder_preview")
        is_placeholder = data_source == "placeholder_preview"
        if is_placeholder:
            placeholder_excluded += 1
        if formal_allowed and not is_placeholder:
            formal_count += 1
        if is_placeholder and path and path in manuscript_text:
            failures.append(FigureFailure(path, "placeholder figure referenced by formal thesis"))
        if (
            formal_allowed
            and not str(item.get("source_hash", ""))
            and data_source == "aggregate_payload"
        ):
            failures.append(FigureFailure(path, "formal aggregate figure missing source_hash"))
    return FigureCheckResult(
        passed=not failures,
        failures=failures,
        formal_figure_count=formal_count,
        placeholder_excluded_count=placeholder_excluded,
    )


def _formal_manuscript_text(root: Path) -> str:
    parts: list[str] = []
    for base in [root / "docs/thesis", root / "artifacts/thesis_report", root / "thesis"]:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix in {".md", ".tex"} and "figure_index" not in path.name:
                parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check thesis figures.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = check_thesis_figures(root=args.root.resolve())
    if result.failures:
        for failure in result.failures:
            print(f"{failure.path}: {failure.message}")
        return 1
    print(
        "thesis figure check passed "
        f"formal={result.formal_figure_count} "
        f"placeholder_excluded={result.placeholder_excluded_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
