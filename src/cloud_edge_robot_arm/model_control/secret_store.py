"""模型 API key 的安全存储抽象。"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol

from cloud_edge_robot_arm.model_control.models import SecretStoreKind


class SecretStoreError(ValueError):
    """Public failures carry no paths, OS errors or credential contents."""

    def __init__(self) -> None:
        super().__init__("model_secret_store_unavailable")


class SecretStore(Protocol):
    """SecretStore 只按 profile id 存取 secret，不暴露批量 dump 接口。"""

    kind: SecretStoreKind

    def set_secret(self, profile_id: str, value: str) -> None:
        """保存单个 profile 的 secret。"""
        ...

    def get_secret(self, profile_id: str) -> str | None:
        """读取单个 profile 的 secret。"""
        ...

    def delete_secret(self, profile_id: str) -> None:
        """删除单个 profile 的 secret。"""
        ...

    def has_secret(self, profile_id: str) -> bool:
        """判断 profile 是否已配置 secret。"""
        ...


class InMemorySecretStore:
    """进程内 secret store，适合 CI 和本地 session-only 模式。"""

    kind = SecretStoreKind.SESSION_ONLY

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    def set_secret(self, profile_id: str, value: str) -> None:
        """在进程内保存 secret，进程退出后自动丢失。"""

        self._secrets[profile_id] = value

    def get_secret(self, profile_id: str) -> str | None:
        """读取进程内 secret。"""

        return self._secrets.get(profile_id)

    def delete_secret(self, profile_id: str) -> None:
        """删除进程内 secret。"""

        self._secrets.pop(profile_id, None)

    def has_secret(self, profile_id: str) -> bool:
        """检查进程内是否存在 secret。"""

        return profile_id in self._secrets


def create_secret_store(database_path: Path) -> SecretStore:
    """Use stable private user data, with a separate namespace for each DB path."""

    mode = os.environ.get("MODEL_CONTROL_SECRET_STORE", "ENCRYPTED_FILE")
    if mode == SecretStoreKind.SESSION_ONLY:
        return InMemorySecretStore()
    if mode != SecretStoreKind.ENCRYPTED_FILE:
        raise SecretStoreError() from None
    from cloud_edge_robot_arm.model_control.encrypted_secret_store import EncryptedFileSecretStore

    override = os.environ.get("MODEL_CONTROL_SECRET_DIR")
    if override is not None:
        directory = Path(override)
    else:
        try:
            configured_base = os.environ.get("XDG_DATA_HOME", "")
            data_base = (
                Path(configured_base) if configured_base else Path.home() / ".local" / "share"
            )
            if not data_base.is_absolute():
                raise SecretStoreError()
            database_identity = os.path.abspath(os.fspath(database_path)).encode("utf-8")
            namespace = hashlib.sha256(database_identity).hexdigest()
            directory = data_base / "BIGsmall" / "model-control-secrets" / namespace
        except (OSError, ValueError, RuntimeError):
            raise SecretStoreError() from None
    return EncryptedFileSecretStore(directory)
