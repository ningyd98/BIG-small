"""LLM-only provider 协议和脱敏响应模型，供真实与 fake provider 共用。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ProviderHealth:
    """Sanitized provider readiness result."""

    provider: str
    model_name: str
    ready: bool
    runtime_type: str
    secret_configured: bool = False
    installed_model_count: int = 0
    version: str = ""
    endpoint_hash: str = ""
    blockers: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderResponse:
    """Sanitized model response evidence."""

    provider: str
    model_name: str
    runtime_type: str
    accepted: bool
    content: str
    sanitized_response: str
    prompt_hash: str
    response_hash: str
    latency_ms: float
    request_id: str
    token_usage: Mapping[str, int] | str = "NOT_AVAILABLE"
    error_code: str = ""
    error_message: str = ""


class LLMProvider(Protocol):
    """Minimal provider interface used by the experiment runner."""

    provider_name: str
    model_name: str

    def health_check(self) -> ProviderHealth:
        """Return sanitized readiness information."""
        ...

    def complete(self, *, prompt: str, request_id: str) -> ProviderResponse:
        """Run a single chat-completion style request."""
        ...
