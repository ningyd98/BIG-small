"""模型控制中心的数据模型。

响应模型刻意包含 ``api_key`` 的 write-only 占位字段，便于测试确认它始终为
None；真实 secret 只通过 SecretStore 保存，不进入 SQLite、日志或 artifact。
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class PlannerProviderKind(StrEnum):
    """支持的 Planner provider 类型。"""

    MOCK = "MOCK"
    RULE_BASED = "RULE_BASED"
    OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE"
    OLLAMA = "OLLAMA"


class SecretStoreKind(StrEnum):
    """Secret 存储模式。"""

    SESSION_ONLY = "SESSION_ONLY"
    ENVIRONMENT = "ENVIRONMENT"
    ENCRYPTED_FILE = "ENCRYPTED_FILE"


class ModelProviderProfile(BaseModel):
    """非敏感模型 profile。"""

    profile_id: str
    display_name: str
    provider_kind: PlannerProviderKind
    base_url: str = ""
    chat_completions_path: str = "/v1/chat/completions"
    model_name: str
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout_seconds: float = 30.0
    max_retries: int = 2
    json_mode: bool = True
    enabled: bool = True
    active: bool = False
    secret_present: bool = False
    secret_store_kind: SecretStoreKind = SecretStoreKind.SESSION_ONLY
    endpoint_hash: str = ""
    config_version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    secret_updated_at: datetime | None = None
    api_key: None = None


class PlannerRuntimeStatus(BaseModel):
    """当前 active planner 状态。"""

    active_profile_id: str = ""
    active_provider: PlannerProviderKind = PlannerProviderKind.MOCK
    active_model: str = "mock"
    endpoint_hash: str = ""
    config_version: int = 0
    health: str = "READY"
    circuit_breaker: str = "CLOSED"
    last_test: dict[str, object] = Field(default_factory=dict)
