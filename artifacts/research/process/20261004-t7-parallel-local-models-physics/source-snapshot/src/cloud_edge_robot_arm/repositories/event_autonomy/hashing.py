"""事件自治哈希工具，用于幂等键和证据一致性校验。

Stable payload hashes for persisted event-autonomy records.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def stable_payload_hash(value: Any, *, ignore_fields: set[str] | None = None) -> str:
    """Return a deterministic SHA-256 hash for pydantic models or JSON values."""
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    if ignore_fields and isinstance(payload, dict):
        payload = {k: v for k, v in payload.items() if k not in ignore_fields}
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
