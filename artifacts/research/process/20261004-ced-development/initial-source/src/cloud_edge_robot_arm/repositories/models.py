"""结构化数据模型，作为 API、测试和服务之间的稳定契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AcceptedCommandDecision:
    accepted: bool
    code: str
    message: str
    existing_hash: str | None = None


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    plan_version: int
    command_seq: int
    state: str
    contract_json: str
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class StateTransitionRecord:
    task_id: str
    from_state: str
    to_state: str
    reason: str
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class StepExecutionRecord:
    task_id: str
    step_id: str
    skill: str
    attempt: int
    success: bool
    error_code: str | None
    duration_ms: int
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class ActionExecutionRecord:
    task_id: str
    step_id: str
    action_id: str
    action_type: str
    success: bool
    error_code: str | None
    duration_ms: int
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class AcceptedCommandRecord:
    task_id: str
    plan_version: int
    command_seq: int
    payload_hash: str
    accepted_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class AuditEventRecord:
    task_id: str
    event_type: str
    details: dict[str, object]
    timestamp: datetime = field(default_factory=utc_now)
