"""Redaction and stable hashing helpers for LLM-only provider evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_hash(payload: str | bytes) -> str:
    """Return a stable SHA-256 hex digest."""

    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(data).hexdigest()


def endpoint_hash(endpoint: str) -> str:
    """Hash an endpoint so artifacts do not expose internal URLs verbatim."""

    return stable_hash(endpoint) if endpoint else ""


def redact_text(text: str, secrets: list[str]) -> str:
    """Remove known secret values from text."""

    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = redacted.replace("Authorization", "[REDACTED_HEADER]")
    redacted = redacted.replace("Bearer ", "[REDACTED_BEARER] ")
    return redacted


def sanitized_json(payload: Any, *, secrets: list[str] | None = None) -> str:
    """Serialize payload deterministically and redact known secret values."""

    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return redact_text(text, secrets or [])
