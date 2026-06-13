from __future__ import annotations

from datetime import UTC, datetime


def scene_is_fresh(
    scene_updated_at: datetime | None,
    staleness_ms: int,
    *,
    now: datetime | None = None,
) -> bool:
    if scene_updated_at is None:
        return True
    checked_at = now or datetime.now(UTC)
    age_ms = (checked_at - scene_updated_at).total_seconds() * 1000
    return age_ms <= staleness_ms


def telemetry_is_fresh(
    telemetry_timestamp: datetime | None,
    staleness_ms: int,
    *,
    now: datetime | None = None,
) -> bool:
    if telemetry_timestamp is None:
        return True
    checked_at = now or datetime.now(UTC)
    age_ms = (checked_at - telemetry_timestamp).total_seconds() * 1000
    return age_ms <= staleness_ms
