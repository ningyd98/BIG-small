"""LLM-only artifact 写入工具。

所有文件写入使用确定性 JSON，且只保存 hash 后的 prompt/response，不保存 API key、
Authorization header 或原始 secret。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def stable_hash(payload: str | bytes) -> str:
    """返回稳定 SHA-256。"""

    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """写出 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """写出 JSONL。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    """计算文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()
