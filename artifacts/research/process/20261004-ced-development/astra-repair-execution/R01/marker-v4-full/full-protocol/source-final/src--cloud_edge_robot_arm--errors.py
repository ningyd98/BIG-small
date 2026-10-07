"""统一错误模型，保证 API、运行时和测试可以用稳定 code 判断失败原因。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StructuredError(BaseModel):
    """结构化错误响应，用稳定 code 替代原始异常泄露。"""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    category: str = "SYSTEM"
    details: dict[str, Any] = Field(default_factory=dict)
