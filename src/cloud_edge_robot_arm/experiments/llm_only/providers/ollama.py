"""Ollama provider adapter for local LLM-only experiments."""

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

OllamaTransport = Callable[[str, str, dict[str, object] | None, float], Mapping[str, Any]]


class OllamaProvider:
    """Local Ollama HTTP provider. It never pulls or downloads models."""

    provider_name = "ollama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float = 30.0,
        transport: OllamaTransport | None = None,
    ) -> None:
        configured_base_url = base_url
        if configured_base_url is None:
            configured_base_url = os.getenv("BIGSMALL_OLLAMA_BASE_URL")
        if configured_base_url is None:
            configured_base_url = "http://127.0.0.1:11434"
        self.base_url = configured_base_url.rstrip("/")
        configured_model = model_name
        if configured_model is None:
            configured_model = os.getenv("BIGSMALL_OLLAMA_MODEL")
        self.model_name: str = configured_model or ""
        self.timeout_seconds = timeout_seconds
        self._transport = transport or self._default_transport

    def health_check(self) -> ProviderHealth:
        """Check daemon and installed model list without downloading anything."""

        blockers: list[str] = []
        if not self._loopback_allowed():
            blockers.append("OLLAMA_REMOTE_ENDPOINT_NOT_ALLOWED")
        version = ""
        models: list[str] = []
        if not blockers:
            try:
                version_payload = self._transport(
                    "GET",
                    f"{self.base_url}/api/version",
                    None,
                    self.timeout_seconds,
                )
                version_value = version_payload.get("version")
                version = version_value if isinstance(version_value, str) else ""
                tags_payload = self._transport(
                    "GET",
                    f"{self.base_url}/api/tags",
                    None,
                    self.timeout_seconds,
                )
                models = _model_names(tags_payload)
            except Exception:  # noqa: BLE001 - health result must be sanitized
                blockers.append("OLLAMA_DAEMON_UNREACHABLE")
        if not self.model_name:
            blockers.append("OLLAMA_MODEL_NOT_CONFIGURED")
        elif models and self.model_name not in models:
            blockers.append("OLLAMA_MODEL_NOT_INSTALLED")
        return ProviderHealth(
            provider=self.provider_name,
            model_name=self.model_name,
            ready=not blockers,
            runtime_type="LOCAL_LLM_RUNTIME" if not blockers else "BLOCKED_BY_ENV",
            installed_model_count=len(models),
            version=version,
            endpoint_hash=endpoint_hash(self.base_url),
            blockers=blockers,
        )

    def complete(self, *, prompt: str, request_id: str) -> ProviderResponse:
        """Run local OpenAI-compatible chat completion against Ollama."""

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
            "temperature": 0,
        }
        start = perf_counter()
        try:
            response = self._transport(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                payload,
                self.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            return ProviderResponse(
                provider=self.provider_name,
                model_name=self.model_name,
                runtime_type="LOCAL_LLM_RUNTIME",
                accepted=False,
                content="",
                sanitized_response=sanitized_json({"error": message}),
                prompt_hash=stable_hash(prompt),
                response_hash=stable_hash(message),
                latency_ms=(perf_counter() - start) * 1000,
                request_id=request_id,
                error_code="OLLAMA_HTTP_ERROR",
                error_message="ollama request failed",
            )
        sanitized = sanitized_json(response)
        content = _extract_content(response)
        return ProviderResponse(
            provider=self.provider_name,
            model_name=self.model_name,
            runtime_type="LOCAL_LLM_RUNTIME",
            accepted=bool(content),
            content=content,
            sanitized_response=sanitized,
            prompt_hash=stable_hash(prompt),
            response_hash=stable_hash(sanitized),
            latency_ms=(perf_counter() - start) * 1000,
            request_id=request_id,
            token_usage=_extract_usage(response),
        )

    def _loopback_allowed(self) -> bool:
        return self.base_url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]"))

    @staticmethod
    def _default_transport(
        method: str,
        url: str,
        payload: dict[str, object] | None,
        timeout: float,
    ) -> Mapping[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = response.read(1_000_000)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"http_status={exc.code}") from exc
        loaded = json.loads(body.decode("utf-8"))
        if not isinstance(loaded, Mapping):
            raise RuntimeError("non_object_response")
        return loaded


def _model_names(payload: Mapping[str, Any]) -> list[str]:
    models = payload.get("models")
    names: list[str] = []
    if isinstance(models, list):
        for item in models:
            if isinstance(item, Mapping):
                name = item.get("name")
                if isinstance(name, str):
                    names.append(name)
    return sorted(names)


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
