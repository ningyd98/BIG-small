"""本地模型下载任务模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ModelDownloadStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    CONNECTING = "CONNECTING"
    DOWNLOADING = "DOWNLOADING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"


class ModelDownloadJob(BaseModel):
    download_id: str
    provider: str = "OLLAMA"
    model_name: str
    status: ModelDownloadStatus = ModelDownloadStatus.CREATED
    total_bytes: int = 0
    completed_bytes: int = 0
    progress_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    digest: str = ""
    current_layer: str = ""
    message: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str = ""
    error_message: str = ""
    requested_by: str = ""
    cancel_requested: bool = False
