"""模型 API key 的安全存储抽象。"""

from __future__ import annotations

from typing import Protocol

from cloud_edge_robot_arm.model_control.models import SecretStoreKind


class SecretStore(Protocol):
    """SecretStore 只按 profile id 存取 secret，不暴露批量 dump 接口。"""

    kind: SecretStoreKind

    def set_secret(self, profile_id: str, value: str) -> None: ...

    def get_secret(self, profile_id: str) -> str | None: ...

    def delete_secret(self, profile_id: str) -> None: ...

    def has_secret(self, profile_id: str) -> bool: ...


class InMemorySecretStore:
    """进程内 secret store，适合 CI 和本地 session-only 模式。"""

    kind = SecretStoreKind.SESSION_ONLY

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    def set_secret(self, profile_id: str, value: str) -> None:
        self._secrets[profile_id] = value

    def get_secret(self, profile_id: str) -> str | None:
        return self._secrets.get(profile_id)

    def delete_secret(self, profile_id: str) -> None:
        self._secrets.pop(profile_id, None)

    def has_secret(self, profile_id: str) -> bool:
        return profile_id in self._secrets
