"""租约时间工具。

所有 lease deadline 使用 UTC，避免本地时区变化影响 worker crash 恢复判断。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def lease_deadline(ttl_seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=ttl_seconds)
