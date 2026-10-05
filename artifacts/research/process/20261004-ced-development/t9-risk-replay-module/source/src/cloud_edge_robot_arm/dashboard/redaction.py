"""Dashboard 脱敏工具。

所有向前端、日志和 artifact 摘要暴露的数据都应先经过这里或同等脱敏逻辑。
"""

from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = {"token", "password", "secret", "controller_address", "robot_serial"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "<redacted>" if str(key).lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        value = value.replace(str(__import__("pathlib").Path.home()), "$HOME")
        value = re.sub(r"(?i)(token|password|secret)=([^\s,;]+)", r"\1=<redacted>", value)
        return value
    return value
