"""Context-bound visual supervision; replies cannot replace active contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cloud_edge_robot_arm.vision.observations import RGBDObservation


class SupervisionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    episode_id: str = Field(min_length=1)
    plan_version: int = Field(ge=0)
    state_version: int = Field(ge=0)
    next_step_id: str = Field(min_length=1)
    next_skill: str = Field(min_length=1)
    observation_id: str = Field(min_length=1)
    captured_at: datetime
    proprioception: dict[str, Any]

    @model_validator(mode="after")
    def observable_only(self) -> SupervisionContext:
        allowed = {"gripper_open", "holding_object_id", "tcp_pose", "collision_detected",
                   "estop_engaged"}
        if set(self.proprioception) - allowed or self.captured_at.tzinfo is None:
            raise ValueError("supervision requires timestamped observable robot state only")
        return self


class SupervisionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    episode_id: str
    plan_version: int = Field(ge=0)
    state_version: int = Field(ge=0)
    observation_id: str
    next_step_id: str
    recommendation: Literal["CONTINUE", "REOBSERVE", "REPLAN", "STOP"]
    reason: str = Field(max_length=500)


@dataclass(frozen=True)
class SupervisionFrame:
    observation: RGBDObservation
    context: SupervisionContext


def decide_supervision(reply: SupervisionDecision, captured: SupervisionContext,
                      current: SupervisionContext, *, maximum_age_s: float) -> str:
    bindings = ("episode_id", "plan_version", "state_version", "observation_id", "next_step_id")
    if any(getattr(reply, key) != getattr(captured, key) for key in bindings):
        return "REJECT"
    if any(getattr(captured, key) != getattr(current, key) for key in (
        "episode_id", "plan_version", "state_version", "next_step_id"
    )) or not 0 <= (datetime.now(UTC) - captured.captured_at).total_seconds() <= maximum_age_s:
        return "DISCARD"
    # Replanning is a request to stop the current sequence. T13 will own safe replacement.
    return "STOP" if reply.recommendation == "REPLAN" else reply.recommendation
