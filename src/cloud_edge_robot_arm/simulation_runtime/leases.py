from __future__ import annotations

from datetime import UTC, datetime, timedelta


def lease_deadline(ttl_seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=ttl_seconds)
