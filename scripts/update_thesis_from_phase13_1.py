#!/usr/bin/env python
"""更新论文 Phase 13.1 摘要文件，但不加入未经证据支持的性能结论。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Write Phase 13.1 thesis update summary.")
    parser.add_argument("--root", type=Path, default=Path("artifacts/phase13_1"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/thesis/phase13_1_真实模型回填说明.md"),
    )
    args = parser.parse_args()
    verification_path = args.root / "verification/phase13_1_summary.json"
    verification = (
        json.loads(verification_path.read_text(encoding="utf-8"))
        if verification_path.exists()
        else {"status": "NOT_RUN"}
    )
    accepted = int(verification.get("accepted_count", 0) or 0)
    if accepted > 0:
        text = (
            "# Phase 13.1 真实模型证据回填说明\n\n"
            f"当前已形成 {accepted} 条真实模型 accepted evidence。"
            "论文性能结论仍需人工审阅后合并。\n"
        )
    else:
        text = (
            "# Phase 13.1 真实模型证据回填说明\n\n"
            "当前环境未形成真实 OpenAI-compatible 或 Ollama runtime accepted evidence。"
            "论文继续保持 NOT_AVAILABLE 表述，不使用 fake provider 结果生成性能结论。\n"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
