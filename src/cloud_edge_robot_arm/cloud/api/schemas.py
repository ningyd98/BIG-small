"""Pydantic schemas for the cloud planning API request/response bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from cloud_edge_robot_arm.cloud.planning.models import (
    RobotCapabilities,
    SafetyPolicyReference,
    SceneSummary,
)

# ── Health ───────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime


# ── Capabilities ─────────────────────────────────────────────────────────────


class CapabilitiesResponse(BaseModel):
    supported_skills: list[str]
    supported_control_modes: list[str]
    planner_name: str
    model_name: str


# ── TaskContract Schema ──────────────────────────────────────────────────────


class TaskContractSchemaResponse(BaseModel):
    task_contract_schema: dict[str, Any]
    version: str


# ── Planning Request ─────────────────────────────────────────────────────────


class PlanningRequest(BaseModel):
    request_id: str = Field(min_length=1)
    user_instruction: str = Field(min_length=1)
    control_mode: str = Field(
        default="EVENT_TRIGGERED_EDGE_AUTONOMY",
        pattern=r"^(PERIODIC_CLOUD_SUPERVISION|EVENT_TRIGGERED_EDGE_AUTONOMY|AUTO)$",
    )
    scene: SceneSummary
    capabilities: RobotCapabilities = Field(default_factory=lambda: RobotCapabilities())
    safety_policy: SafetyPolicyReference | None = None


# ── Planning Response ────────────────────────────────────────────────────────


class PlanningResponse(BaseModel):
    request_id: str
    outcome: str
    reason: str | None = None
    contract: dict[str, Any] | None = None
    validation_errors: list[dict[str, Any]] = Field(default_factory=list)
    validation_warnings: list[dict[str, Any]] = Field(default_factory=list)
    attempt_count: int = 0
    created_at: str


# ── Dispatch ─────────────────────────────────────────────────────────────────


class DispatchRequest(BaseModel):
    pass  # No body needed for now — may add override options in future


class DispatchResponse(BaseModel):
    request_id: str
    task_id: str
    dispatched: bool
    edge_accepted: bool | None = None
    edge_reason: str | None = None
