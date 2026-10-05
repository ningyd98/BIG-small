"""Finite online evidence/cost decisions, with no execution or model-request transport."""

from __future__ import annotations

import copy
import json
import math
import os
import re
import tempfile
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from types import MappingProxyType
from typing import Any, Literal, TypeGuard, cast

from pydantic import BaseModel

from cloud_edge_robot_arm.auto_mode.candidates import (
    CandidateSet,
    build_candidates,
    canonical_value,
    content_hash,
)
from cloud_edge_robot_arm.auto_mode.judgment import (
    CostDecisionJudge,
    DecisionJudge,
    DecisionTrace,
    JudgmentResult,
)
from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction, DecisionContext
from cloud_edge_robot_arm.edge.evidence.models import ActionEvidenceContract, DecisionEnvelope
from cloud_edge_robot_arm.research.cost_ledger import CostLedger, CostSnapshot
from cloud_edge_robot_arm.vision.risk.models import RiskModelArtifact

_REQUIRED_WEIGHTS = frozenset(
    {"failure_loss", "stop_failure_loss", "inference_weight", "network_weight", "switch_weight"}
)


def _number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _weights(values: Mapping[str, float]) -> Mapping[str, float]:
    if set(values) != _REQUIRED_WEIGHTS or any(not _number(v) or v < 0 for v in values.values()):
        raise ValueError("weights require the five preregistered finite nonnegative costs")
    return MappingProxyType({key: float(value) for key, value in values.items()})


@dataclass(frozen=True)
class ActionCostEstimate:
    action: DecisionAction
    failure_probability: float | None
    failure_loss: float
    inference_cost: float | None
    network_cost: float | None
    switch_cost: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", DecisionAction(self.action))
        if self.failure_probability is not None and (
            not _number(self.failure_probability) or not 0 <= self.failure_probability <= 1
        ):
            raise ValueError("failure probability must be calibrated or None")
        if not _number(self.failure_loss) or self.failure_loss < 0:
            raise ValueError("failure loss must be finite and nonnegative")
        for value in (self.inference_cost, self.network_cost, self.switch_cost):
            if value is not None and (not _number(value) or value < 0):
                raise ValueError("cost components must be measured finite values or None")


def estimate_action_costs(
    context: DecisionContext, measured_costs: CostSnapshot, weights: Mapping[str, float]
) -> list[ActionCostEstimate]:
    """Use mean measured cost per sent attempt, never provider RTT as inference time.

    Timing aggregates have no per-action or per-role attribution, so this heuristic
    explicitly uses the aggregate mean for REQUEST_CLOUD. Unknown inference stays
    None, including when only round-trip timing exists. No request is sent here.
    """
    frozen = _weights(weights)
    attempts = measured_costs.model_requests
    if type(attempts) is not int or attempts < 0:
        raise ValueError("measured attempt denominator is invalid")
    for value in (measured_costs.inference_s, measured_costs.network_s, measured_costs.switch_s):
        if value is not None and (not _number(value) or value < 0):
            raise ValueError("measured cost aggregate is invalid")
    result = []
    for action in DecisionAction:
        probability = (
            context.risk_estimate.failure_probability_by_action.get(action.value)
            if context.risk_estimate.status == "VALID"
            else None
        )
        if probability is not None and (not _number(probability) or not 0 <= probability <= 1):
            probability = None
        loss = (
            frozen["stop_failure_loss"] if action == DecisionAction.STOP else frozen["failure_loss"]
        )
        if action == DecisionAction.REQUEST_CLOUD:
            inference = (
                measured_costs.inference_s / attempts * frozen["inference_weight"]
                if attempts and measured_costs.inference_s is not None
                else None
            )
            network = (
                measured_costs.network_s / attempts * frozen["network_weight"] if attempts else None
            )
            switch = (
                measured_costs.switch_s / attempts * frozen["switch_weight"] if attempts else None
            )
        else:
            # These rule actions make no model/transport/mode request themselves.
            inference = network = switch = 0.0
        if action == DecisionAction.STOP:
            # STOP pays deterministic task-failure loss, not a made-up p=1.
            probability = None
        result.append(ActionCostEstimate(action, probability, loss, inference, network, switch))
    return result


