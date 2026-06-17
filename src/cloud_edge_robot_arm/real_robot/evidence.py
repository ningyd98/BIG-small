from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RealRobotRunEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str = Field(min_length=1)
    execution_status: str
    execution_mode: str
    validation_claimed: bool
    artifact_provenance_complete: bool
    hardware_motion_observed: bool
    config_hash: str = ""
    software_commit: str = ""
    operator_confirmation: str = ""
    robot_state_before: dict[str, Any] = Field(default_factory=dict)
    robot_state_after: dict[str, Any] = Field(default_factory=dict)
    trajectory_summary: dict[str, Any] = Field(default_factory=dict)
    safety_decision: dict[str, Any] = Field(default_factory=dict)
    stop_status: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def reject_dry_run_as_hardware_execution(self) -> RealRobotRunEvidence:
        if self.execution_status == "HARDWARE_EXECUTED" and (
            self.execution_mode == "DRY_RUN" or not self.hardware_motion_observed
        ):
            raise ValueError("dry-run evidence cannot be marked as hardware executed")
        if self.validation_claimed and not self.artifact_provenance_complete:
            raise ValueError("validation requires complete artifact provenance")
        return self


def audit_evidence_complete(payload: dict[str, Any]) -> bool:
    required = {
        "config_hash",
        "software_commit",
        "operator_confirmation",
        "robot_state_before",
        "robot_state_after",
        "trajectory_summary",
        "safety_decision",
        "stop_status",
        "result",
    }
    return required.issubset(payload.keys())
