"""Shared runtime decision vocabulary; events carry online verification only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from cloud_edge_robot_arm.edge.evidence.conditions import ConditionStatus


class DecisionAction(StrEnum):
    CONTINUE = "CONTINUE"
    REOBSERVE = "REOBSERVE"
    LOCAL_RECOVER = "LOCAL_RECOVER"
    REQUEST_CLOUD = "REQUEST_CLOUD"
    STOP = "STOP"


class DecisionEventKind(StrEnum):
    SKILL_BOUNDARY = "SKILL_BOUNDARY"
    EVIDENCE_INVALIDATED = "EVIDENCE_INVALIDATED"
    ANOMALY = "ANOMALY"
    CLOUD_RETURN = "CLOUD_RETURN"
    SUPERVISION_TICK = "SUPERVISION_TICK"
    RESULT_VERIFIED = "RESULT_VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"


@dataclass(frozen=True)
class DecisionEvent:
    event_id: str
    kind: DecisionEventKind
    occurred_at: datetime
    observation_id: str
    atomic_action_active: bool
    verification_status: ConditionStatus

    def __post_init__(self) -> None:
        if not self.event_id or not self.observation_id:
            raise ValueError("decision event requires event and observation identities")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include timezone")
        object.__setattr__(self, "kind", DecisionEventKind(self.kind))
        object.__setattr__(self, "verification_status", ConditionStatus(self.verification_status))
