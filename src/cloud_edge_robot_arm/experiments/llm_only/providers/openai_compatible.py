"""OpenAI-compatible provider adapter for real LLM-only experiments."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

from cloud_edge_robot_arm.experiments.llm_only.providers.base import (
    ProviderHealth,
    ProviderResponse,
)
from cloud_edge_robot_arm.experiments.llm_only.providers.redaction import (
    endpoint_hash,
    sanitized_json,
    stable_hash,
)

Transport = Callable[[str, dict[str, object], dict[str, str], float], Mapping[str, Any]]


class OpenAICompatibleProvider:
    """Safe chat-completions client with explicit paid-call authorization."""

    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float = 30.0,
        temperature: float = 0.0,
        max_tokens: int = 800,
        allow_paid_model_call: bool = False,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.allow_paid_model_call = allow_paid_model_call
        self._transport = transport or self._default_transport

    @classmethod
    def from_environment(
        cls,
        *,
        allow_paid_model_call: bool = False,
        transport: Transport | None = None,
    ) -> OpenAICompatibleProvider:
        """Build provider from BIGSMALL_LLM_* environment variables."""

        timeout = float(os.getenv("BIGSMALL_LLM_TIMEOUT_SECONDS", "30"))
        return cls(
            base_url=os.getenv("BIGSMALL_LLM_BASE_URL", ""),
            api_key=os.getenv("BIGSMALL_LLM_API_KEY", ""),
            model_name=os.getenv("BIGSMALL_LLM_MODEL", ""),
            timeout_seconds=timeout,
            allow_paid_model_call=allow_paid_model_call,
            transport=transport,
        )

    def health_check(self) -> ProviderHealth:
        """Validate local configuration without issuing paid inference."""

        blockers: list[str] = []
        if not self.base_url:
            blockers.append("OPENAI_COMPATIBLE_BASE_URL_NOT_CONFIGURED")
        if not self.api_key:
            blockers.append("OPENAI_COMPATIBLE_API_KEY_NOT_CONFIGURED")
        if not self.model_name:
            blockers.append("OPENAI_COMPATIBLE_MODEL_NOT_CONFIGURED")
        if not self.allow_paid_model_call:
            blockers.append("PAID_MODEL_CALL_NOT_AUTHORIZED")
        if self.base_url and not self.base_url.startswith(
            ("https://", "http://127.0.0.1", "http://localhost")
        ):
            blockers.append("OPENAI_COMPATIBLE_ENDPOINT_NOT_ALLOWED")
        return ProviderHealth(
            provider=self.provider_name,
            model_name=self.model_name,
            ready=not blockers,
            runtime_type="REAL_LLM_RUNTIME" if not blockers else "BLOCKED_BY_ENV",
            secret_configured=bool(self.api_key),
            endpoint_hash=endpoint_hash(self.base_url),
            blockers=blockers,
        )

    def complete(self, *, prompt: str, request_id: str) -> ProviderResponse:
        """Run one chat completion and return sanitized evidence."""

        health = self.health_check()
        if not health.ready:
            return ProviderResponse(
                provider=self.provider_name,
                model_name=self.model_name,
                runtime_type="BLOCKED_BY_ENV",
                accepted=False,
                content="",
                sanitized_response=sanitized_json({"blockers": health.blockers}),
                prompt_hash=stable_hash(prompt),
                response_hash=stable_hash("|".join(health.blockers)),
                latency_ms=0.0,
                request_id=request_id,
                error_code="PROVIDER_NOT_READY",
                error_message=";".join(health.blockers),
            )
        payload: dict[str, object] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-BIGSMALL-Request-ID": request_id,
        }
        start = perf_counter()
        try:
            response = self._transport(
                f"{self.base_url}/chat/completions",
                payload,
                headers,
                self.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - converted to sanitized evidence
            latency_ms = (perf_counter() - start) * 1000
            message = str(exc)
            return ProviderResponse(
                provider=self.provider_name,
                model_name=self.model_name,
                runtime_type="REAL_LLM_RUNTIME",
                accepted=False,
                content="",
                sanitized_response=sanitized_json({"error": message}, secrets=[self.api_key]),
                prompt_hash=stable_hash(prompt),
                response_hash=stable_hash(message),
                latency_ms=latency_ms,
                request_id=request_id,
                error_code="PROVIDER_HTTP_ERROR",
                error_message="provider request failed",
            )
        latency_ms = (perf_counter() - start) * 1000
        content = _extract_content(response)
        sanitized = sanitized_json(response, secrets=[self.api_key])
        return ProviderResponse(
            provider=self.provider_name,
            model_name=self.model_name,
            runtime_type="REAL_LLM_RUNTIME",
            accepted=bool(content),
            content=content,
            sanitized_response=sanitized,
            prompt_hash=stable_hash(prompt),
            response_hash=stable_hash(sanitized),
            latency_ms=latency_ms,
            request_id=request_id,
            token_usage=_extract_usage(response),
        )

    @staticmethod
    def _default_transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout: float,
    ) -> Mapping[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = response.read(1_000_000)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"http_status={exc.code}") from exc
        loaded = json.loads(body.decode("utf-8"))
        if not isinstance(loaded, Mapping):
            raise RuntimeError("non_object_response")
        return loaded


def _extract_content(payload: Mapping[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, Mapping):
            message = first.get("message")
            if isinstance(message, Mapping):
                content = message.get("content")
                if isinstance(content, str):
                    return content
    return ""


def _extract_usage(payload: Mapping[str, Any]) -> Mapping[str, int] | str:
    usage = payload.get("usage")
    if isinstance(usage, Mapping):
        parsed: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                parsed[key] = value
        return parsed or "NOT_AVAILABLE"
    return "NOT_AVAILABLE"
