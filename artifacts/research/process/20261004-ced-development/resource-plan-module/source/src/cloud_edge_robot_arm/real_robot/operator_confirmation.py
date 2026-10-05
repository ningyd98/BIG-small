"""现场操作员确认模型。

确认记录只保存哈希和时间戳，不保存个人敏感信息或明文 token。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class OperatorConfirmation(BaseModel):
    model_config = ConfigDict(frozen=True)

    confirmation_id: str = Field(min_length=1)
    token_hash: str = Field(min_length=16)
    issued_at: datetime
    expires_at: datetime
    allowed_robot_hash: str = Field(min_length=1)
    allowed_config_hash: str = Field(min_length=1)
    allowed_level: str = Field(min_length=1)
    allowed_action: str = Field(min_length=1)
    consumed_at: datetime | None = None
    local_origin_verified: bool

    @classmethod
    def issue(
        cls,
        *,
        confirmation_id: str,
        token: str,
        issued_at: datetime,
        expires_at: datetime,
        allowed_robot_hash: str,
        allowed_config_hash: str,
        allowed_level: str,
        allowed_action: str,
        local_origin_verified: bool,
    ) -> OperatorConfirmation:
        if expires_at <= issued_at:
            raise ValueError("operator confirmation expires_at must be after issued_at")
        return cls(
            confirmation_id=confirmation_id,
            token_hash=_hash_token(token),
            issued_at=issued_at,
            expires_at=expires_at,
            allowed_robot_hash=allowed_robot_hash,
            allowed_config_hash=allowed_config_hash,
            allowed_level=allowed_level,
            allowed_action=allowed_action,
            local_origin_verified=local_origin_verified,
        )

    def consume(
        self,
        *,
        token: str,
        robot_hash: str,
        config_hash: str,
        level: str,
        action: str,
        now: datetime | None = None,
    ) -> OperatorConfirmation:
        checked_at = now or datetime.now(UTC)
        if self.consumed_at is not None:
            raise ValueError("operator confirmation already consumed")
        if checked_at > self.expires_at:
            raise ValueError("operator confirmation expired")
        if _hash_token(token) != self.token_hash:
            raise ValueError("operator confirmation token mismatch")
        if robot_hash != self.allowed_robot_hash:
            raise ValueError("operator confirmation robot mismatch")
        if config_hash != self.allowed_config_hash:
            raise ValueError("operator confirmation config mismatch")
        if level != self.allowed_level:
            raise ValueError("operator confirmation level mismatch")
        if action != self.allowed_action:
            raise ValueError("operator confirmation action mismatch")
        if not self.local_origin_verified:
            raise ValueError("operator confirmation local origin is not verified")
        return self.model_copy(update={"consumed_at": checked_at})

    def artifact_metadata(self) -> dict[str, object]:
        return {
            "confirmation_id": self.confirmation_id,
            "token_hash": self.token_hash,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "allowed_robot_hash": self.allowed_robot_hash,
            "allowed_config_hash": self.allowed_config_hash,
            "allowed_level": self.allowed_level,
            "allowed_action": self.allowed_action,
            "consumed_at": self.consumed_at.isoformat() if self.consumed_at else None,
            "local_origin_verified": self.local_origin_verified,
        }


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
