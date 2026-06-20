#!/usr/bin/env python
"""核验论文 BibTeX 元数据，避免未核验文献进入正式参考文献。"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReferenceVerificationResult:
    """参考文献核验结果。"""

    passed: bool
    entry_count: int
    cited_key_count: int
    failures: list[str]
    entry_keys: list[str]


def verify_references(
    *,
    bib_path: Path = Path("thesis/references.bib"),
    manuscript_root: Path | None = None,
) -> ReferenceVerificationResult:
    """验证 BibTeX 条目非空、key 唯一、字段完整且正文引用可追踪。"""

    manuscript_root = manuscript_root or Path.cwd()
    if not bib_path.exists():
        return ReferenceVerificationResult(False, 0, 0, [f"missing bibliography: {bib_path}"], [])
    text = bib_path.read_text(encoding="utf-8")
    entries = _parse_bibtex(text)
    failures: list[str] = []
    keys = [entry["key"] for entry in entries]
    if not entries:
        failures.append("bibliography is empty")
    duplicated = sorted({key for key in keys if keys.count(key) > 1})
    failures.extend(f"duplicated citation key: {key}" for key in duplicated)
    verified_entries: list[dict[str, str]] = []
    for entry in entries:
        missing = [field for field in ("title", "author", "year") if not entry.get(field)]
        if missing:
            failures.append(f"{entry['key']}: missing required fields {missing}")
            continue
        if not any(entry.get(field) for field in ("doi", "arxiv", "url", "note", "isbn")):
            failures.append(f"{entry['key']}: missing verifiable identifier")
            continue
        verified_entries.append(entry)
    cited = _cited_keys(manuscript_root)
    orphan = sorted(set(keys) - cited)
    missing_citations = sorted(cited - set(keys))
    failures.extend(f"bibliography entry not cited: {key}" for key in orphan)
    failures.extend(f"citation without bibliography entry: {key}" for key in missing_citations)
    return ReferenceVerificationResult(
        passed=not failures and bool(verified_entries),
        entry_count=len(verified_entries),
        cited_key_count=len(cited),
        failures=failures,
        entry_keys=keys,
    )


def _parse_bibtex(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for match in re.finditer(
        r"@(?P<type>\w+)\s*\{\s*(?P<key>[^,]+),(?P<body>.*?)(?=\n@\w+\s*\{|\Z)", text, re.S
    ):
        body = match.group("body").strip()
        if body.endswith("}"):
            body = body[:-1]
        fields = {
            field.lower(): value.strip().strip("{}").strip('"')
            for field, value in re.findall(
                r"(\w+)\s*=\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\"[^\"]*\"|[^,\n]+)", body
            )
        }
        fields["type"] = match.group("type").lower()
        fields["key"] = match.group("key").strip()
        if (
            fields["type"] == "misc"
            and fields.get("eprint")
            and fields.get("archiveprefix", "").lower() == "arxiv"
        ):
            fields["arxiv"] = fields["eprint"]
        entries.append(fields)
    return entries


def _cited_keys(root: Path) -> set[str]:
    keys: set[str] = set()
    for base in [root / "docs/thesis", root / "thesis", root / "artifacts/thesis_report"]:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in {".md", ".tex"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            keys.update(re.findall(r"@\s*([A-Za-z0-9:_-]+)", text))
            keys.update(re.findall(r"\\cite\{([^}]+)\}", text))
    expanded: set[str] = set()
    for key in keys:
        expanded.update(part.strip() for part in key.split(",") if part.strip())
    return expanded


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify thesis references.")
    parser.add_argument("--bib", type=Path, default=Path("thesis/references.bib"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("thesis/generated/reference_verification.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/thesis/参考文献核验报告.md"),
    )
    args = parser.parse_args()
    result = verify_references(bib_path=args.bib, manuscript_root=args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result.__dict__, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(_render_report(result, args.bib), encoding="utf-8")
    if not result.passed:
        for failure in result.failures:
            print(f"reference-verification-failed: {failure}")
        return 1
    print(
        f"reference verification passed entries={result.entry_count} cited={result.cited_key_count}"
    )
    return 0


def _render_report(result: ReferenceVerificationResult, bib_path: Path) -> str:
    status = "PASSED" if result.passed else "FAILED"
    failures = "\n".join(f"- {failure}" for failure in result.failures) or "- 无"
    keys = "\n".join(f"- `{key}`" for key in result.entry_keys) or "- 无"
    return f"""# 参考文献核验报告

- 状态：{status}
- BibTeX 文件：`{bib_path}`
- 正式核验条目数：{result.entry_count}
- 正文引用 key 数：{result.cited_key_count}
- 核验范围：仓库级元数据核验；不声明已经满足学校最终格式。
- 核验规则：key 唯一、title/author/year 必填、正文存在引用。
- 可核验标识：每条至少包含 DOI、arXiv、ISBN、标准编号或官方 URL 之一。

## 条目 Key

{keys}

## 失败项

{failures}
"""


if __name__ == "__main__":
    raise SystemExit(main())
