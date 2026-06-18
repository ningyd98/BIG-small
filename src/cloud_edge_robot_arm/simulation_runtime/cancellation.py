"""取消过程的数据模型。

取消记录只描述运行时信号和进程处理结果，不删除已有 evidence，也不把 timeout
伪装成用户取消。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class CancellationRecord:
    """一次取消请求的审计字段。"""

    requested_at: datetime
    acknowledged_at: datetime | None = None
    terminated_at: datetime | None = None
    force_killed: bool = False


def requested_now() -> CancellationRecord:
    return CancellationRecord(requested_at=datetime.now(UTC))
