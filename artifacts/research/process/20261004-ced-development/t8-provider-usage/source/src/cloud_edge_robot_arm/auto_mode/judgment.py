"""Immutable finite-choice judgments; rule scores never masquerade as probabilities."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, Protocol

from cloud_edge_robot_arm.auto_mode.candidates import CandidateSet
from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionContext
from cloud_edge_robot_arm.edge.evidence.models import DecisionEnvelope

if TYPE_CHECKING:
    from cloud_edge_robot_arm.auto_mode.joint_policy import ActionCostEstimate


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class JudgmentResult:
    selected_candidate_id: str | None
    rule_scores: Mapping[str, float]
    candidate_probabilities: Mapping[str, float] | None
    reported_confidence: float | None
    status: Literal["SELECTED", "ABSTAIN", "ERROR"]
    provider_version: str
    latency_ms: float

    def __post_init__(self) -> None:
        if self.status not in {"SELECTED", "ABSTAIN", "ERROR"}:
            raise ValueError("unsupported judgment status")
        if self.selected_candidate_id is not None and (
            not isinstance(self.selected_candidate_id, str) or not self.selected_candidate_id
        ):
            raise ValueError("selected candidate identity must be a nonempty string or None")
        if (self.status == "SELECTED") != bool(self.selected_candidate_id):
            raise ValueError("only SELECTED can identify a selected candidate")
        if (
            not isinstance(self.provider_version, str)
            or not self.provider_version
            or not _finite(self.latency_ms)
            or self.latency_ms < 0
        ):
            raise ValueError("provider identity and finite measured/reported latency are required")
        scores = dict(self.rule_scores)
        if any(
            not isinstance(key, str) or not key or not _finite(value) or value < 0
            for key, value in scores.items()
        ):
            raise ValueError("rule costs must be named finite nonnegative values")
        object.__setattr__(self, "rule_scores", MappingProxyType(scores))
        if self.candidate_probabilities is not None:
            probabilities = dict(self.candidate_probabilities)
            if (
                any(
                    not isinstance(key, str) or not key or not _finite(value) or not 0 <= value <= 1
                    for key, value in probabilities.items()
                )
                or sum(probabilities.values()) > 1 + 1e-9
            ):
                raise ValueError("candidate probabilities conflict or are outside [0,1]")
            object.__setattr__(self, "candidate_probabilities", MappingProxyType(probabilities))
        if self.reported_confidence is not None and (
            not _finite(self.reported_confidence) or not 0 <= self.reported_confidence <= 1
        ):
            raise ValueError("reported confidence must be a finite unit interval value")


@dataclass(frozen=True)
class DecisionTrace:
    envelope: DecisionEnvelope
    candidates: CandidateSet
    judgment: JudgmentResult
    estimates: Sequence[ActionCostEstimate]
    disposition: str
    reason_codes: Sequence[str]
    verification_event_ids: Sequence[str]
    cost_snapshot: Mapping[str, object] | None = None
    risk_model_hash: str = ""
    weights_hash: str = ""
    source_hashes: Mapping[str, str] | None = None
    observation_checksum: str = ""
    calibration_version: str = ""
    software_only: bool = False
    rule_cpu_ms: float | None = None
    provider_elapsed_ms: float | None = None

    def __post_init__(self) -> None:
        self.candidates.validate()
        if self.software_only and self.envelope.valid_until > self.envelope.created_at:
            raise ValueError("software trace cannot authorize future physical submission")
        if self.envelope.candidate_set_hash != self.candidates.content_hash:
            raise ValueError("trace candidate/envelope hash mismatch")
        if not self.disposition:
            raise ValueError("trace must distinguish selection and fallback disposition")
        object.__setattr__(self, "estimates", tuple(replace(row) for row in self.estimates))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "verification_event_ids", tuple(self.verification_event_ids))
        object.__setattr__(self, "cost_snapshot", _freeze(self.cost_snapshot or {}))
        object.__setattr__(self, "source_hashes", MappingProxyType(dict(self.source_hashes or {})))
        for latency in (self.rule_cpu_ms, self.provider_elapsed_ms):
            if latency is not None and (not _finite(latency) or latency < 0):
                raise ValueError("trace elapsed time must remain finite and nonnegative")


def _freeze(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {key: _freeze(item) if isinstance(item, Mapping) else item for key, item in value.items()}
    )


class DecisionJudge(Protocol):
    def choose(
        self,
        context: DecisionContext,
        candidates: CandidateSet,
        estimates: Sequence[ActionCostEstimate],
    ) -> JudgmentResult: ...


class CostDecisionJudge:
    """Deterministic minimum known cost over already legal candidates, then ID tie-break."""

    provider_version = (
        "cost-decision-rule.v1:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    )

    def __init__(self, *, context_version: str | None = None) -> None:
        if context_version is not None:
            self.provider_version = type(self).provider_version + ":" + context_version

    def choose(
        self,
        context: DecisionContext,
        candidates: CandidateSet,
        estimates: Sequence[ActionCostEstimate],
    ) -> JudgmentResult:
        from cloud_edge_robot_arm.auto_mode.joint_policy import score_actions

        started = perf_counter()
        candidates.validate()
        scores = score_actions(context, estimates)
        feasible = {
            row.candidate_id: scores[row.action]
            for row in candidates.candidates
            if row.executable and row.action in scores
        }
        if not feasible:
            return JudgmentResult(
                None,
                {},
                None,
                None,
                "ABSTAIN",
                self.provider_version,
                (perf_counter() - started) * 1000,
            )
        selected = min(feasible, key=lambda identity: (feasible[identity], identity))
        return JudgmentResult(
            selected,
            feasible,
            None,
            None,
            "SELECTED",
            self.provider_version,
            (perf_counter() - started) * 1000,
        )
