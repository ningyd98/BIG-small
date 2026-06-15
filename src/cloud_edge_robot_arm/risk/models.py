from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cloud_edge_robot_arm.contracts import ControlMode


class RiskPolicy(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    version: str = Field(min_length=1)
    task_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    scene_dynamics_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    perception_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    network_weight: float = Field(default=0.15, ge=0.0, le=1.0)
    execution_weight: float = Field(default=0.2, ge=0.0, le=1.0)
    safety_weight: float = Field(default=0.2, ge=0.0, le=1.0)
    low_threshold: float = Field(default=25.0, ge=0.0, le=100.0)
    medium_threshold: float = Field(default=50.0, ge=0.0, le=100.0)
    high_threshold: float = Field(default=75.0, ge=0.0, le=100.0)
    critical_threshold: float = Field(default=90.0, ge=0.0, le=100.0)
    stale_scene_ms: int = Field(default=5_000, ge=0)
    stale_heartbeat_ms: int = Field(default=3_000, ge=0)
    missing_input_penalty: float = Field(default=80.0, ge=0.0, le=100.0)
    scene_target_moved_bonus: float = Field(default=20.0, ge=0.0, le=100.0)
    cache_miss_penalty: float = Field(default=20.0, ge=0.0, le=100.0)
    cache_no_match_penalty: float = Field(default=35.0, ge=0.0, le=100.0)


class RiskSnapshotInput(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    task_id: str = Field(min_length=1)
    task_type: str = Field(min_length=1)
    skill_name: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    scene_version: int = Field(ge=0)
    scene_updated_at: datetime | None = None
    scene_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    target_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    target_moved: bool | None = None
    target_lost: bool | None = None
    obstacle_count: int | None = Field(default=None, ge=0)
    obstacle_change_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    network_latency_ms: int | None = Field(default=None, ge=0)
    network_jitter_ms: int | None = Field(default=None, ge=0)
    packet_loss_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    disconnected_seconds: float | None = Field(default=None, ge=0.0)
    last_heartbeat_at: datetime | None = None
    execution_failures: int | None = Field(default=None, ge=0)
    timeout_count: int | None = Field(default=None, ge=0)
    replans_count: int | None = Field(default=None, ge=0)
    safety_rejections: int | None = Field(default=None, ge=0)
    estop_engaged: bool | None = None
    safety_decision: str | None = None
    current_mode: ControlMode
    has_complete_contract: bool | None = None
    remaining_steps_persisted: bool | None = None
    edge_capability_ready: bool | None = None
    cloud_available: bool | None = None
    event_autonomy_ready: bool | None = None
    supervision_available: bool | None = None
    cache_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    cache_match_type: str | None = None
    policy_version: str = Field(min_length=1)
    current_time: datetime

    @field_validator("current_time", "scene_updated_at", "last_heartbeat_at")
    @classmethod
    def datetimes_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
