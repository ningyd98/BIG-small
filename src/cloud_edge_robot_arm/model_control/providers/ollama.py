"""Ollama HTTP 客户端接口。

生产实现后续通过 HTTP API 调用 Ollama；测试可以注入同名方法的 fake transport。
这里不执行 ``ollama`` CLI，也不允许任意下载 URL。
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Protocol, cast


class OllamaTransport(Protocol):
    """Ollama 传输协议，便于测试注入 fake server。"""

    def get_version(self) -> dict[str, Any]:
        """读取 Ollama daemon 版本。"""
        ...

    def list_models(self) -> list[dict[str, Any]]:
        """列出已安装模型。"""
        ...

    def show_model(self, model_name: str) -> dict[str, Any]:
        """读取指定模型详情。"""
        ...

    def pull_model(self, model_name: str) -> list[dict[str, Any]]:
        """通过 HTTP pull 流下载指定模型。"""
        ...

    def chat(self, model_name: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        """调用 OpenAI-compatible chat completions 接口。"""
        ...


class OllamaHttpClient:
    """基于 Ollama REST API 的最小客户端。"""

    def __init__(self, *, base_url: str = "http://127.0.0.1:11434", timeout_s: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def get_version(self) -> dict[str, Any]:
        """读取本地 Ollama 版本。"""

        return self._json("GET", "/api/version")

    def list_models(self) -> list[dict[str, Any]]:
        """返回 Ollama `/api/tags` 中的模型列表。"""

        payload = self._json("GET", "/api/tags")
        return list(payload.get("models", []))

    def show_model(self, model_name: str) -> dict[str, Any]:
        """返回单个模型的详情元数据。"""

        return self._json("POST", "/api/show", {"model": model_name})

    def pull_model(self, model_name: str) -> list[dict[str, Any]]:
        """拉取模型并解析 Ollama NDJSON 进度事件。"""

        response = self._raw("POST", "/api/pull", {"model": model_name, "stream": True})
        rows: list[dict[str, Any]] = []
        for line in response.splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def chat(self, model_name: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        """向本地模型发送 chat completion 测试请求。"""

        return self._json(
            "POST",
            "/v1/chat/completions",
            {"model": model_name, "messages": messages, "stream": False},
        )

    def _json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parsed = json.loads(self._raw(method, path, payload))
        return cast(dict[str, Any], parsed)

    def _raw(self, method: str, path: str, payload: dict[str, Any] | None = None) -> str:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            body = response.read(4_000_000).decode("utf-8")
            return cast(str, body)
