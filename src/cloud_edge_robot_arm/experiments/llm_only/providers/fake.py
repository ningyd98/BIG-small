"""确定性 fake provider，只用于 pipeline 检查，绝不能作为真实模型证据。"""

from __future__ import annotations

from time import perf_counter

from cloud_edge_robot_arm.experiments.llm_only.providers.base import (
    ProviderHealth,
    ProviderResponse,
)
from cloud_edge_robot_arm.experiments.llm_only.providers.redaction import stable_hash


class FakeLLMProvider:
    """Pipeline-only provider that must never be treated as real model evidence."""

    provider_name = "fake"

    def __init__(self, *, model_name: str = "fake-pipeline") -> None:
        self.model_name = model_name

    def health_check(self) -> ProviderHealth:
        """Fake provider is available for pipeline tests only."""

        return ProviderHealth(
            provider=self.provider_name,
            model_name=self.model_name,
            ready=True,
            runtime_type="FAKE_PROVIDER_PIPELINE_TEST",
        )

    def complete(self, *, prompt: str, request_id: str) -> ProviderResponse:
        """Return deterministic non-authoritative content."""

        start = perf_counter()
        content = f"fake-contract:{stable_hash(prompt)[:16]}"
        sanitized = f'{{"content":"{content}","provider":"fake"}}'
        return ProviderResponse(
            provider=self.provider_name,
            model_name=self.model_name,
            runtime_type="FAKE_PROVIDER_PIPELINE_TEST",
            accepted=False,
            content=content,
            sanitized_response=sanitized,
            prompt_hash=stable_hash(prompt),
            response_hash=stable_hash(sanitized),
            latency_ms=(perf_counter() - start) * 1000,
            request_id=request_id,
        )
