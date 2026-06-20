#!/usr/bin/env python
"""验证论文 Markdown、LaTeX、DOCX 和 PDF 构建状态。"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Check thesis build status.")
    parser.add_argument(
        "--status",
        type=Path,
        default=Path("artifacts/thesis_report/build_status.json"),
    )
    args = parser.parse_args()
    if not args.status.exists():
        print(f"missing build status: {args.status}")
        return 1
    payload = json.loads(args.status.read_text(encoding="utf-8"))
    failures: list[str] = []
    for key in ["markdown", "latex"]:
        path = Path(str(payload.get(key, "")))
        if not path.exists() or path.stat().st_size <= 0:
            failures.append(f"{key} missing or empty: {path}")
    docx = payload.get("docx", {})
    if not isinstance(docx, dict) or docx.get("status") != "BUILT_AND_VALIDATED":
        failures.append("docx is not BUILT_AND_VALIDATED")
    else:
        failures.extend(_validate_docx(Path(str(docx["path"]))))
    pdf = payload.get("pdf", {})
    if not isinstance(pdf, dict) or pdf.get("status") != "BUILT_AND_VALIDATED":
        failures.append("pdf is not BUILT_AND_VALIDATED")
    else:
        path = Path(str(pdf["path"]))
        if not path.exists() or path.stat().st_size <= 0:
            failures.append(f"pdf missing or empty: {path}")
        if int(pdf.get("pages") or 0) <= 0:
            failures.append("pdf page count is not positive")
        if not str(pdf.get("sha256", "")):
            failures.append("pdf sha256 missing")
    if failures:
        for failure in failures:
            print(f"thesis-build-failed: {failure}")
        return 1
    print(
        "thesis build check passed "
        f"docx={docx.get('size_bytes')}B "
        f"pdf={pdf.get('size_bytes')}B pages={pdf.get('pages')}"
    )
    return 0


def _validate_docx(path: Path) -> list[str]:
    failures: list[str] = []
    if not path.exists() or path.stat().st_size <= 0:
        return [f"docx missing or empty: {path}"]
    try:
        with zipfile.ZipFile(path) as archive:
            text = archive.read("word/document.xml").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile) as exc:
        return [f"docx cannot be unpacked: {exc}"]
    for marker in ["面向边缘智能场景的小型机械臂云边协同控制系统的设计", "摘要", "结论"]:
        if marker not in text:
            failures.append(f"docx missing marker: {marker}")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
