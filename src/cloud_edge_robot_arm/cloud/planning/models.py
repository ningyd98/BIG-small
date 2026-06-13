"""Phase 4 cloud planning data models.

These models define the cloud-side contract for planning requests, scene
understanding, planner adapters, and planning outcomes.  The cloud NEVER
controls joints, motors, PWM, or low-level trajectory points directly.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from cloud_edge_robot_arm.contracts import Pose, TaskContract

# ── Scene Summary ────────────────────────────────────────────────────────────


class SceneObjectSummary(BaseModel):
    """A light-weight scene object visible to the cloud planner."""

    object_id: str = Field(min_length=1)
    object_class: str = Field(min_length=1)
    pose: Pose | None = None
    pose_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    region_id: str | None = None


class TargetRegionSummary(BaseModel):
    """A workspace region known to the cloud planner."""

    region_id: str = Field(min_length=1)
    center: Pose
    radius_m: float = Field(gt=0, default=0.08)


class SceneSummary(BaseModel):
    """Structured scene view sent from edge to cloud for planning."""

    scene_version: int = Field(ge=0)
    updated_at: datetime
    objects: list[SceneObjectSummary] = Field(default_factory=list)
    regions: list[TargetRegionSummary] = Field(default_factory=list)
    obstacles: list[dict[str, Any]] = Field(default_factory=list)
    scene_confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    robot_state: dict[str, Any] = Field(default_factory=dict)

    @field_validator("updated_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("scene updated_at must be timezone-aware")
        return v


# ── Robot Capabilities ───────────────────────────────────────────────────────


class RobotCapabilities(BaseModel):
    """Declared capabilities the edge publishes for cloud awareness."""

    supported_skills: list[str] = Field(
        min_length=1, default_factory=lambda: ["HOME"]
    )
    max_reach_m: float = Field(gt=0, default=0.65)
    max_tcp_velocity: float = Field(gt=0, default=1.0)
    max_joint_velocity: float = Field(gt=0, default=2.0)
    max_acceleration: float = Field(gt=0, default=5.0)
    grip_force_N: float = Field(gt=0, default=10.0)
    has_gripper: bool = True


class SafetyPolicyReference(BaseModel):
    """Edge safety policy metadata — cloud must respect these bounds."""

    policy_version: str = Field(min_length=1)
    policy_hash: str = Field(min_length=1)
    hard_limit_max_tcp_velocity: float = Field(gt=0)
    hard_limit_max_joint_velocity: float = Field(gt=0)
    hard_limit_max_acceleration: float = Field(gt=0)
    minimum_safe_height: float = Field(ge=0)
    obstacle_safety_distance: float = Field(ge=0)


# ── Planning Request / Response ──────────────────────────────────────────────


class PlanningOutcome(StrEnum):
    PLANNED = "PLANNED"
    REQUEST_MORE_OBSERVATION = "REQUEST_MORE_OBSERVATION"
    REJECTED = "REJECTED"
    PLANNER_FAILED = "PLANNER_FAILED"


class InitialPlanningRequest(BaseModel):
    """A validated request from the API layer to the planning pipeline."""

    request_id: str = Field(min_length=1)
    user_instruction: str = Field(min_length=1)
    control_mode: str = Field(
        default="EVENT_TRIGGERED_EDGE_AUTONOMY",
        pattern=r"^(PERIODIC_CLOUD_SUPERVISION|EVENT_TRIGGERED_EDGE_AUTONOMY|AUTO)$",
    )
    scene: SceneSummary
    capabilities: RobotCapabilities = Field(default_factory=lambda: RobotCapabilities())
    safety_policy: SafetyPolicyReference | None = None
    previous_contract: TaskContract | None = None
    # Retry/re-plan context (Phase 6)
    trigger_event: str | None = None
    trigger_event_id: str | None = None
    failed_step_id: str | None = None
    completed_step_ids: list[str] = Field(default_factory=list)
    local_retry_count: int = Field(ge=0, default=0)

    @field_validator("scene")
    @classmethod
    def _scene_freshness(cls, v: SceneSummary) -> SceneSummary:
        # freshness is checked later in the pipeline with configurable TTL
        return v


class PlannerDraft(BaseModel):
    """Raw planner output before validation and repair."""

    raw_text: str
    parsed_json: dict[str, Any] | None = None
    parse_error: str | None = None


class ValidationResult(BaseModel):
    """Result of validating planner output against schemas and semantics."""

    passed: bool = True
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class PlanningAttempt(BaseModel):
    """One invocation of a planner, including validation and repair."""

    attempt: int = Field(ge=1)
    planner_name: str
    model_name: str
    prompt_version: str
    prompt_hash: str
    temperature: float = 0.0
    max_tokens: int = 4096
    draft: PlannerDraft
    validation: ValidationResult = Field(default_factory=ValidationResult)
    repaired: bool = False
    repair_attempts: int = 0
    latency_ms: int = 0
    raw_output_hash: str = ""
    error: str | None = None


class DispatchResult(BaseModel):
    """Result of dispatching a generated contract to the edge gateway."""

    dispatched: bool
    edge_accepted: bool | None = None
    edge_reason: str | None = None
    task_id: str


class InitialPlanningResponse(BaseModel):
    """Final, structured planning response returned to the API caller."""

    request_id: str
    outcome: PlanningOutcome
    reason: str | None = None
    contract: TaskContract | None = None
    attempts: list[PlanningAttempt] = Field(default_factory=list)
    validation: ValidationResult = Field(default_factory=ValidationResult)
    dispatch: DispatchResult | None = None
    created_at: datetime