def score_actions(
    context: DecisionContext, estimates: Sequence[ActionCostEstimate]
) -> Mapping[DecisionAction, float]:
    """Compute finite expected costs; missing probability/cost remains unranked."""
    scores: dict[DecisionAction, float] = {}
    seen: set[DecisionAction] = set()
    for row in estimates:
        row = replace(row)  # Revalidate dataclass fields on external estimates.
        if row.action in seen:
            raise ValueError("duplicate action cost estimate")
        seen.add(row.action)
        if row.action == DecisionAction.STOP:
            risk_cost = row.failure_loss
        elif row.failure_probability is None:
            continue
        else:
            risk_cost = row.failure_probability * row.failure_loss
        if any(v is None for v in (row.inference_cost, row.network_cost, row.switch_cost)):
            continue
        assert (
            row.inference_cost is not None
            and row.network_cost is not None
            and row.switch_cost is not None
        )
        score = risk_cost + row.inference_cost + row.network_cost + row.switch_cost
        if math.isfinite(score):
            scores[row.action] = score
    return MappingProxyType(scores)


@dataclass(frozen=True)
class JointPolicyAdmission:
    """Future source-bound admission request, never an acceptance flag.

    T12a does not authorize an ordinary research decision from this object. A
    future source verifier must reconstruct INITIAL, calibrated provenance and
    every preregistered weight candidate, including actual selection outcomes.
    SELECTION_EXPLORATION needs INITIAL/calibration and finite candidates first,
    rather than circularly requiring its own completed selection result.
    """

    stage: Literal["SELECTION_EXPLORATION", "SELECTION_ACCEPTED"]
    initial_protocol_directory: str
    risk_artifact_hash: str
    candidate_weights: Sequence[Mapping[str, float]]
    source_hashes: Mapping[str, str]
    selection_directory: str | None = None

    def __post_init__(self) -> None:
        if self.stage not in {"SELECTION_EXPLORATION", "SELECTION_ACCEPTED"}:
            raise ValueError("unsupported joint admission stage")
        if not self.initial_protocol_directory or len(self.risk_artifact_hash) != 64:
            raise ValueError("joint admission requires INITIAL and risk artifact identity")
        if not self.candidate_weights or not self.source_hashes:
            raise ValueError("joint admission requires finite preregistered candidates and sources")
        object.__setattr__(
            self, "candidate_weights", tuple(_weights(row) for row in self.candidate_weights)
        )
        object.__setattr__(self, "source_hashes", MappingProxyType(dict(self.source_hashes)))


ContractProvider = Callable[[DecisionContext], Mapping[DecisionAction, ActionEvidenceContract]]
AdmissionProvider = Callable[[DecisionContext], JointPolicyAdmission | None]


def joint_policy_source_hashes() -> Mapping[str, str]:
    """Bind rule, candidate, risk estimator and evidence validator actual sources."""
    import hashlib

    from cloud_edge_robot_arm.edge.evidence import validator
    from cloud_edge_robot_arm.vision.risk import calibration

    base = Path(__file__).parent
    sources = {
        f"auto_mode/{name}": base / name
        for name in ("candidates.py", "judgment.py", "joint_policy.py", "runtime_events.py")
    }
    sources.update(
        {
            "edge/evidence/validator.py": Path(validator.__file__),
            "vision/risk/calibration.py": Path(calibration.__file__),
        }
    )
    return MappingProxyType(
        {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in sources.items()}
    )


