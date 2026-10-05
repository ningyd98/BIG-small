"""Revalidate online evidence at cloud return and immediately before submission.

Validation has no dispatch side effects. Canonical condition verdicts are supplied
by the single online evaluate_conditions entry point; missing ones remain UNKNOWN.
Postconditions belong to subsequent effect verification, never assumed here.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import TypeGuard

from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionStatus,
    OnlineEvidenceSnapshot,
    evaluate_conditions,
)
from cloud_edge_robot_arm.edge.evidence.models import (
    ActionEvidenceContract,
    CommitContext,
    DecisionEnvelope,
    EvidenceVerdict,
)


def _number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _aware(value: object) -> TypeGuard[datetime]:
    return (
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
    )


def _base_validation(
    contract: ActionEvidenceContract,
    now: datetime,
    current_context_hash: str,
    calibration_version: str,
    online_evidence: OnlineEvidenceSnapshot | None,
) -> tuple[EvidenceVerdict | None, float | None]:
    evidence = contract.evidence
    if any(
        type(value) is not int or value < 0
        for value in (contract.plan_version, contract.command_seq)
    ):
        return EvidenceVerdict("INVALID", ("action_version_or_sequence_invalid",)), None
    if not contract.context_hash or contract.context_hash != current_context_hash:
        return EvidenceVerdict("INVALID", ("context_mismatch",)), None
    if not evidence.observation_id or not evidence.calibration_version:
        return EvidenceVerdict("UNKNOWN", ("observation_or_calibration_missing",)), None
    if evidence.calibration_version != calibration_version:
        return EvidenceVerdict("UNKNOWN", ("calibration_mismatch",)), None
    if not _aware(now) or not _aware(evidence.captured_at):
        return EvidenceVerdict("UNKNOWN", ("acquisition_clock_missing",)), None
    age = (now - evidence.captured_at).total_seconds()
    if age < 0:
        return EvidenceVerdict("INVALID", ("future_observation",)), None
    if evidence.identity_status == "INVALID" or evidence.sensor_status == "INVALID":
        return EvidenceVerdict("INVALID", ("identity_or_sensor_invalid",)), None
    if evidence.identity_status != "CONFIRMED" or evidence.sensor_status != "VALID":
        return EvidenceVerdict("UNKNOWN", ("identity_or_sensor_unknown",)), None
    if not set(contract.sensor_requirements).issubset(set(evidence.available_sensors)):
        return EvidenceVerdict("UNKNOWN", ("required_sensor_unavailable",)), None
    if (
        not _number(contract.expected_duration_s)
        or contract.expected_duration_s < 0
        or not _number(contract.allowed_error_m)
        or contract.allowed_error_m <= 0
        or not _number(contract.ordinary_ttl_s)
        or contract.ordinary_ttl_s <= 0
    ):
        return EvidenceVerdict("UNKNOWN", ("action_or_ttl_bound_missing",)), None
    if age > contract.ordinary_ttl_s:
        return EvidenceVerdict("INVALID", ("ordinary_ttl_expired",)), None
    statuses = []
    if contract.preconditions and online_evidence is None:
        return EvidenceVerdict("UNKNOWN", ("precondition_evidence_missing",)), None
    if online_evidence is not None:
        observation = online_evidence.observation
        if any(
            (
                observation.observation_id != evidence.observation_id,
                observation.captured_at != evidence.captured_at,
                observation.calibration_version != evidence.calibration_version,
                online_evidence.context_hash != contract.context_hash,
                online_evidence.plan_version != contract.plan_version,
                online_evidence.command_seq != contract.command_seq,
                type(online_evidence.plan_version) is not int,
                type(online_evidence.command_seq) is not int,
            )
        ):
            return EvidenceVerdict("INVALID", ("online_evidence_identity_mismatch",)), None
        # Recompute exact target/tolerances through the canonical evaluator.
        # A caller-supplied PASS for another target cannot authorize this action.
        statuses = [
            value.status for value in evaluate_conditions(contract.preconditions, online_evidence)
        ]
    if ConditionStatus.FAIL in statuses:
        return EvidenceVerdict("INVALID", ("precondition_failed",)), None
    if any(status != ConditionStatus.PASS for status in statuses):
        return EvidenceVerdict("UNKNOWN", ("precondition_unknown",)), None
    return None, age


def validate_evidence(
    contract: ActionEvidenceContract,
    now: datetime,
    current_context_hash: str,
    calibration_version: str,
    *,
    online_evidence: OnlineEvidenceSnapshot | None = None,
) -> EvidenceVerdict:
    base, age = _base_validation(
        contract, now, current_context_hash, calibration_version, online_evidence
    )
    if base is not None:
        return base
    evidence = contract.evidence
    error, motion = evidence.geometric_error_bound_m, evidence.motion_bound_m_s
    if not _number(error) or error < 0 or not _number(motion) or motion < 0:
        return EvidenceVerdict("UNKNOWN", ("calibrated_error_or_motion_bound_missing",))
    assert age is not None
    bound = error + motion * (age + contract.expected_duration_s)
    if not math.isfinite(bound):
        return EvidenceVerdict("UNKNOWN", ("completion_bound_nonfinite",))
    return EvidenceVerdict(
        "VALID" if bound <= contract.allowed_error_m else "INVALID",
        (
            "completion_bound_within_tolerance"
            if bound <= contract.allowed_error_m
            else "completion_bound_exceeds_tolerance",
        ),
        bound,
    )


def validate_b3(
    contract: ActionEvidenceContract,
    now: datetime,
    current_context_hash: str,
    calibration_version: str,
    *,
    online_evidence: OnlineEvidenceSnapshot | None = None,
) -> EvidenceVerdict:
    """Ablate calibrated uncertainty/completion age; retain ordinary checks and TTL."""
    base, _ = _base_validation(
        contract, now, current_context_hash, calibration_version, online_evidence
    )
    return base if base is not None else EvidenceVerdict("VALID", ("b3_base_checks_passed",))


def validate_decision_commit(
    decision: DecisionEnvelope,
    current: CommitContext,
    now: datetime,
) -> EvidenceVerdict:
    if current.cancelled:
        return EvidenceVerdict("INVALID", ("episode_cancelled",))
    for field in ("task_id", "episode_id", "observation_id", "context_hash", "candidate_set_hash"):
        value = getattr(decision, field)
        if not value or value != getattr(current, field):
            return EvidenceVerdict("INVALID", (f"{field}_mismatch_or_missing",))
    for field in ("plan_version", "command_seq", "mode_version"):
        value = getattr(decision, field)
        current_value = getattr(current, field)
        if (
            type(value) is not int
            or value < 0
            or type(current_value) is not int
            or current_value < 0
            or value != current_value
        ):
            return EvidenceVerdict("INVALID", (f"{field}_mismatch_or_invalid",))
    if not decision.decision_id or not decision.policy_version or not decision.provider_version:
        return EvidenceVerdict("INVALID", ("decision_policy_or_provider_identity_missing",))
    if not all(_aware(value) for value in (now, decision.created_at, decision.valid_until)):
        return EvidenceVerdict("INVALID", ("decision_clock_missing",))
    if decision.created_at > now or decision.valid_until <= now:
        return EvidenceVerdict("INVALID", ("decision_future_or_expired",))
    return EvidenceVerdict("VALID", ("decision_current",))
