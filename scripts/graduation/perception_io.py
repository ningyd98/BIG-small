"""Exclusive storage and byte pins shared by the independent development stages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MODES = ("NONE", "SUBPIX")


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_bytes())


def write(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def pinned(path: Path, expected: str) -> Any:
    if sha(path) != expected:
        raise ValueError(f"source SHA256 mismatch: {path.name}")
    return read(path)


def check_sources(allocation: dict) -> None:
    for path, expected in allocation["sources_sha256"].items():
        if sha(ROOT / path) != expected:
            raise ValueError(f"development source changed: {path}")
