"""Evidence records keep historical software results apart from research runs."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class EvidenceKind(StrEnum):
    SOFTWARE = "SOFTWARE"
    MOCK = "MOCK"
    PLANNING = "PLANNING"
    PHYSICS = "PHYSICS"
    HARDWARE = "HARDWARE"


class StageStatus(StrEnum):
    REAL = "REAL"
    NOT_EXECUTED = "NOT_EXECUTED"
    BLOCKED = "BLOCKED"
    MOCK = "MOCK"


class StageEvidence(BaseModel):
    stage: str
    status: StageStatus
    source_hashes: list[str] = Field(default_factory=list)
    reason: str | None = None


class RunProvenance(BaseModel):
    run_id: str
    source_tree_hash: str
    scene_group_id: str
    split_role: str
    model_snapshot_hash: str | None = None
    observation_hashes: list[str] = Field(default_factory=list)
    physics_steps: int = Field(ge=0)
    evidence_kind: EvidenceKind
    blocked_reason: str | None = None
    stages: list[StageEvidence] = Field(default_factory=list)
    # A completed task outcome is distinct from authentic runtime evidence.
    task_success: bool = False
    # Existing Phase 11/12 data is preserved, but excluded from new-run rates.
    cohort: Literal["NEW_RESEARCH", "HISTORICAL"] = "NEW_RESEARCH"
    # Online consumption of labels or simulator truth invalidates the run.
    ground_truth_exposed_online: bool = False

