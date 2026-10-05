"""Read-only runtime composition; source validation never grants method admission.

The actual INITIAL/calibration/selection verifier is not implemented. Diagnostics
use isolated software quota, while existing executors retain every safety boundary.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Literal, cast

from pydantic import BaseModel

from cloud_edge_robot_arm.auto_mode.candidates import CandidateSet, build_candidates, content_hash
from cloud_edge_robot_arm.auto_mode.joint_policy import (
    JointEvidencePolicy,
    joint_policy_source_hashes,
)
from cloud_edge_robot_arm.auto_mode.judgment import DecisionTrace
from cloud_edge_robot_arm.auto_mode.runtime_events import (
    DecisionAction,
    DecisionContext,
    DecisionEvent,
)
from cloud_edge_robot_arm.contracts import AutoModeStatus, ExecutionCheckpoint, TaskContract
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionSpec,
    ConditionStatus,
    OnlineEvidenceSnapshot,
    evaluate_conditions,
)
from cloud_edge_robot_arm.edge.evidence.models import (
    ActionEvidenceContract,
    CommitContext,
    EvidenceVerdict,
)
from cloud_edge_robot_arm.edge.evidence.validator import validate_decision_commit, validate_evidence
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudgetState
from cloud_edge_robot_arm.research.network import NetworkCostSnapshot
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.risk.calibration import estimate_risk
from cloud_edge_robot_arm.vision.risk.features import extract_risk_features
from cloud_edge_robot_arm.vision.risk.models import RiskEstimate, RiskModelArtifact


def _isolated(value: Any) -> Any:
    if isinstance(value, BaseModel):
        if set(vars(value)) - set(type(value).model_fields):
            raise ValueError("undeclared runtime model fields")
        return type(value).model_validate(_isolated(value.model_dump()))
    if isinstance(value, Mapping):
        return {key: _isolated(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return type(value)(_isolated(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return type(value)(
            **{item.name: _isolated(getattr(value, item.name)) for item in fields(value)}
        )
    return deepcopy(value)


def _aware(now: datetime) -> bool:
    return isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset() is not None


@dataclass(frozen=True)
class RuntimeCompositionSnapshot:
    """Complete owner-thread inputs; checkpoint truth maps never enter the policy."""

    active_contract: TaskContract
    checkpoint: ExecutionCheckpoint
    mode_status: AutoModeStatus
    online_evidence: OnlineEvidenceSnapshot
    verification_budget: VerificationBudgetState
    capabilities: set[DecisionAction]
    network_cost: NetworkCostSnapshot
    condition_specs: Sequence[ConditionSpec]
    action_contracts: Mapping[DecisionAction, ActionEvidenceContract]
    previous_observation: RGBDObservation | None = None
    calibration_residuals: Sequence[float] = ()
    cancelled: bool = False
    atomic_action_active: bool = False

    def __post_init__(self) -> None:
        if type(self.cancelled) is not bool or type(self.atomic_action_active) is not bool:
            raise ValueError("explicit cancellation and atomic flags required")
        for model, names in (
            (self.active_contract, ("plan_version", "command_seq")),
            (self.checkpoint, ("plan_version", "command_seq", "current_step_index")),
            (self.mode_status, ("mode_version",)),
        ):
            if any(type(getattr(model, name)) is not int for name in names):
                raise ValueError("integer current versions required")
        for name in (
            "active_contract",
            "checkpoint",
            "mode_status",
            "online_evidence",
            "verification_budget",
            "network_cost",
            "previous_observation",
        ):
            object.__setattr__(self, name, _isolated(getattr(self, name)))
        object.__setattr__(
            self, "capabilities", frozenset(DecisionAction(v) for v in self.capabilities)
        )
        object.__setattr__(self, "condition_specs", tuple(_isolated(self.condition_specs)))
        object.__setattr__(self, "calibration_residuals", tuple(self.calibration_residuals))
        object.__setattr__(
            self,
            "action_contracts",
            MappingProxyType(
                {
                    DecisionAction(key): _isolated(value)
                    for key, value in self.action_contracts.items()
                }
            ),
        )


def _check_identity(snap: RuntimeCompositionSnapshot, event: DecisionEvent, now: datetime) -> None:
    contract, checkpoint, online, mode = (
        snap.active_contract,
        snap.checkpoint,
        snap.online_evidence,
        snap.mode_status,
    )
    ids = [step.step_id for step in contract.steps]
    completed = checkpoint.completed_step_ids
    if (
        not _aware(now)
        or event.occurred_at > now
        or contract.timestamp > now
        or contract.task_id != checkpoint.task_id
        or contract.task_id != mode.task_id
        or (checkpoint.plan_version, checkpoint.command_seq)
        != (contract.plan_version, contract.command_seq)
        or (online.plan_version, online.command_seq)
        != (contract.plan_version, contract.command_seq)
        or event.observation_id != online.observation.observation_id
        or not online.observation.episode_id
        or not online.context_hash
        or event.atomic_action_active != snap.atomic_action_active
        or len(ids) != len(set(ids))
        or ids[: len(completed)] != completed
        or checkpoint.current_step_index != len(completed)
        or checkpoint.pending_step_ids != ids[len(completed) :]
        or (
            checkpoint.pending_step_ids
            and checkpoint.current_step_id != checkpoint.pending_step_ids[0]
        )
    ):
        raise ValueError("snapshot identity invalid")


def _hard_stop(snap: RuntimeCompositionSnapshot, now: datetime) -> tuple[str, ...]:
    state, budget = snap.online_evidence.robot_state, snap.verification_budget
    return tuple(
        reason
        for active, reason in (
            (snap.cancelled, "episode_cancelled"),
            (
                state.estop_engaged or state.collision_detected or not state.connected,
                "hard_robot_safety_state",
            ),
            (now >= budget.deadline_at, "absolute_verification_deadline_expired"),
            (now >= snap.active_contract.valid_until, "active_contract_expired"),
            (
                bool(budget.exhausted_reason)
                or budget.consecutive_no_progress >= budget.limits.max_no_progress,
                "verification_budget_exhausted",
            ),
        )
        if active
    )


def compose_decision_context(
    snapshot: RuntimeCompositionSnapshot,
    event: DecisionEvent,
    now: datetime,
    *,
    risk_model: RiskModelArtifact | None = None,
) -> DecisionContext:
    """Derive online features and canonical verdicts; missing calibration is UNKNOWN."""
    snap = cast(RuntimeCompositionSnapshot, _isolated(snapshot))
    _check_identity(snap, event, now)
    online = snap.online_evidence
    conditions = evaluate_conditions(snap.condition_specs, online, now=now)
    status = (
        ConditionStatus.FAIL
        if any(v.status == ConditionStatus.FAIL for v in conditions)
        else ConditionStatus.UNKNOWN
        if not conditions or any(v.status == ConditionStatus.UNKNOWN for v in conditions)
        else ConditionStatus.PASS
    )
    features = extract_risk_features(
        online.observation, snap.previous_observation, snap.calibration_residuals
    )
    unknown = RiskEstimate(None, {a.value: None for a in DecisionAction}, None, None, "UNKNOWN")
    risk = unknown
    if risk_model is not None and not _hard_stop(snap, now):
        try:
            risk = estimate_risk(_isolated(risk_model), features)
        except (ValueError, OSError, KeyError, TypeError):
            risk = unknown
    action = snap.action_contracts.get(DecisionAction.CONTINUE)
    verdict = (
        EvidenceVerdict("UNKNOWN", ("current_action_contract_missing",))
        if action is None
        else validate_evidence(
            action,
            now,
            online.context_hash,
            online.observation.calibration_version or "",
            online_evidence=online,
        )
    )
    return DecisionContext(
        snap.active_contract.task_id,
        online.observation.episode_id or "",
        snap.mode_status.current_mode,
        snap.mode_status.mode_version,
        snap.active_contract.plan_version,
        snap.active_contract.command_seq,
        replace(event, occurred_at=now, verification_status=status),
        online,
        verdict,
        conditions,
        features,
        risk,
        snap.network_cost,
        snap.capabilities,
        _isolated(snap.verification_budget),
    )


@dataclass(frozen=True)
class RuntimeCompositionResult:
    action: DecisionAction
    scope: Literal["SOFTWARE_ONLY", "NOT_ADMITTED"]
    reasons: tuple[str, ...]
    evaluated_at: datetime | None
    context: DecisionContext | None = None
    candidates: CandidateSet | None = None
    trace: DecisionTrace | None = None
    source_verdict: EvidenceVerdict = EvidenceVerdict("UNKNOWN", ("source_binding_missing",))


class RuntimeCompositionAdapter:
    """No admission flags, dispatch, mode mutations or persistent budget transaction."""

    def __init__(
        self,
        snapshot_reader: Callable[[], RuntimeCompositionSnapshot],
        *,
        policy: JointEvidencePolicy | None = None,
        source_validator: Callable[[], None] | None = None,
        risk_model: RiskModelArtifact | None = None,
        clock: Callable[[], datetime] | None = None,
        software_only: bool = False,
    ) -> None:
        if type(software_only) is not bool or (
            policy is not None and policy.software_only and not software_only
        ):
            raise ValueError("software policy requires explicit diagnostic composition")
        self.snapshot_reader, self.policy, self.source_validator = (
            snapshot_reader,
            policy,
            source_validator,
        )
        self.risk_model, self.software_only = _isolated(risk_model), software_only
        self.clock = clock or (lambda: datetime.now(UTC))
        self._events: OrderedDict[str, tuple[str, RuntimeCompositionResult]] = OrderedDict()

    def _clock(self, previous: datetime | None = None) -> datetime:
        now = self.clock()
        if not _aware(now) or (previous is not None and now < previous):
            raise ValueError("clock missing or reversed")
        return now

    def _read(self) -> RuntimeCompositionSnapshot:
        value = self.snapshot_reader()
        if not isinstance(value, RuntimeCompositionSnapshot):
            raise ValueError("owner snapshot unavailable")
        return cast(RuntimeCompositionSnapshot, _isolated(value))

    def _source(self) -> EvidenceVerdict:
        if self.source_validator is None:
            return EvidenceVerdict("UNKNOWN", ("source_binding_missing",))
        try:
            if self.source_validator() is not None:
                raise ValueError("a source flag is not binding validation")
        except Exception:
            return EvidenceVerdict("INVALID", ("source_binding_unavailable",))
        return EvidenceVerdict("VALID", ("runtime_source_callback_completed",))

    def evaluate(self, event: DecisionEvent) -> RuntimeCompositionResult:
        scope: Literal["SOFTWARE_ONLY", "NOT_ADMITTED"] = (
            "SOFTWARE_ONLY" if self.software_only else "NOT_ADMITTED"
        )
        now = None
        context = None
        candidates = None
        source = EvidenceVerdict("UNKNOWN", ("source_binding_missing",))

        def stop(*reasons: str) -> RuntimeCompositionResult:
            return RuntimeCompositionResult(
                DecisionAction.STOP, scope, tuple(reasons), now, context, candidates, None, source
            )

        try:
            now = self._clock()
            try:
                snap = self._read()
            finally:
                now = self._clock(now)
            context = compose_decision_context(snap, event, now, risk_model=self.risk_model)
            candidates = build_candidates(context, action_contracts=snap.action_contracts)
        except Exception:
            return stop("snapshot_identity_invalid")
        if hard := _hard_stop(snap, now):
            return stop(*hard)
        digest = content_hash((snap, event))

        def fresh() -> RuntimeCompositionSnapshot:
            nonlocal now
            now = self._clock(now)
            try:
                value = self._read()
            finally:
                now = self._clock(now)
            _check_identity(value, event, now)
            return value

        source = self._source()
        try:
            current = fresh()
        except Exception:
            return stop("current_snapshot_unavailable")
        if hard := _hard_stop(current, now):
            return stop(*hard)
        if source.status == "INVALID":
            return stop("source_binding_unavailable")
        if content_hash((current, event)) != digest:
            return stop("current_snapshot_changed")
        if not self.software_only:
            return stop("actual_admission_verifier_unavailable", *source.reasons)
        current_context = replace(context, event=replace(context.event, occurred_at=now))
        candidates = build_candidates(current_context, action_contracts=current.action_contracts)
        cached = self._events.get(event.event_id)
        if cached is not None:
            if cached[0] != digest:
                return stop("duplicate_event_context_changed")
            if (
                cached[1].candidates is None
                or cached[1].candidates.content_hash != candidates.content_hash
            ):
                return stop("duplicate_event_candidates_expired")
            return cast(RuntimeCompositionResult, _isolated(cached[1]))
        if self.policy is None or not self.policy.software_only:
            return stop("software_policy_unavailable")
        isolated_context = _isolated(context)
        try:
            action = DecisionAction(self.policy.decide(isolated_context))
            now = self._clock(now)
            before, after = context.verification_budget, isolated_context.verification_budget
            budget_copy = replace(
                after,
                remaining_reobservations=before.remaining_reobservations,
                remaining_retries=before.remaining_retries,
            )
            normalized = replace(isolated_context, verification_budget=budget_copy)
            if (
                content_hash(normalized) != content_hash(context)
                or (
                    before.remaining_reobservations - after.remaining_reobservations
                    not in ((0, 1) if action == DecisionAction.REOBSERVE else (0,))
                )
                or (
                    before.remaining_retries - after.remaining_retries
                    not in ((0, 1) if action == DecisionAction.REQUEST_CLOUD else (0,))
                )
            ):
                return stop("policy_mutated_bound_context")
            _isolated(isolated_context)
        except Exception:
            try:
                now = self._clock(now)
            except Exception:
                return stop("policy_clock_unavailable")
            if hard := _hard_stop(snap, now):
                return stop(*hard)
            return stop("policy_failed_or_context_invalid")
        source = self._source()
        try:
            current = fresh()
            if hard := _hard_stop(current, now):
                return stop(*hard)
            if source.status == "INVALID" or content_hash((current, event)) != digest:
                return stop("current_source_or_snapshot_changed_after_policy")
            if dict(self.policy.source_hashes) != dict(joint_policy_source_hashes()):
                return stop("policy_source_changed")
            trace = _isolated(self.policy.last_trace)
            current_context = replace(context, event=replace(context.event, occurred_at=now))
            candidates = build_candidates(
                current_context, action_contracts=current.action_contracts
            )
            observation = context.online_evidence.observation
            if (
                trace is None
                or trace.envelope.candidate_set_hash != candidates.content_hash
                or (
                    trace.envelope.policy_version != self.policy.policy_version
                    or trace.envelope.action != action
                    or trace.envelope.task_id != context.task_id
                    or trace.envelope.episode_id != context.episode_id
                    or trace.envelope.observation_id != context.event.observation_id
                    or trace.envelope.context_hash != context.online_evidence.context_hash
                    or any(
                        type(getattr(trace.envelope, name)) is not int
                        or getattr(trace.envelope, name) != getattr(context, name)
                        for name in ("plan_version", "command_seq", "mode_version")
                    )
                    or trace.envelope.provider_version != trace.judgment.provider_version
                    or trace.envelope.created_at < context.event.occurred_at
                    or trace.envelope.created_at > now
                    or trace.observation_checksum != observation.checksum_sha256
                    or trace.calibration_version != observation.calibration_version
                    or trace.risk_model_hash != self.policy.risk_model.model_hash
                    or trace.weights_hash != self.policy.weights_hash
                    or dict(trace.source_hashes or {}) != dict(self.policy.source_hashes)
                    or tuple(trace.verification_event_ids) != (event.event_id,)
                    or not trace.software_only
                    or trace.envelope.valid_until != trace.envelope.created_at
                )
            ):
                return stop("policy_trace_binding_invalid")
            selected = next(row for row in candidates.candidates if row.action == action)
            if not selected.executable and trace.disposition != "DEFERRED_ATOMIC":
                return stop("selected_candidate_unavailable")
        except Exception:
            return stop("policy_trace_unavailable")
        result = RuntimeCompositionResult(
            action, scope, tuple(trace.reason_codes), now, context, candidates, trace, source
        )
        self._events[event.event_id] = digest, _isolated(result)
        if len(self._events) > 128:
            self._events.popitem(last=False)
        return cast(RuntimeCompositionResult, _isolated(result))

    def validate_for_existing_submission(self, result: RuntimeCompositionResult) -> EvidenceVerdict:
        """Read-only revalidation, always closed until a real admission verifier exists."""
        if (
            self.software_only
            or result.scope == "SOFTWARE_ONLY"
            or (result.trace is not None and result.trace.software_only)
        ):
            return EvidenceVerdict("INVALID", ("software_diagnostic_never_submit",))
        try:
            now = self._clock()
            source = self._source()
            try:
                current = self._read()
            finally:
                now = self._clock(now)
            if hard := _hard_stop(current, now):
                return EvidenceVerdict("INVALID", hard)
            if source.status != "VALID":
                return EvidenceVerdict("UNKNOWN", source.reasons)
            if result.trace is None or result.context is None:
                return EvidenceVerdict("UNKNOWN", ("current_decision_envelope_missing",))
            ctx = compose_decision_context(
                current, result.context.event, now, risk_model=self.risk_model
            )
            candidates = build_candidates(ctx, action_contracts=current.action_contracts)
            commit = CommitContext(
                ctx.task_id,
                ctx.episode_id,
                ctx.event.observation_id,
                ctx.plan_version,
                ctx.command_seq,
                ctx.mode_version,
                ctx.online_evidence.context_hash,
                candidates.content_hash,
                current.cancelled,
            )
            verdict = validate_decision_commit(result.trace.envelope, commit, now)
            if verdict.status != "VALID":
                return verdict
            if current.atomic_action_active:
                return EvidenceVerdict("INVALID", ("ordinary_submit_deferred_atomic",))
            if result.action in {DecisionAction.CONTINUE, DecisionAction.LOCAL_RECOVER}:
                contract = current.action_contracts.get(result.action)
                if contract is None:
                    return EvidenceVerdict("UNKNOWN", ("current_action_contract_missing",))
                verdict = validate_evidence(
                    contract,
                    now,
                    ctx.online_evidence.context_hash,
                    ctx.online_evidence.observation.calibration_version or "",
                    online_evidence=ctx.online_evidence,
                )
                if verdict.status != "VALID":
                    return verdict
        except Exception:
            return EvidenceVerdict("INVALID", ("current_submit_context_unavailable",))
        return EvidenceVerdict("UNKNOWN", ("actual_admission_verifier_unavailable",))
