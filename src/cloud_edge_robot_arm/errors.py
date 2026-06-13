from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StructuredError(BaseModel):
    """A machine-readable error returned instead of leaking raw exceptions."""

    model_config = ConfigDict(frozen=True)

    code: str
    message: str
    category: str = "SYSTEM"
    details: dict[str, Any] = Field(default_factory=dict)
