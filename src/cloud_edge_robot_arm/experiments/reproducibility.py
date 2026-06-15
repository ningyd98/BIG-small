from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def stable_hash(value: Any) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        payload = value
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def config_hash(config: BaseModel) -> str:
    payload = config.model_dump(mode="json")
    if "artifact_dir" in payload:
        payload["artifact_dir"] = "<artifact_dir>"
    return stable_hash(payload)
