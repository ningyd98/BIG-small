from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class CancellationRecord:
    requested_at: datetime
    acknowledged_at: datetime | None = None
    terminated_at: datetime | None = None
    force_killed: bool = False


def requested_now() -> CancellationRecord:
    return CancellationRecord(requested_at=datetime.now(UTC))
