from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class RuntimeJobStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    LEASED = "LEASED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLING = "CANCELLING"
    FINALIZING = "FINALIZING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    BLOCKED_BY_ENV = "BLOCKED_BY_ENV"
    INTERRUPTED = "INTERRUPTED"
    RECOVERY_PENDING = "RECOVERY_PENDING"


TERMINAL_STATUSES = {
    RuntimeJobStatus.SUCCEEDED,
    RuntimeJobStatus.FAILED,
    RuntimeJobStatus.CANCELLED,
    RuntimeJobStatus.TIMED_OUT,
    RuntimeJobStatus.BLOCKED_BY_ENV,
}


@dataclass(frozen=True)
class SimulationJobRecord:
    job_id: str
    run_id: str
    batch_id: str
    backend: str
    scenario_id: str
    control_mode: str
    seed: int
    manifest_id: str
    reproducibility_hash: str
    status: RuntimeJobStatus
    draft: dict[str, Any]
    manifest: dict[str, Any]
    attempt: int = 0
    max_attempts: int = 1
    priority: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    timeout_seconds: int = 300
    cancel_requested: bool = False
    worker_id: str = ""
    lease_id: str = ""
    lease_expires_at: datetime | None = None
    blocker_codes: list[str] = field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    artifact_root: str = ""
    artifact_paths: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    source_commit: str = ""
    source_tree_hash: str = ""


@dataclass(frozen=True)
class SimulationJobEvent:
    event_id: str
    job_id: str
    run_id: str
    sequence: int
    stream_sequence: int
    event_type: str
    previous_status: str = ""
    next_status: str = ""
    reason_code: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "simulation_runtime"
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SimulationJobLease:
    lease_id: str
    job_id: str
    worker_id: str
    acquired_at: datetime
    expires_at: datetime
    heartbeat_at: datetime
    released_at: datetime | None = None


@dataclass(frozen=True)
class SimulationJobAttempt:
    job_id: str
    run_id: str
    attempt: int
    worker_id: str
    started_at: datetime
    ended_at: datetime | None
    result: str
    error: str
    artifact_paths: dict[str, str]


@dataclass(frozen=True)
class SimulationBatchRecord:
    batch_id: str
    manifest: dict[str, Any]
    run_ids: list[str]
    total: int
    created_at: datetime
    completed_at: datetime | None = None


class RuntimeHealthResponse(BaseModel):
    status: str = "READY"
    database: str = "sqlite"
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    workers: int = Field(ge=0)
    real_controller_contacted: bool = False
    hardware_motion_observed: bool = False
    hardware_write_operations: list[str] = Field(default_factory=list)


class WorkerStatusView(BaseModel):
    worker_id: str
    backend: str
    status: str
    active_job_id: str = ""
    lease_id: str = ""
    heartbeat_at: datetime | None = None


class WorkerListResponse(BaseModel):
    workers: list[WorkerStatusView]


class QueueStatusResponse(BaseModel):
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    blocked: int = Field(ge=0)
    max_queued_jobs: int = Field(ge=0)
    max_batch_runs: int = Field(ge=0)


class AttemptView(BaseModel):
    attempt: int
    worker_id: str
    started_at: datetime
    ended_at: datetime | None = None
    result: str
    error: str = ""
    artifact_paths: dict[str, str] = Field(default_factory=dict)


class AttemptListResponse(BaseModel):
    attempts: list[AttemptView]


class RecoveryResponse(BaseModel):
    recovered_jobs: list[str] = Field(default_factory=list)
    interrupted_jobs: list[str] = Field(default_factory=list)
    incomplete_artifacts: list[str] = Field(default_factory=list)
    rerun_started: bool = False