def _provider_copy(value: Any) -> Any:
    """Rebuild models/dataclasses/proxies without sharing mutable descendants."""
    if isinstance(value, BaseModel):
        return value.model_copy(deep=True)
    if isinstance(value, Mapping):
        return {key: _provider_copy(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(_provider_copy(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_provider_copy(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return replace(
            value,
            **{
                field.name: _provider_copy(getattr(value, field.name))
                for field in fields(value)
                if field.init
            },
        )
    return copy.deepcopy(value)


def _provider_context(context: DecisionContext) -> DecisionContext:
    """Providers receive an isolated complete observable snapshot, never authority."""
    return cast(DecisionContext, _provider_copy(context))


def _hard_stop(context: DecisionContext, now: datetime) -> bool:
    state = context.online_evidence.robot_state
    budget = context.verification_budget
    return (
        state.estop_engaged
        or state.collision_detected
        or not state.connected
        or budget.exhausted_reason is not None
        or now >= budget.deadline_at
        or budget.consecutive_no_progress >= budget.limits.max_no_progress
        or any(
            row.measured_values.get("hard_safety_fault") is True
            for row in context.condition_verdicts
        )
    )


def _envelope_expiry(
    context: DecisionContext,
    action: DecisionAction,
    contract: ActionEvidenceContract | None,
    now: datetime,
) -> datetime:
    """Derive validity from actual evidence; no guessed TTL or physical bounds."""
    if action == DecisionAction.STOP:
        return now
    deadline = context.verification_budget.deadline_at
    if deadline.tzinfo is None or deadline <= now:
        return now
    if action == DecisionAction.REOBSERVE:
        return deadline
    if contract is None:
        return now
    evidence = contract.evidence
    if (
        evidence.captured_at.tzinfo is None
        or evidence.captured_at > now
        or not _number(contract.ordinary_ttl_s)
        or contract.ordinary_ttl_s <= 0
    ):
        return now
    age = (now - evidence.captured_at).total_seconds()
    horizon = min((deadline - now).total_seconds(), contract.ordinary_ttl_s - age)
    if horizon <= 0:
        return now
    expiry = now + timedelta(seconds=horizon)
    if action == DecisionAction.REQUEST_CLOUD:
        return expiry if expiry > now else now
    error, motion = evidence.geometric_error_bound_m, evidence.motion_bound_m_s
    if (
        not _number(error)
        or error < 0
        or not _number(motion)
        or motion < 0
        or not _number(contract.allowed_error_m)
        or contract.allowed_error_m <= 0
        or not _number(contract.expected_duration_s)
        or contract.expected_duration_s < 0
    ):
        return now
    available = contract.allowed_error_m - error - motion * contract.expected_duration_s
    if not math.isfinite(available) or available < 0:
        return now
    if motion > 0:
        horizon = min(horizon, available / motion - age)
        if horizon <= 0:
            return now
        expiry = now + timedelta(seconds=horizon)
    return expiry if expiry > now else now


class JsonDecisionTraceSink:
    """Atomically archive an immutable hashed decision; conflicting IDs never overwrite."""

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    def __call__(self, trace: DecisionTrace) -> None:
        identity = trace.envelope.decision_id
        if re.fullmatch(r"decision-[0-9a-f]{32}", identity) is None:
            raise ValueError("unsafe decision trace identity")
        payload = canonical_value(trace)
        record = {
            "schema_version": "ced.decision-trace.v1",
            "content_hash": content_hash(payload),
            "payload": payload,
        }
        encoded = json.dumps(
            record, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / f"{identity}.json"
        with tempfile.NamedTemporaryFile(
            dir=self.directory, prefix=".decision-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            try:
                # Atomic install without replacement, including concurrent writers.
                os.link(temporary, target)
            except FileExistsError:
                if target.read_bytes() != encoded:
                    raise ValueError("conflicting immutable decision trace") from None
            directory_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)


class JointEvidencePolicy:
    """T12a SOFTWARE_ONLY math with actual adaptive admission explicitly closed.

    This object produces audit decisions only. Hardware dispatch and commit must
    remain in the existing executor. Rule/provider latency is recorded separately;
    arbitrary synchronous injected providers cannot be forcibly interrupted.
    """

    def __init__(
        self,
        risk_model: RiskModelArtifact,
        weights: Mapping[str, float],
        cost_ledger: CostLedger,
        judge: DecisionJudge | None = None,
        *,
        contract_provider: ContractProvider | None = None,
        software_only: bool = False,
        clock: Callable[[], datetime] | None = None,
        admission_provider: AdmissionProvider | None = None,
        trace_sink: Callable[[DecisionTrace], None] | None = None,
        judge_timeout_s: float = 1.0,
    ) -> None:
        if type(software_only) is not bool or not _number(judge_timeout_s) or judge_timeout_s <= 0:
            raise ValueError("explicit software mode and finite judgment timeout are required")
        self.risk_model = replace(
            risk_model, feature_schema=MappingProxyType(dict(risk_model.feature_schema))
        )
        self.weights = _weights(weights)
        self.cost_ledger = cost_ledger
        self.contract_provider = contract_provider
        self.software_only = software_only
        self.clock = clock or (lambda: datetime.now(UTC))
        self.admission_provider = admission_provider
        self.trace_sink = trace_sink
        self.judge_timeout_s = float(judge_timeout_s)
        self.source_hashes = joint_policy_source_hashes()
        self.weights_hash = content_hash(self.weights)
        self.policy_version = "joint-evidence.v1:" + content_hash(
            {
                "weights": self.weights_hash,
                "risk": self.risk_model.model_hash,
                "sources": self.source_hashes,
                "software_only": software_only,
            }
        )
        self.judge = (
            judge if judge is not None else CostDecisionJudge(context_version=self.policy_version)
        )
        self._traces: list[DecisionTrace] = []
        self._events: OrderedDict[str, tuple[str, DecisionTrace]] = OrderedDict()
        self.last_trace: DecisionTrace | None = None

    @property
    def traces(self) -> tuple[DecisionTrace, ...]:
        """Immutable audit records; durable storage can be supplied as trace_sink."""
        return tuple(self._traces)

    def _clock_after(self, previous: datetime, boundary: str) -> datetime:
        """Recheck observable time after callbacks, including exceptional returns."""
        current = self.clock()
        if current.tzinfo is None or current.utcoffset() is None or current < previous:
            raise ValueError(f"{boundary} clock is missing or reversed")
        return current

    def _save(
        self,
        context: DecisionContext,
        candidates: CandidateSet,
        estimates: Sequence[ActionCostEstimate],
        costs: CostSnapshot,
        judgment: JudgmentResult,
        action: DecisionAction,
        disposition: str,
        reasons: Sequence[str],
        now: datetime,
        *,
        rule_ms: float | None = None,
        provider_ms: float | None = None,
    ) -> DecisionAction:
        selected = next(row for row in candidates.candidates if row.action == action)
        expiry = _envelope_expiry(context, action, selected.evidence_contract, now)
        if self.software_only or disposition in {"DEFERRED_ATOMIC", "HARD_STOP", "NOT_ADMITTED"}:
            expiry = now
        envelope = DecisionEnvelope(
            "decision-"
            + content_hash(
                {
                    "event": context.event.event_id,
                    "candidates": candidates.content_hash,
                    "policy": self.policy_version,
                    "action": action,
                    "created_at": now,
                }
            )[:32],
            context.task_id,
            context.episode_id,
            context.event.observation_id,
            context.plan_version,
            context.command_seq,
            context.mode_version,
            context.online_evidence.context_hash,
            candidates.content_hash,
            action,
            self.policy_version,
            judgment.provider_version,
            now,
            expiry,
        )
        trace = DecisionTrace(
            envelope,
            candidates,
            judgment,
            estimates,
            disposition,
            tuple(reasons),
            (context.event.event_id,),
            costs.model_dump(),
            self.risk_model.model_hash,
            self.weights_hash,
            self.source_hashes,
            context.online_evidence.observation.checksum_sha256,
            context.online_evidence.observation.calibration_version or "",
            self.software_only,
            rule_ms,
            provider_ms,
        )
        # A failed publication never consumes an allowance. The actual durable
        # execution/budget transaction remains outside this SOFTWARE_ONLY policy.
        reservation: str | None = None
        if action == DecisionAction.REOBSERVE:
            reservation = "remaining_reobservations"
        elif action == DecisionAction.REQUEST_CLOUD and (
            any(row.status.value == "FAIL" for row in context.condition_verdicts)
            or context.event.verification_status.value == "FAIL"
            or context.evidence_verdict.status == "INVALID"
        ):
            reservation = "remaining_retries"
        budget = context.verification_budget
        if reservation is not None and getattr(budget, reservation) <= 0:
            raise RuntimeError("verification allowance changed before audit publication")
        if self.trace_sink is not None:
            self.trace_sink(trace)
        acknowledged_at = self._clock_after(now, "audit acknowledgement")
        if action != DecisionAction.STOP and _hard_stop(context, acknowledged_at):
            # The sink may have archived an intent, but no ordinary choice,
            # cache entry or allowance reservation is published after expiry.
            raise RuntimeError(
                "verification deadline or budget changed before audit acknowledgement"
            )
        if reservation is not None:
            if getattr(budget, reservation) <= 0:
                raise RuntimeError("verification budget changed before reservation commit")
            setattr(budget, reservation, getattr(budget, reservation) - 1)
        self._traces.append(trace)
        self.last_trace = trace
        return action

    def _fallback(
        self,
        context: DecisionContext,
        candidates: CandidateSet,
        estimates: Sequence[ActionCostEstimate],
        costs: CostSnapshot,
        judgment: JudgmentResult,
        reasons: Sequence[str],
        now: datetime,
        *,
        rule_ms: float | None = None,
        provider_ms: float | None = None,
    ) -> DecisionAction:
        available = next(
            row for row in candidates.candidates if row.action == DecisionAction.REOBSERVE
        )
        if _hard_stop(context, now):
            return self._save(
                context,
                candidates,
                estimates,
                costs,
                judgment,
                DecisionAction.STOP,
                "FALLBACK_STOP",
                (*reasons, "hard_stop_or_budget_exhausted"),
                now,
                rule_ms=rule_ms,
                provider_ms=provider_ms,
            )
        if available.executable and context.verification_budget.remaining_reobservations > 0:
            action, disposition = DecisionAction.REOBSERVE, "FALLBACK_REOBSERVE"
            reasons = (*reasons, "requires_new_capture")
        else:
            action, disposition = DecisionAction.STOP, "FALLBACK_STOP"
            reasons = (*reasons, "reobservation_unavailable")
        return self._save(
            context,
            candidates,
            estimates,
            costs,
            judgment,
            action,
            disposition,
            reasons,
            now,
            rule_ms=rule_ms,
            provider_ms=provider_ms,
        )

    def decide(self, context: DecisionContext) -> DecisionAction:
        """Read the live T8 ledger, filter, judge, validate and audit; never dispatch."""
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("decision clock must be timezone-aware")
        costs = self.cost_ledger.snapshot()
        reasons: tuple[str, ...]
        current = replace(context, event=replace(context.event, occurred_at=now))
        empty = JudgmentResult(
            None, {}, None, None, "ABSTAIN", CostDecisionJudge.provider_version, 0.0
        )
        # No contract/model/judge provider precedes these unconditional stops.
        if _hard_stop(context, now) or not self.software_only or context.event.atomic_action_active:
            candidates = build_candidates(current)
            if _hard_stop(context, now):
                action, disposition, reasons = (
                    DecisionAction.STOP,
                    "HARD_STOP",
                    ("hard_stop_or_budget_exhausted",),
                )
            elif not self.software_only:
                action, disposition, reasons = (
                    DecisionAction.STOP,
                    "NOT_ADMITTED",
                    ("adaptive_not_accepted", "actual_admission_verifier_unavailable"),
                )
            else:
                action, disposition, reasons = (
                    DecisionAction.CONTINUE,
                    "DEFERRED_ATOMIC",
                    ("await_atomic_boundary", "no_new_physical_authority"),
                )
            return self._save(
                context, candidates, (), costs, empty, action, disposition, reasons, now
            )
        contracts: Mapping[DecisionAction, ActionEvidenceContract] = MappingProxyType({})
        contract_error = None
        if self.contract_provider is not None:
            try:
                contracts = MappingProxyType(
                    {
                        DecisionAction(key): cast(ActionEvidenceContract, _provider_copy(value))
                        for key, value in self.contract_provider(_provider_context(context)).items()
                    }
                )
            except Exception as exc:
                contract_error = f"contract_provider_error:{type(exc).__name__}"
            now = self._clock_after(now, "contract provider return")
            current = replace(context, event=replace(context.event, occurred_at=now))
            if _hard_stop(context, now):
                return self._save(
                    context,
                    build_candidates(current, action_contracts=contracts),
                    (),
                    costs,
                    empty,
                    DecisionAction.STOP,
                    "HARD_STOP",
                    tuple(reason for reason in (
                        contract_error, "hard_stop_or_budget_exhausted_after_contract_return"
                    ) if reason is not None),
                    now,
                )
        candidates = build_candidates(current, action_contracts=contracts)
        estimates = tuple(estimate_action_costs(context, costs, self.weights))
        key = content_hash(
            {
                "task": context.task_id,
                "episode": context.episode_id,
                "mode": context.mode,
                "mode_version": context.mode_version,
                "plan": context.plan_version,
                "command": context.command_seq,
                "event": context.event,
                "online_evidence": context.online_evidence,
                "contracts": contracts,
                "contract_error": contract_error,
                "evidence": context.evidence_verdict,
                "risk_estimate": context.risk_estimate,
                "risk_features": context.risk_features,
                "network": context.network_cost,
                "conditions": context.condition_verdicts,
                "costs": costs.model_dump(),
                "deadline": context.verification_budget.deadline_at,
                "capabilities": context.capabilities,
                "budget_limits": context.verification_budget.limits,
            }
        )
        old = self._events.get(context.event.event_id)
        if old is not None:
            if old[0] == key:
                action = old[1].envelope.action
                # Reserved capture/retry allowance is not charged twice. Current
                # TTL/bounds must still permit a previously chosen ordinary action.
                from cloud_edge_robot_arm.auto_mode.candidates import fresh_cloud_input

                current_choice = next(row for row in candidates.candidates if row.action == action)
                still_valid = (
                    current_choice.executable
                    if action == DecisionAction.CONTINUE
                    else fresh_cloud_input(context, contracts, now)
                    if action == DecisionAction.REQUEST_CLOUD
                    else True
                )
                if still_valid:
                    self.last_trace = old[1]
                    return action
            action = self._save(
                context,
                candidates,
                estimates,
                costs,
                empty,
                DecisionAction.STOP,
                "DUPLICATE_CHANGED",
                ("duplicate_event_inputs_changed_or_expired",),
                now,
            )
        elif contract_error is not None or not any(
            row.executable and row.action in {DecisionAction.CONTINUE, DecisionAction.REQUEST_CLOUD}
            for row in candidates.candidates
        ):
            action = self._fallback(
                context,
                candidates,
                estimates,
                costs,
                empty,
                (contract_error or "current_evidence_requires_new_observation",),
                now,
            )
        else:
            provider_candidates = cast(CandidateSet, _provider_copy(candidates))
            provider_estimates = tuple(replace(row) for row in estimates)
            estimate_hash = content_hash(provider_estimates)
            judge_started = perf_counter()
            result = empty
            failure: str | None = None
            try:
                proposed = self.judge.choose(
                    _provider_context(context), provider_candidates, provider_estimates
                )
                if not isinstance(proposed, JudgmentResult):
                    raise ValueError("malformed judgment result")
                result = replace(proposed)
                provider_candidates.validate()  # Recheck isolated provider input after return.
                candidates.validate()
                if content_hash(provider_estimates) != estimate_hash:
                    raise ValueError("action cost estimates changed during provider call")
            except Exception as exc:
                result = JudgmentResult(
                    None,
                    {},
                    None,
                    None,
                    "ERROR",
                    result.provider_version
                    if result is not empty
                    else str(
                        getattr(self.judge, "provider_version", type(self.judge).__qualname__)
                    ),
                    (perf_counter() - judge_started) * 1000,
                )
                failure = f"judge_failure:{type(exc).__name__}"
            elapsed = (perf_counter() - judge_started) * 1000
            finished = self._clock_after(now, "judgment")
            if (
                elapsed > self.judge_timeout_s * 1000
                or finished >= context.verification_budget.deadline_at
            ):
                result = JudgmentResult(
                    None, {}, None, None, "ERROR", result.provider_version, elapsed
                )
                failure = "judge_failure:TimeoutError"
            refreshed = build_candidates(
                replace(context, event=replace(context.event, occurred_at=finished)),
                action_contracts=contracts,
            )
            selected = next(
                (
                    row
                    for row in refreshed.candidates
                    if row.candidate_id == result.selected_candidate_id
                ),
                None,
            )
            identities = {row.candidate_id for row in refreshed.candidates}
            if failure is None:
                if result.status != "SELECTED" or selected is None or not selected.executable:
                    failure = f"judge_{result.status.lower()}_or_out_of_set"
                elif (
                    set(result.rule_scores) - identities
                    or set(result.candidate_probabilities or {}) - identities
                ):
                    failure = "judge_payload_out_of_set"
                elif refreshed.content_hash != candidates.content_hash:
                    failure = "evidence_changed_or_expired_during_judgment"
            is_rule = type(self.judge) is CostDecisionJudge
            rule_ms, provider_ms = (elapsed, None) if is_rule else (None, elapsed)
            # Audit errors are deliberately outside the provider exception block;
            # a failed durable sink cannot cause a hidden fallback or double charge.
            if failure is not None:
                action = self._fallback(
                    context,
                    refreshed,
                    estimates,
                    costs,
                    result,
                    (failure,),
                    finished,
                    rule_ms=rule_ms,
                    provider_ms=provider_ms,
                )
            else:
                assert selected is not None
                action = selected.action
                reasons = ("software_only_math_fixture",)
                if action == DecisionAction.REOBSERVE:
                    reasons += ("requires_new_capture",)
                action = self._save(
                    context,
                    refreshed,
                    estimates,
                    costs,
                    result,
                    action,
                    "SOFTWARE_ONLY_SELECTED",
                    reasons,
                    finished,
                    rule_ms=rule_ms,
                    provider_ms=provider_ms,
                )
        assert self.last_trace is not None
        self._events[context.event.event_id] = (key, self.last_trace)
        if len(self._events) > 128:
            self._events.popitem(last=False)
        return action
