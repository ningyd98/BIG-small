"""Durable verified recovery contracts; authorization and ACK are not resolution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from datetime import UTC, datetime
from math import isfinite
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
from cloud_edge_robot_arm.contracts.models import (
    ActiveTaskContractRecord,
    EdgeEvent,
    ExecutionCheckpoint,
    RecoveryBudget,
    ReplanExecutionReceipt,
    RobotState,
    SkillExecutionResult,
    replan_payload_hash,
)
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionSpec,
    ConditionVerdict,
    OnlineEvidenceSnapshot,
    evaluate_conditions,
)
from cloud_edge_robot_arm.edge.evidence.models import (
    ActionEvidenceContract,
    CommitContext,
    DecisionEnvelope,
)
from cloud_edge_robot_arm.edge.evidence.validator import validate_decision_commit, validate_evidence
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)

if TYPE_CHECKING:
    from cloud_edge_robot_arm.repositories.event_autonomy.protocol import EventAutonomyRepository


def _utc_clock() -> datetime:
    return datetime.now(UTC)


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _identity(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty identity required")


def _aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware source clock required")


def _state_payload(state: VerificationBudgetState) -> dict[str, Any]:
    state.__post_init__()
    if any(
        not isinstance(name, str) or status not in {"UNKNOWN", "FAIL", "PASS"}
        for name, (status, _) in state.previous_conditions.items()
    ):
        raise ValueError("invalid verified progress state")
    return {**asdict(state), "deadline_at": state.deadline_at.isoformat()}


def _state_from_payload(payload: dict[str, Any]) -> VerificationBudgetState:
    values = dict(payload)
    values["deadline_at"] = datetime.fromisoformat(values["deadline_at"])
    values["limits"] = VerificationBudget(**values["limits"])
    values["previous_conditions"] = {
        name: tuple(value) for name, value in values["previous_conditions"].items()
    }
    state = VerificationBudgetState(**values)
    _state_payload(state)
    return state


def copy_budget(state: VerificationBudgetState) -> VerificationBudgetState:
    return _state_from_payload(json.loads(json.dumps(_state_payload(state), allow_nan=False)))


@dataclass(frozen=True)
class VerificationBudgetRecord:
    task_id: str
    state: VerificationBudgetState
    revision: int
    created_at: datetime
    updated_at: datetime
    content_hash: str = ""

    def __post_init__(self) -> None:
        _identity(self.task_id)
        _aware(self.created_at)
        _aware(self.updated_at)
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError("invalid verification budget revision")
        object.__setattr__(self, "state", copy_budget(self.state))
        digest = _hash(self.to_payload(include_hash=False))
        if self.content_hash and self.content_hash != digest:
            raise ValueError("verification budget content hash mismatch")
        object.__setattr__(self, "content_hash", digest)

    def to_payload(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload = {
            "schema_version": "recovery.verification-budget.v1",
            "task_id": self.task_id,
            "state": _state_payload(self.state),
            "revision": self.revision,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
        if include_hash:
            payload["content_hash"] = self.content_hash
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> VerificationBudgetRecord:
        values = dict(payload)
        if values.pop("schema_version") != "recovery.verification-budget.v1":
            raise ValueError("unknown verification budget schema")
        values["state"] = _state_from_payload(values["state"])
        for name in ("created_at", "updated_at"):
            values[name] = datetime.fromisoformat(values[name])
        return cls(**values)

    @classmethod
    def create(cls, task_id: str, state: VerificationBudgetState) -> VerificationBudgetRecord:
        now = datetime.now(UTC)
        return cls(task_id, state, 0, now, now)

    def detached(self) -> VerificationBudgetRecord:
        return type(self).from_payload(self.to_payload())


# Keep the ten roadmap fields positional; binding/CAS metadata is keyword-only.
@dataclass(frozen=True)
class RecoveryRecord:
    recovery_id: str
    event_id: str
    task_id: str
    attempt_id: str
    state: str
    budget_state: VerificationBudgetState
    progress_signature: str
    last_verified_at: datetime | None
    resolution_observation_id: str
    reason: str
    revision: int = field(default=0, kw_only=True)
    task_budget_revision: int = field(default=0, kw_only=True)
    failure_plan_version: int | None = field(default=None, kw_only=True)
    failure_command_seq: int | None = field(default=None, kw_only=True)
    plan_version: int | None = field(default=None, kw_only=True)
    command_seq: int | None = field(default=None, kw_only=True)
    episode_id: str = field(default="", kw_only=True)
    step_id: str = field(default="", kw_only=True)
    skill: str = field(default="", kw_only=True)
    payload_hash: str = field(default="", kw_only=True)
    checkpoint_hash: str = field(default="", kw_only=True)
    conditions: tuple[ConditionSpec, ...] = field(default=(), kw_only=True)
    execution_receipt: ReplanExecutionReceipt | None = field(default=None, kw_only=True)
    executed_at: datetime | None = field(default=None, kw_only=True)
    execution_completion: SkillExecutionResult | None = field(default=None, kw_only=True)
    executed_checkpoint_hash: str = field(default="", kw_only=True)
    reobservation_reserved: bool = field(default=False, kw_only=True)
    last_observation_id: str = field(default="", kw_only=True)
    last_observation_captured_at: datetime | None = field(default=None, kw_only=True)
    last_verification_hash: str = field(default="", kw_only=True)
    authorization_hash: str = field(default="", kw_only=True)
    evidence_scope: str = field(default="UNAVAILABLE", kw_only=True)
    authorized_at: datetime | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        for value in (self.recovery_id, self.event_id, self.task_id, self.attempt_id):
            _identity(value)
        if self.evidence_scope not in {"UNAVAILABLE", "SOFTWARE_ONLY", "ACTUAL_SOURCE"}:
            raise ValueError("unsupported recovery evidence scope")
        if self.state not in RECOVERY_STATES:
            raise ValueError("unsupported recovery state")
        for name in (
            "revision",
            "task_budget_revision",
            "failure_plan_version",
            "failure_command_seq",
            "plan_version",
            "command_seq",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("invalid recovery version or revision")
        for timestamp in (
            self.authorized_at,
            self.last_verified_at,
            self.executed_at,
            self.last_observation_captured_at,
        ):
            if timestamp is not None:
                _aware(timestamp)
        object.__setattr__(self, "budget_state", copy_budget(self.budget_state))
        object.__setattr__(
            self,
            "conditions",
            tuple(
                ConditionSpec(
                    item.name,
                    item.target_id,
                    _freeze_data(item.tolerances),
                    tuple(item.sensor_requirements),
                )
                for item in self.conditions
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        payload = {item.name: getattr(self, item.name) for item in fields(self)}
        payload["schema_version"] = "recovery.record.v1"
        payload["budget_state"] = _state_payload(self.budget_state)
        payload["conditions"] = [_condition_payload(item) for item in self.conditions]
        payload["execution_completion"] = (
            self.execution_completion.model_dump(mode="json") if self.execution_completion else None
        )
        payload["execution_receipt"] = (
            self.execution_receipt.model_dump(mode="json") if self.execution_receipt else None
        )
        for name in (
            "authorized_at",
            "last_verified_at",
            "executed_at",
            "last_observation_captured_at",
        ):
            value = getattr(self, name)
            payload[name] = value.isoformat() if value else None
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RecoveryRecord:
        values = dict(payload)
        if values.pop("schema_version") != "recovery.record.v1":
            raise ValueError("unknown recovery record schema")
        values["budget_state"] = _state_from_payload(values["budget_state"])
        values["conditions"] = tuple(ConditionSpec(**item) for item in values["conditions"])
        if values["execution_completion"] is not None:
            values["execution_completion"] = SkillExecutionResult.model_validate_json(
                json.dumps(values["execution_completion"])
            )
        if values["execution_receipt"] is not None:
            values["execution_receipt"] = ReplanExecutionReceipt.model_validate_json(
                json.dumps(values["execution_receipt"])
            )
        for name in (
            "authorized_at",
            "last_verified_at",
            "executed_at",
            "last_observation_captured_at",
        ):
            if values[name] is not None:
                values[name] = datetime.fromisoformat(values[name])
        return cls(**values)

    def detached(self) -> RecoveryRecord:
        return type(self).from_payload(self.to_payload())

    def content_hash(self) -> str:
        return _hash(self.to_payload())

    def bindings_hash(self) -> str:
        names = (
            "recovery_id",
            "event_id",
            "task_id",
            "attempt_id",
            "failure_plan_version",
            "failure_command_seq",
            "plan_version",
            "command_seq",
            "episode_id",
            "step_id",
            "skill",
            "payload_hash",
            "checkpoint_hash",
            "conditions",
        )
        payload = self.to_payload()
        return _hash({name: payload[name] for name in names})


RECOVERY_STATES = frozenset(
    {
        "DETECTED",
        "RECOVERY_AUTHORIZED",
        "RETRY_EXECUTED",
        "VERIFIED_RESOLVED",
        "EXHAUSTED",
        "UNRECOVERABLE",
    }
)


def _condition_payload(condition: ConditionSpec) -> dict[str, Any]:
    return {
        "name": condition.name,
        "target_id": condition.target_id,
        "tolerances": _plain_data(condition.tolerances),
        "sensor_requirements": list(condition.sensor_requirements),
    }


def validate_detected(
    record: RecoveryRecord, event: EdgeEvent | None, pool: VerificationBudgetRecord | None
) -> None:
    if (
        record.state != "DETECTED"
        or record.revision != 0
        or record.execution_receipt is not None
        or record.executed_at is not None
        or record.last_verified_at is not None
        or record.resolution_observation_id
        or record.authorization_hash
        or record.execution_completion is not None
        or record.executed_checkpoint_hash
        or record.reobservation_reserved
        or record.last_observation_id
        or record.last_verification_hash
        or record.progress_signature
        or record.authorized_at
        or record.evidence_scope != "UNAVAILABLE"
    ):
        raise ValueError("public initialization cannot assert recovery effects")
    if (
        event is None
        or event.task_id != record.task_id
        or record.failure_plan_version != event.plan_version
        or record.failure_command_seq != event.command_seq
    ):
        raise ValueError("recovery failure event identity mismatch")
    if (
        pool is None
        or pool.task_id != record.task_id
        or pool.state != record.budget_state
        or pool.revision != record.task_budget_revision
    ):
        raise ValueError("recovery must use the existing complete task verification pool")


def _freeze_data(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_data(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_data(item) for item in value)
    return deepcopy(value)


@dataclass(frozen=True)
class RecoveryAuthorizationEvidence:
    """Frozen canonical inputs supplied by the actual source provider.

    v1 binds candidate_set_hash to the whole current contract and context_hash
    to the checkpoint; a future T12 adapter must explicitly map its distinct
    candidate/choice/context identities rather than replacing those hashes.
    """

    recovery_id: str
    decision: DecisionEnvelope
    current: CommitContext
    action: ActionEvidenceContract
    online_evidence: OnlineEvidenceSnapshot
    evidence_scope: str = field(default="UNAVAILABLE", kw_only=True)

    def __post_init__(self) -> None:
        _identity(self.recovery_id)
        if not isinstance(self.online_evidence, OnlineEvidenceSnapshot):
            raise ValueError("actual online snapshot required")
        observation = type(self.online_evidence.observation).model_validate(
            self.online_evidence.observation.model_dump()
        )
        object.__setattr__(
            self,
            "online_evidence",
            replace(
                self.online_evidence,
                observation=observation,
                robot_state=self.online_evidence.robot_state.model_copy(deep=True),
                visual_facts=_freeze_data(self.online_evidence.visual_facts),
            ),
        )

    def digest(self) -> str:
        return _hash(
            {
                "recovery_id": self.recovery_id,
                "evidence_scope": self.evidence_scope,
                "decision": _plain_data(self.decision),
                "current": _plain_data(self.current),
                "action": _plain_data(self.action),
                "online": {
                    "observation": self.online_evidence.observation.model_dump(mode="json"),
                    "robot": self.online_evidence.robot_state.model_dump(mode="json"),
                    "facts": _plain_data(self.online_evidence.visual_facts),
                    "plan_version": self.online_evidence.plan_version,
                    "command_seq": self.online_evidence.command_seq,
                    "context_hash": self.online_evidence.context_hash,
                },
            }
        )


def _plain_data(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain_data(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_data(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {item.name: _plain_data(getattr(value, item.name)) for item in fields(value)}
    return value


@dataclass(frozen=True)
class RecoveryAuthorizationResult:
    authorized: bool
    recovery: RecoveryRecord | None
    retry_budget: RecoveryBudget | None
    verification_budget: VerificationBudgetRecord | None
    reasons: tuple[str, ...]


def authorization_reasons(
    record: RecoveryRecord,
    pool: VerificationBudgetRecord | None,
    budget: RecoveryBudget | None,
    event: EdgeEvent | None,
    active: ActiveTaskContractRecord | None,
    checkpoint: ExecutionCheckpoint | None,
    cancelled: bool,
    proof: RecoveryAuthorizationEvidence,
    step_id: str,
    skill: str,
    now: datetime,
) -> tuple[str, ...]:
    if not isinstance(proof, RecoveryAuthorizationEvidence):
        return ("typed_authorization_source_unavailable",)
    if proof.evidence_scope != "SOFTWARE_ONLY":
        # Existing TaskStep list[str] has no certified target/tolerance binding.
        # A source flag alone cannot invent the absent physical admission proof.
        return ("actual_frozen_recovery_requirement_binding_unavailable",)
    if not _safe_robot(proof.online_evidence.robot_state):
        return ("actual_robot_hard_stop",)
    if (
        pool is None
        or budget is None
        or active is None
        or checkpoint is None
        or event is None
        or record.state != "DETECTED"
        or cancelled
    ):
        return ("authorization_source_or_state_unavailable",)
    if (
        now >= pool.state.deadline_at
        or pool.state.exhausted_reason
        or (budget.retry_deadline is not None and now >= budget.retry_deadline)
        or pool.state.remaining_retries <= 0
        or budget.task_retry_count >= pool.state.limits.max_retries
    ):
        return ("authorization_budget_or_deadline_exhausted",)
    if (
        event.task_id != record.task_id
        or event.plan_version != record.failure_plan_version
        or event.command_seq != record.failure_command_seq
        or proof.recovery_id != record.recovery_id
        or active.plan_version != record.plan_version
        or active.command_seq != record.command_seq
        or active.contract_hash != record.payload_hash
        or replan_payload_hash(active.contract) != record.payload_hash
        or checkpoint.plan_version != record.plan_version
        or checkpoint.command_seq != record.command_seq
        or checkpoint_digest(checkpoint) != record.checkpoint_hash
        or step_id != record.step_id
        or skill != record.skill
        or not record.episode_id
        or not record.conditions
    ):
        return ("authorization_current_identity_mismatch",)
    for condition in record.conditions:
        expected_target = (
            active.contract.task_target.target_region_id
            if condition.name == "tcp_above_region"
            else active.contract.task_target.object_id
        )
        if condition.target_id != expected_target:
            return ("condition_target_not_bound_to_current_contract",)
    step = next((item for item in active.contract.steps if item.step_id == step_id), None)
    if step is not None:
        required = set(step.success_conditions)
        supplied = {item.name for item in record.conditions}
        if (required and supplied != required) or (
            skill == "GRASP" and "object_held" not in supplied
        ):
            return ("frozen_recovery_conditions_missing_or_weakened",)
    if (
        step is None
        or step.skill.value != skill
        or budget.step_retry_counts.get(step_id, 0) >= step.retry_limit
        or budget.skill_retry_counts.get(skill, 0)
        >= active.contract.failure_policy.local_retry_limit
    ):
        return ("frozen_step_retry_limit_exhausted",)
    if (
        proof.current.plan_version != record.plan_version
        or proof.current.command_seq != record.command_seq
        or proof.current.task_id != record.task_id
        or proof.current.episode_id != record.episode_id
        or proof.current.context_hash != record.checkpoint_hash
        or proof.current.candidate_set_hash != record.payload_hash
        or proof.current.cancelled
        or proof.action.plan_version != record.plan_version
        or proof.action.command_seq != record.command_seq
        or proof.action.context_hash != record.checkpoint_hash
        or proof.online_evidence.observation.episode_id != record.episode_id
        or proof.action.expected_duration_s < max(step.timeout_ms, step.expected_duration_ms) / 1000
        or [_condition_payload(item) for item in proof.action.postconditions]
        != [_condition_payload(item) for item in record.conditions]
        or proof.decision.action not in {DecisionAction.LOCAL_RECOVER, DecisionAction.REQUEST_CLOUD}
    ):
        return ("authorization_action_or_context_binding_mismatch",)
    verdict = validate_decision_commit(proof.decision, proof.current, now)
    if verdict.status != "VALID":
        return verdict.reasons
    verdict = validate_evidence(
        proof.action,
        now,
        record.checkpoint_hash,
        proof.online_evidence.observation.calibration_version or "",
        online_evidence=proof.online_evidence,
    )
    return () if verdict.status == "VALID" else verdict.reasons


def checkpoint_digest(checkpoint: ExecutionCheckpoint) -> str:
    payload = checkpoint.model_dump(mode="json")
    payload["checkpoint_hash"] = ""
    return replan_payload_hash(payload)


def authorized_values(
    record: RecoveryRecord,
    pool: VerificationBudgetRecord,
    retry: RecoveryBudget,
    proof: RecoveryAuthorizationEvidence,
    now: datetime,
) -> tuple[RecoveryRecord, VerificationBudgetRecord]:
    state = copy_budget(pool.state)
    state.remaining_retries = min(
        state.remaining_retries - 1,
        retry.remaining_retries,
        max(0, state.limits.max_retries - retry.task_retry_count),
    )
    next_pool = replace(
        pool, state=state, revision=pool.revision + 1, updated_at=now, content_hash=""
    )
    next_record = replace(
        record,
        state="RECOVERY_AUTHORIZED",
        revision=record.revision + 1,
        task_budget_revision=next_pool.revision,
        budget_state=state,
        authorization_hash=proof.digest(),
        authorized_at=now,
        evidence_scope=proof.evidence_scope,
        reason="canonical recovery authorized",
    )
    return next_record, next_pool


@dataclass(frozen=True)
class RecoveryExecutionEvidence:
    receipt: ReplanExecutionReceipt
    completion: SkillExecutionResult | None
    checkpoint_hash: str
    evidence_scope: str = field(default="UNAVAILABLE", kw_only=True)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "receipt",
            ReplanExecutionReceipt.model_validate_json(self.receipt.model_dump_json()),
        )
        if self.completion is not None:
            object.__setattr__(
                self,
                "completion",
                SkillExecutionResult.model_validate_json(self.completion.model_dump_json()),
            )


@dataclass(frozen=True)
class RecoveryTransitionEvidence:
    requested_state: str
    verification: tuple[ConditionVerdict, ...] = ()
    execution: RecoveryExecutionEvidence | None = None
    online_evidence: OnlineEvidenceSnapshot | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "verification",
            tuple(
                ConditionVerdict(
                    item.status,
                    item.condition_name,
                    item.observation_id,
                    _freeze_data(item.measured_values),
                    tuple(item.reasons),
                )
                for item in self.verification
            ),
        )
        if self.online_evidence is not None:
            source = self.online_evidence
            object.__setattr__(
                self,
                "online_evidence",
                replace(
                    source,
                    observation=type(source.observation).model_validate_json(
                        source.observation.model_dump_json()
                    ),
                    robot_state=source.robot_state.model_copy(deep=True),
                    visual_facts=_freeze_data(source.visual_facts),
                ),
            )
        if self.execution is not None:
            object.__setattr__(
                self,
                "execution",
                RecoveryExecutionEvidence(
                    self.execution.receipt,
                    self.execution.completion,
                    self.execution.checkpoint_hash,
                    evidence_scope=self.execution.evidence_scope,
                ),
            )


def _current_source(
    record: RecoveryRecord,
    active: ActiveTaskContractRecord | None,
    checkpoint: ExecutionCheckpoint | None,
    cancelled: bool,
) -> bool:
    return bool(
        not cancelled
        and active
        and checkpoint
        and active.task_id == record.task_id
        and checkpoint.task_id == record.task_id
        and active.plan_version == record.plan_version
        and active.command_seq == record.command_seq
        and checkpoint.plan_version == record.plan_version
        and checkpoint.command_seq == record.command_seq
        and active.contract_hash == record.payload_hash
        and replan_payload_hash(active.contract) == record.payload_hash
    )


def _execution_available(
    record: RecoveryRecord,
    proof: RecoveryExecutionEvidence | None,
    checkpoint: ExecutionCheckpoint,
    now: datetime,
) -> bool:
    if proof is None or proof.completion is None or proof.evidence_scope != record.evidence_scope:
        return False
    receipt, completion = proof.receipt, proof.completion
    return bool(
        record.authorized_at
        and receipt.started_at >= record.authorized_at
        and receipt.repair_id == record.attempt_id
        and receipt.task_id == record.task_id
        and receipt.plan_version == record.plan_version
        and receipt.command_seq == record.command_seq
        and receipt.payload_hash == record.payload_hash
        and completion.task_id == record.task_id
        and completion.plan_version == record.plan_version
        and completion.command_seq == record.command_seq
        and completion.step_id == record.step_id
        and completion.skill.value == record.skill
        and completion.details.get("recovery_id") == record.recovery_id
        and completion.details.get("attempt_id") == record.attempt_id
        and proof.checkpoint_hash == checkpoint_digest(checkpoint)
        and checkpoint.step_attempts.get(record.step_id, 0) > 0
        and receipt.started_at <= completion.timestamp <= checkpoint.updated_at <= now
    )


def _update_progress(
    state: VerificationBudgetState,
    conditions: tuple[ConditionSpec, ...],
    verdicts: tuple[ConditionVerdict, ...],
    valid_source: bool,
) -> None:
    rank = {"UNKNOWN": 0, "FAIL": 1, "PASS": 2}
    progress = False
    for condition, verdict in zip(conditions, verdicts, strict=True):
        key = _hash(_condition_payload(condition))
        status = str(verdict.status) if valid_source else "UNKNOWN"
        value = verdict.measured_values.get("residual_m")
        residual = (
            float(value)
            if valid_source
            and status != "UNKNOWN"
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isfinite(value)
            and value >= 0
            and verdict.measured_values.get("source") == "rgbd_estimate"
            else None
        )
        previous = state.previous_conditions.get(key)
        if previous is not None:
            old_status, old_residual = previous
            progress |= rank[status] > rank[old_status] or (
                residual is not None and old_residual is not None and residual < old_residual - 1e-6
            )
            candidates = [item for item in (old_residual, residual) if item is not None]
            state.previous_conditions[key] = (
                status if rank[status] > rank[old_status] else old_status,
                min(candidates) if candidates else None,
            )
        else:
            state.previous_conditions[key] = (status, residual)
    state.consecutive_no_progress = 0 if progress else state.consecutive_no_progress + 1
    state.verification_rounds += 1
    if state.consecutive_no_progress >= state.limits.max_no_progress:
        state.exhausted_reason = "no_progress_exhausted"


def transition_values(
    record: RecoveryRecord,
    pool: VerificationBudgetRecord,
    proof: RecoveryTransitionEvidence,
    active: ActiveTaskContractRecord | None,
    checkpoint: ExecutionCheckpoint | None,
    cancelled: bool,
    now: datetime,
) -> tuple[RecoveryRecord, VerificationBudgetRecord] | None:
    """Pure derivation inside repository CAS; providers are never invoked under its lock."""
    if not isinstance(proof, RecoveryTransitionEvidence):
        raise ValueError("typed actual transition source required")
    if record.state in {"VERIFIED_RESOLVED", "EXHAUSTED", "UNRECOVERABLE"}:
        return None
    state = copy_budget(pool.state)
    changes: dict[str, Any] = {}
    next_state = record.state
    if now >= state.deadline_at or state.exhausted_reason:
        state.exhausted_reason = state.exhausted_reason or "deadline_exhausted"
        next_state = "EXHAUSTED"
    elif proof.requested_state == "UNRECOVERABLE":
        next_state = "UNRECOVERABLE"
    elif not _current_source(record, active, checkpoint, cancelled) or checkpoint is None:
        return None
    elif record.state == "RECOVERY_AUTHORIZED" and proof.requested_state == "RETRY_EXECUTED":
        if not _execution_available(record, proof.execution, checkpoint, now):
            return None
        assert proof.execution is not None and proof.execution.completion is not None
        next_state = "RETRY_EXECUTED"
        changes.update(
            execution_receipt=proof.execution.receipt,
            execution_completion=proof.execution.completion,
            executed_at=proof.execution.completion.timestamp,
            executed_checkpoint_hash=proof.execution.checkpoint_hash,
        )
    elif record.state == "RETRY_EXECUTED" and proof.requested_state in {
        "RETRY_EXECUTED",
        "VERIFIED_RESOLVED",
    }:
        source = proof.online_evidence
        if (
            source is None
            or not _safe_robot(source.robot_state)
            or (record.last_observation_id and not record.reobservation_reserved)
        ):
            return None
        actual = tuple(evaluate_conditions(record.conditions, source, now=now))
        if _plain_data(actual) != _plain_data(proof.verification):
            raise ValueError("supplied verdict differs from canonical actual source")
        observation = source.observation
        valid = bool(
            record.executed_at
            and observation.captured_at > record.executed_at
            and observation.captured_at <= now
            and observation.episode_id == record.episode_id
            and source.plan_version == record.plan_version
            and source.command_seq == record.command_seq
            and source.context_hash == checkpoint_digest(checkpoint)
            and observation.observation_id != record.last_observation_id
            and (
                record.last_observation_captured_at is None
                or observation.captured_at > record.last_observation_captured_at
            )
        )
        _update_progress(state, record.conditions, actual, valid)
        all_pass = valid and bool(actual) and all(str(item.status) == "PASS" for item in actual)
        next_state = (
            "VERIFIED_RESOLVED"
            if all_pass
            else ("EXHAUSTED" if state.exhausted_reason else "RETRY_EXECUTED")
        )
        changes.update(
            last_verified_at=now,
            last_observation_id=observation.observation_id,
            last_observation_captured_at=observation.captured_at,
            last_verification_hash=_hash(
                {
                    "verdicts": _plain_data(actual),
                    "observation": observation.model_dump(mode="json"),
                    "facts": _plain_data(source.visual_facts),
                    "robot": source.robot_state.model_dump(mode="json"),
                    "plan_version": source.plan_version,
                    "command_seq": source.command_seq,
                    "context_hash": source.context_hash,
                }
            ),
            progress_signature=_hash(_plain_data(state.previous_conditions)),
            reobservation_reserved=False,
            resolution_observation_id=observation.observation_id if all_pass else "",
        )
    else:
        return None
    next_pool = replace(
        pool, state=state, revision=pool.revision + 1, updated_at=now, content_hash=""
    )
    updated = replace(
        record,
        **changes,
        state=next_state,
        revision=record.revision + 1,
        budget_state=state,
        task_budget_revision=next_pool.revision,
        reason=state.exhausted_reason or next_state.lower(),
    )
    return updated, next_pool


def _safe_robot(robot: RobotState) -> bool:
    return bool(robot.connected and not robot.estop_engaged and not robot.collision_detected)


@dataclass(frozen=True)
class RecoveryReservationEvidence:
    robot_state: RobotState
    checkpoint_hash: str
    captured_at: datetime
    evidence_scope: str = field(default="UNAVAILABLE", kw_only=True)

    def __post_init__(self) -> None:
        _aware(self.captured_at)
        object.__setattr__(
            self, "robot_state", RobotState.model_validate_json(self.robot_state.model_dump_json())
        )


def reservation_available(
    record: RecoveryRecord,
    proof: RecoveryReservationEvidence | None,
    active: ActiveTaskContractRecord | None,
    checkpoint: ExecutionCheckpoint | None,
    cancelled: bool,
    now: datetime,
) -> bool:
    return bool(
        isinstance(proof, RecoveryReservationEvidence)
        and checkpoint
        and _current_source(record, active, checkpoint, cancelled)
        and proof.evidence_scope == record.evidence_scope
        and proof.evidence_scope != "UNAVAILABLE"
        and _safe_robot(proof.robot_state)
        and proof.checkpoint_hash == checkpoint_digest(checkpoint)
        and 0 <= (now - proof.captured_at).total_seconds() <= 5
    )


def reserved_values(
    record: RecoveryRecord, pool: VerificationBudgetRecord, now: datetime
) -> tuple[RecoveryRecord, VerificationBudgetRecord] | None:
    if record.state != "RETRY_EXECUTED" or record.reobservation_reserved:
        return None
    state = copy_budget(pool.state)
    if now >= state.deadline_at or state.exhausted_reason:
        state.exhausted_reason = state.exhausted_reason or "deadline_exhausted"
    elif state.remaining_reobservations <= 0:
        state.exhausted_reason = "reobservation_exhausted"
    else:
        state.remaining_reobservations -= 1
    next_pool = replace(
        pool, state=state, revision=pool.revision + 1, updated_at=now, content_hash=""
    )
    updated = replace(
        record,
        revision=record.revision + 1,
        task_budget_revision=next_pool.revision,
        budget_state=state,
        reobservation_reserved=not bool(state.exhausted_reason),
        state="EXHAUSTED" if state.exhausted_reason else record.state,
        reason=state.exhausted_reason or "reobservation reserved before capture",
    )
    return updated, next_pool


class RecoveryLifecycleService:
    """Provider-backed software coordination. Missing actual providers stays unavailable."""

    def __init__(
        self,
        *,
        repository: EventAutonomyRepository,
        execution_provider: Callable[[RecoveryRecord], RecoveryExecutionEvidence | None]
        | None = None,
        evidence_provider: Callable[[RecoveryRecord], OnlineEvidenceSnapshot | None] | None = None,
        current_state_provider: Callable[[RecoveryRecord], RecoveryReservationEvidence | None]
        | None = None,
    ) -> None:
        self.repository = repository
        self.execution_provider = execution_provider
        self.evidence_provider = evidence_provider
        self.current_state_provider = current_state_provider

    def _source_preflight(self, record: RecoveryRecord, pool: VerificationBudgetRecord) -> bool:
        if _utc_clock() >= pool.state.deadline_at or pool.state.exhausted_reason:
            return False
        cancelled = self.repository.get_state(record.task_id) in {
            "CANCELLED",
            "ABORTED",
            "STOPPED",
            "SAFETY_STOPPED",
            "COMPLETED",
        } or any(
            event.severity == "CRITICAL" or event.event_type.value == "MANUAL_INTERRUPT"
            for event in self.repository.list_events(record.task_id)
        )
        return _current_source(
            record,
            self.repository.get_active_contract(record.task_id),
            self.repository.get_latest_execution_checkpoint(record.task_id),
            cancelled,
        )

    def advance_recovery(
        self,
        recovery_id: str,
        expected_state: str,
        next_state: str,
        verification: Sequence[ConditionVerdict],
    ) -> RecoveryRecord:
        record = self.repository.get_recovery(recovery_id)
        if record is None:
            raise ValueError("unknown recovery identity")
        if record.state != expected_state:
            return record
        pool = self.repository.get_verification_budget(record.task_id)
        if pool is None:
            return record
        source_available = self._source_preflight(record, pool)
        execution = (
            self.execution_provider(record.detached())
            if source_available
            and next_state == "RETRY_EXECUTED"
            and expected_state == "RECOVERY_AUTHORIZED"
            and self.execution_provider is not None
            else None
        )
        source = (
            self.evidence_provider(record.detached())
            if source_available
            and expected_state == "RETRY_EXECUTED"
            and self.evidence_provider is not None
            and (not record.last_observation_id or record.reobservation_reserved)
            else None
        )
        proof = RecoveryTransitionEvidence(next_state, tuple(verification), execution, source)
        updated = self.repository.advance_recovery_if_current(
            record,
            expected_state=expected_state,
            expected_revision=record.revision,
            expected_budget_revision=pool.revision,
            verified_transition=proof,
        )
        return updated or self.repository.get_recovery(recovery_id) or record

    def reserve_reobservation(self, recovery_id: str) -> RecoveryRecord | None:
        record = self.repository.get_recovery(recovery_id)
        if record is None:
            return None
        pool = self.repository.get_verification_budget(record.task_id)
        if pool is None:
            return None
        if self.current_state_provider is None or not self._source_preflight(record, pool):
            return None
        proof = self.current_state_provider(record.detached())
        updated = self.repository.reserve_reobservation_if_current(
            recovery_id=recovery_id,
            expected_revision=record.revision,
            expected_budget_revision=pool.revision,
            reservation=proof,
        )
        return updated if updated and updated.reobservation_reserved else None
