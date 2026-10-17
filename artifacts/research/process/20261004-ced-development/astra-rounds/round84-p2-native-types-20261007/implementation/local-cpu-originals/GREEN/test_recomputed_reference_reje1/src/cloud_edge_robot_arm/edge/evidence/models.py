"""Immutable online evidence and identity envelopes; no offline labels."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Literal

from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class VisualEvidence:
    observation_id: str
    calibration_version: str
    captured_at: datetime
    geometric_error_bound_m: float | None
    motion_bound_m_s: float | None
    identity_status: Literal["CONFIRMED", "UNKNOWN", "INVALID"]
    sensor_status: Literal["VALID", "UNKNOWN", "INVALID"]
    available_sensors: tuple[str, ...] = ("rgbd", "rgb", "depth")

    def __post_init__(self) -> None:
        object.__setattr__(self, "available_sensors", tuple(self.available_sensors))


@dataclass(frozen=True)
class ActionEvidenceContract:
    evidence: VisualEvidence
    expected_duration_s: float
    allowed_error_m: float
    sensor_requirements: Sequence[str]
    preconditions: Sequence[ConditionSpec]
    postconditions: Sequence[ConditionSpec]
    plan_version: int
    command_seq: int
    context_hash: str
    ordinary_ttl_s: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "sensor_requirements", tuple(self.sensor_requirements))
        for name in ("preconditions", "postconditions"):
            object.__setattr__(
                self,
                name,
                tuple(
                    replace(
                        condition,
                        tolerances=MappingProxyType(
                            {key: _freeze(value) for key, value in condition.tolerances.items()}
                        ),
                        sensor_requirements=tuple(condition.sensor_requirements),
                    )
                    for condition in getattr(self, name)
                ),
            )


@dataclass(frozen=True)
class EvidenceVerdict:
    status: Literal["VALID", "INVALID", "UNKNOWN"]
    reasons: tuple[str, ...]
    bound_at_completion_m: float | None = None

    def __post_init__(self) -> None:
        if self.status not in {"VALID", "INVALID", "UNKNOWN"}:
            raise ValueError("unsupported evidence verdict status")
        object.__setattr__(self, "reasons", tuple(self.reasons))


@dataclass(frozen=True)
class DecisionEnvelope:
    decision_id: str
    task_id: str
    episode_id: str
    observation_id: str
    plan_version: int
    command_seq: int
    mode_version: int
    context_hash: str
    candidate_set_hash: str
    action: DecisionAction
    policy_version: str
    provider_version: str
    created_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", DecisionAction(self.action))


@dataclass(frozen=True)
class CommitContext:
    task_id: str
    episode_id: str
    observation_id: str
    plan_version: int
    command_seq: int
    mode_version: int
    context_hash: str
    candidate_set_hash: str
    cancelled: bool
