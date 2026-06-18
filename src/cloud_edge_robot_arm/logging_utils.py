"""日志配置工具，避免各模块重复初始化 handler 或泄露敏感路径。"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any


def build_json_log_record(
    *,
    level: int,
    event: str,
    message: str,
    task_id: str | None = None,
    plan_version: int | None = None,
    command_seq: int | None = None,
    extra: Mapping[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> str:
    occurred_at = timestamp if timestamp is not None else datetime.now(UTC)
    payload: dict[str, Any] = {
        "timestamp": occurred_at.isoformat(),
        "level": logging.getLevelName(level),
        "event": event,
        "message": message,
    }
    if task_id is not None:
        payload["task_id"] = task_id
    if plan_version is not None:
        payload["plan_version"] = plan_version
    if command_seq is not None:
        payload["command_seq"] = command_seq
    if extra is not None:
        payload.update(dict(extra))
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
