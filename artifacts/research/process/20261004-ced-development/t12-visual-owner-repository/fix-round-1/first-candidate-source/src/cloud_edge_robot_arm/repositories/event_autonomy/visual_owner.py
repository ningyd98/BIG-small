"""Strict durable source codecs; no actual owner, lease, mode or admission authority."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, get_args, get_origin

from pydantic import BaseModel

from cloud_edge_robot_arm.contracts.models import (
    ActiveTaskContractRecord,
    ExecutionCheckpoint,
    RecoveryBudget,
    TaskContract,
    TaskStep,
)
from cloud_edge_robot_arm.repositories.event_autonomy.hashing import stable_payload_hash

if TYPE_CHECKING:
    from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord
    from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudgetState
    from cloud_edge_robot_arm.vision.owner_registration import (
        OriginalActionRequirements,
        StepGroundingBinding,
        VisualOriginalPlan,
        VisualOwnerIdentity,
    )


def canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware durable source clock required")
    return value


def counter(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("strict nonnegative source revision required")
    return value


def sha(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError("exact source SHA256 required")
    return value


def _finite(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite durable source payload")


_Model = TypeVar("_Model", bound=BaseModel)


def serialized_model(payload: Any, model: type[_Model]) -> _Model:
    """Reject raw schema/type differences before a decoded model can hide them."""
    if not isinstance(payload, dict) or set(payload) != set(model.model_fields):
        raise ValueError("complete registered durable model schema required")
    for name, field in model.model_fields.items():
        if field.annotation is int:
            counter(payload[name])
        elif get_origin(field.annotation) is dict and get_args(field.annotation)[1:] == (int,):
            if not isinstance(payload[name], dict):
                raise ValueError("registered integer source map required")
            for item in payload[name].values():
                counter(item)
    _finite(payload)
    encoded = canonical(payload)
    result = model.model_validate_json(encoded)
    if canonical(result.model_dump(mode="json")) != encoded:
        raise ValueError("serialized durable model types or values changed")
    return result


def requirement_from_payload(payload: dict[str, Any]) -> OriginalActionRequirements:
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.vision.owner_registration import OriginalActionRequirements

    result = OriginalActionRequirements(
        TaskStep.model_validate_json(canonical(payload["original_step"])),
        tuple(ConditionSpec(**condition) for condition in payload["preconditions"]),
        tuple(ConditionSpec(**condition) for condition in payload["postconditions"]),
        payload["allowed_error_m"],
        tuple(payload["sensor_requirements"]),
        payload["ordinary_ttl_s"],
        payload["expected_duration_s"],
        payload["policy_source_hashes"],
    )
    if canonical(result.to_payload()) != canonical(payload):
        raise ValueError("original requirement envelope differs")
    return result


def original_from_payload(payload: dict[str, Any]) -> VisualOriginalPlan:
    from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
    from cloud_edge_robot_arm.vision.owner_registration import (
        VisualOwnerIdentity,
        freeze_original_visual_plan,
    )

    result = freeze_original_visual_plan(
        identity=VisualOwnerIdentity(**payload["identity"]),
        contract=TaskContract.model_validate_json(canonical(payload["contract"])),
        proposal_hash=payload["proposal_hash"],
        role_bundle_hash=payload["role_bundle_hash"],
        compiler_source_hashes=payload["compiler_source_hashes"],
        source_hashes=payload["source_hashes"],
        requirements={
            name: requirement_from_payload(value) for name, value in payload["requirements"].items()
        },
        dependencies=tuple(StepDependency(**value) for value in payload["dependencies"]),
        task_deadline_at=datetime.fromisoformat(payload["task_deadline_at"]),
        verification_deadline_at=datetime.fromisoformat(payload["verification_deadline_at"]),
        registered_at=datetime.fromisoformat(payload["registered_at"]),
    )
    if canonical(result.to_payload()) != canonical(payload):
        raise ValueError("original source envelope differs")
    return result


def copy_original(original: VisualOriginalPlan) -> VisualOriginalPlan:
    return original_from_payload(json.loads(canonical(original.to_payload())))


def grounding_from_payload(payload: dict[str, Any]) -> StepGroundingBinding:
    from cloud_edge_robot_arm.vision.owner_registration import (
        StepGroundingBinding,
        VisualOwnerIdentity,
    )

    values = dict(payload)
    values.pop("binding_scope", None)
    values["current_identity"] = VisualOwnerIdentity(**values["current_identity"])
    values["original_requirements"] = requirement_from_payload(values["original_requirements"])
    values["_grounded_step_json"] = canonical(values.pop("grounded_step"))
    for name in ("created_at", "valid_until"):
        values[name] = datetime.fromisoformat(values[name])
    result = StepGroundingBinding(**values)
    if canonical(result.to_payload()) != canonical(payload):
        raise ValueError("grounding source envelope differs")
    return result


def strict_checkpoint(checkpoint: ExecutionCheckpoint) -> ExecutionCheckpoint:
    payload = checkpoint.model_dump(mode="json")
    _finite(payload)
    for name in ("plan_version", "command_seq", "scene_version", "current_step_index"):
        counter(payload[name])
    for value in payload["step_attempts"].values():
        counter(value)
    result = ExecutionCheckpoint.model_validate_json(canonical(payload))
    aware(result.created_at)
    aware(result.updated_at)
    if result.created_at > result.updated_at or result.updated_at > datetime.now(UTC):
        raise ValueError("checkpoint clock reversed or future")
    expected = dict(result.model_dump(mode="json"))
    expected["checkpoint_hash"] = ""
    if sha(result.checkpoint_hash) != stable_payload_hash(expected):
        raise ValueError("checkpoint canonical source hash differs")
    return result


def strict_retry(budget: RecoveryBudget) -> RecoveryBudget:
    payload = budget.model_dump(mode="json")
    _finite(payload)
    for name, value in payload.items():
        if name.endswith("_counts"):
            for item in value.values():
                counter(item)
        elif name.endswith("_limit") or name in {
            "retry_count_used",
            "task_retry_count",
            "retry_cooldown_ms",
            "remaining_retries",
            "scene_version",
        }:
            counter(value)
    result = RecoveryBudget.model_validate_json(canonical(payload))
    if not result.budget_id or result.retry_deadline is None:
        raise ValueError("explicit original retry pool identity/deadline required")
    aware(result.retry_deadline)
    aware(result.created_at)
    aware(result.updated_at)
    if (
        result.updated_at < result.created_at
        or result.retry_count_used != result.task_retry_count
        or result.task_retry_count > result.task_total_retry_limit
        or result.remaining_retries > result.task_total_retry_limit - result.task_retry_count
        or result.remaining_retries > result.effective_retry_limit
    ):
        raise ValueError("retry source counts/horizon inconsistent")
    return result


def retry_definition(budget: RecoveryBudget) -> dict[str, Any]:
    values = strict_retry(budget).model_dump(mode="json")
    return {
        name: values[name]
        for name in (
            "budget_id",
            "task_id",
            "per_step_retry_limit",
            "per_skill_retry_limit",
            "task_total_retry_limit",
            "retry_cooldown_ms",
            "retry_deadline",
            "retry_backoff_policy",
            "effective_retry_limit",
            "scene_version",
        )
    }


def retry_deadline(budget: RecoveryBudget) -> datetime:
    if budget.retry_deadline is None:
        raise ValueError("original retry deadline unavailable")
    return aware(budget.retry_deadline)


def verification_definition(pool: VerificationBudgetRecord) -> dict[str, Any]:
    verified = pool.detached()
    return {
        "task_id": verified.task_id,
        "limits": verified.to_payload()["state"]["limits"],
        "deadline_at": verified.state.deadline_at.isoformat(),
    }


def make_verification_pool(
    task_id: str, state: VerificationBudgetState
) -> VerificationBudgetRecord:
    from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord

    return VerificationBudgetRecord.create(task_id, state)


def validate_checkpoint(
    original: VisualOriginalPlan,
    checkpoint: ExecutionCheckpoint,
    previous: ExecutionCheckpoint | None = None,
) -> ExecutionCheckpoint:
    current = strict_checkpoint(checkpoint)
    identity, contract = original.identity, original.contract
    ids = [step.step_id for step in contract.steps]
    done = current.completed_step_ids
    if (
        (current.task_id, current.plan_id, current.robot_id)
        != (identity.task_id, identity.plan_id, identity.robot_id)
        or (current.plan_version, current.command_seq, current.scene_version)
        != (contract.plan_version, contract.command_seq, contract.scene_version)
        or ids[: len(done)] != done
        or current.pending_step_ids != ids[len(done) :]
        or current.current_step_index != len(done)
        or current.current_step_id
        != (current.pending_step_ids[0] if current.pending_step_ids else "")
        or current.created_at < original.registered_at
    ):
        raise ValueError("original checkpoint identity/version/cursor differs")
    if previous is not None and (
        done[: len(previous.completed_step_ids)] != previous.completed_step_ids
        or current.created_at != previous.created_at
        or current.updated_at < previous.updated_at
    ):
        raise ValueError("completed original effects or boundary clock regressed")
    return current


def validate_group(
    original: VisualOriginalPlan,
    active: ActiveTaskContractRecord,
    checkpoint: ExecutionCheckpoint,
    pool: VerificationBudgetRecord,
    retry: RecoveryBudget,
) -> None:
    identity, contract = original.identity, original.contract
    record = ActiveTaskContractRecord.model_validate_json(active.model_dump_json())
    if (
        record.status != "ACTIVE"
        or record.contract_hash != stable_payload_hash(record.contract)
        or record.contract_hash != stable_payload_hash(contract)
        or (record.task_id, record.plan_id, record.robot_id)
        != (identity.task_id, identity.plan_id, identity.robot_id)
        or (record.plan_version, record.command_seq, record.scene_version)
        != (contract.plan_version, contract.command_seq, contract.scene_version)
    ):
        raise ValueError("original active contract/source identity differs")
    validate_checkpoint(original, checkpoint)
    pool = pool.detached()
    retry = strict_retry(retry)
    if (
        pool.task_id != identity.task_id
        or retry.task_id != identity.task_id
        or retry.scene_version != contract.scene_version
        or pool.state.deadline_at != original.verification_deadline_at
        or retry_deadline(retry) > original.effective_deadline_at
    ):
        raise ValueError("original task pool identity/deadline differs")


@dataclass(frozen=True, init=False)
class VisualOwnerPublicationRecord:
    _payload_json: str
    binding_scope: ClassVar[str] = "DURABLE_BINDING_ONLY"
    mode_scope: ClassVar[str] = "NOT_INCLUDED"

    def __init__(self, payload: dict[str, Any]) -> None:
        values = dict(payload)
        declared = values.pop("publication_hash", None)
        required = {
            "schema_version",
            "binding_scope",
            "mode_scope",
            "identity",
            "original_plan_hash",
            "contract_hash",
            "owner_revision",
            "state_generation",
            "checkpoint",
            "verification_budget",
            "retry_budget",
            "grounding",
            "effective_deadline_at",
            "operation_hash",
            "source_owner_revision",
            "published_at",
        }
        if (
            set(values) != required
            or values["schema_version"] != "visual.owner.publication.v1"
            or values["binding_scope"] != "DURABLE_BINDING_ONLY"
            or values["mode_scope"] != "NOT_INCLUDED"
        ):
            raise ValueError("unsupported durable publication envelope/scope")
        from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord
        from cloud_edge_robot_arm.vision.owner_registration import VisualOwnerIdentity

        identity = VisualOwnerIdentity(**values["identity"])
        checkpoint = strict_checkpoint(serialized_model(values["checkpoint"], ExecutionCheckpoint))
        pool = VerificationBudgetRecord.from_payload(values["verification_budget"])
        retry = strict_retry(serialized_model(values["retry_budget"], RecoveryBudget))
        if (
            (checkpoint.task_id, checkpoint.plan_id, checkpoint.robot_id)
            != (identity.task_id, identity.plan_id, identity.robot_id)
            or pool.task_id != identity.task_id
            or retry.task_id != identity.task_id
        ):
            raise ValueError("foreign publication source identity")
        for name in ("original_plan_hash", "contract_hash", "operation_hash"):
            sha(values[name])
        for name in ("owner_revision", "state_generation"):
            counter(values[name])
        if values["owner_revision"] < 1:
            raise ValueError("initial owner revision must be positive")
        if values["source_owner_revision"] is not None:
            counter(values["source_owner_revision"])
        deadline, published = (
            aware(datetime.fromisoformat(values[name]))
            for name in ("effective_deadline_at", "published_at")
        )
        if (
            deadline > pool.state.deadline_at
            or deadline > retry_deadline(retry)
            or checkpoint.updated_at > published
        ):
            raise ValueError("publication deadline/clock differs")
        if values["grounding"] is not None:
            grounding_from_payload(values["grounding"])
        _finite(values)
        encoded = canonical(values)
        if declared is not None and sha(declared) != digest(values):
            raise ValueError("publication hash differs")
        object.__setattr__(self, "_payload_json", encoded)

    def to_payload(self) -> dict[str, Any]:
        values = json.loads(self._payload_json)
        return {**values, "publication_hash": digest(values)}

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> VisualOwnerPublicationRecord:
        if "publication_hash" not in payload:
            raise ValueError("stored publication hash missing")
        return cls(payload)

    def digest(self) -> str:
        return digest(json.loads(self._payload_json))

    def detached(self) -> VisualOwnerPublicationRecord:
        return type(self).from_payload(self.to_payload())

    @property
    def identity(self) -> VisualOwnerIdentity:
        from cloud_edge_robot_arm.vision.owner_registration import VisualOwnerIdentity

        return VisualOwnerIdentity(**json.loads(self._payload_json)["identity"])

    @property
    def checkpoint(self) -> ExecutionCheckpoint:
        return serialized_model(json.loads(self._payload_json)["checkpoint"], ExecutionCheckpoint)

    @property
    def verification_budget(self) -> VerificationBudgetRecord:
        from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord

        return VerificationBudgetRecord.from_payload(
            json.loads(self._payload_json)["verification_budget"]
        )

    @property
    def retry_budget(self) -> RecoveryBudget:
        return serialized_model(json.loads(self._payload_json)["retry_budget"], RecoveryBudget)

    @property
    def owner_revision(self) -> int:
        return int(json.loads(self._payload_json)["owner_revision"])

    @property
    def state_generation(self) -> int:
        return int(json.loads(self._payload_json)["state_generation"])

    @property
    def original_plan_hash(self) -> str:
        return str(json.loads(self._payload_json)["original_plan_hash"])

    @property
    def effective_deadline_at(self) -> datetime:
        return datetime.fromisoformat(json.loads(self._payload_json)["effective_deadline_at"])


def publication(
    original: VisualOriginalPlan,
    checkpoint: ExecutionCheckpoint,
    pool: VerificationBudgetRecord,
    retry: RecoveryBudget,
    *,
    revision: int,
    generation: int,
    source_revision: int | None,
    operation_hash: str,
    grounding: StepGroundingBinding | None = None,
) -> VisualOwnerPublicationRecord:
    deadline = min(original.effective_deadline_at, pool.state.deadline_at, retry_deadline(retry))
    if datetime.now(UTC) >= deadline:
        raise ValueError("original source deadline expired")
    return VisualOwnerPublicationRecord(
        {
            "schema_version": "visual.owner.publication.v1",
            "binding_scope": "DURABLE_BINDING_ONLY",
            "mode_scope": "NOT_INCLUDED",
            "identity": original.identity.to_payload(),
            "original_plan_hash": original.digest(),
            "contract_hash": stable_payload_hash(original.contract),
            "owner_revision": revision,
            "state_generation": generation,
            "checkpoint": checkpoint.model_dump(mode="json"),
            "verification_budget": pool.to_payload(),
            "retry_budget": retry.model_dump(mode="json"),
            "grounding": grounding.to_payload() if grounding else None,
            "effective_deadline_at": deadline.isoformat(),
            "operation_hash": operation_hash,
            "source_owner_revision": source_revision,
            "published_at": datetime.now(UTC).isoformat(),
        }
    )


def current_publication(
    record: VisualOwnerPublicationRecord,
    original: VisualOriginalPlan,
    active: ActiveTaskContractRecord | None,
    checkpoint: ExecutionCheckpoint | None,
    pool: VerificationBudgetRecord | None,
    retry: RecoveryBudget | None,
    previous: VisualOwnerPublicationRecord | None = None,
) -> bool:
    if active is None or checkpoint is None or pool is None or retry is None:
        return False
    try:
        validate_group(original, active, checkpoint, pool, retry)
    except (ValueError, TypeError):
        return False
    try:
        if not record_binding_valid(record, original, previous):
            return False
        payload = record.to_payload()
        if payload["grounding"] is not None and (
            datetime.now(UTC) >= grounding_from_payload(payload["grounding"]).valid_until
        ):
            return False
    except (ValueError, TypeError):
        return False
    return (
        record.identity == original.identity
        and record.original_plan_hash == original.digest()
        and record.to_payload()["contract_hash"] == active.contract_hash
        and canonical(record.checkpoint.model_dump(mode="json"))
        == canonical(checkpoint.model_dump(mode="json"))
        and record.verification_budget.content_hash == pool.detached().content_hash
        and canonical(record.retry_budget.model_dump(mode="json"))
        == canonical(retry.model_dump(mode="json"))
        and datetime.now(UTC) < record.effective_deadline_at
    )


def record_binding_valid(
    record: VisualOwnerPublicationRecord,
    original: VisualOriginalPlan,
    previous: VisualOwnerPublicationRecord | None,
) -> bool:
    payload = record.to_payload()
    if (
        record.identity != original.identity
        or record.original_plan_hash != original.digest()
        or payload["contract_hash"] != stable_payload_hash(original.contract)
    ):
        return False
    if record.owner_revision == 1:
        if (
            previous is not None
            or record.state_generation != 0
            or payload["source_owner_revision"] is not None
            or payload["grounding"] is not None
        ):
            return False
        expected = operation_hash(
            original_hash=original.digest(),
            checkpoint=record.checkpoint,
            verification_definition=verification_definition(record.verification_budget),
            retry_definition=retry_definition(record.retry_budget),
        )
    else:
        if (
            previous is None
            or previous.owner_revision != record.owner_revision - 1
            or previous.identity != original.identity
            or previous.original_plan_hash != original.digest()
            or payload["source_owner_revision"] != previous.owner_revision
            or record.state_generation <= previous.state_generation
        ):
            return False
        validate_checkpoint(original, record.checkpoint, previous.checkpoint)
        ground = (
            grounding_from_payload(payload["grounding"])
            if payload["grounding"] is not None
            else None
        )
        validate_grounding(
            original,
            previous,
            record.checkpoint,
            ground,
            record.state_generation,
            at=aware(datetime.fromisoformat(payload["published_at"])),
        )
        expected = operation_hash(
            task_id=original.identity.task_id,
            owner_epoch=original.identity.owner_epoch,
            expected_owner_revision=previous.owner_revision,
            expected_contract_hash=payload["contract_hash"],
            expected_checkpoint_hash=previous.checkpoint.checkpoint_hash,
            checkpoint=record.checkpoint,
            grounding=ground,
            state_generation=record.state_generation,
        )
    return bool(payload["operation_hash"] == expected)


def operation_hash(**values: Any) -> str:
    return digest(
        {
            name: value.to_payload()
            if hasattr(value, "to_payload")
            else value.model_dump(mode="json")
            if hasattr(value, "model_dump")
            else value
            for name, value in values.items()
        }
    )


def initial_inputs(
    original: VisualOriginalPlan,
    checkpoint: ExecutionCheckpoint,
    state: VerificationBudgetState,
    retry: RecoveryBudget,
) -> tuple[VisualOriginalPlan, ExecutionCheckpoint, VerificationBudgetRecord, RecoveryBudget, str]:
    original = copy_original(original)
    checkpoint = validate_checkpoint(original, checkpoint)
    pool = make_verification_pool(original.identity.task_id, state)
    retry = strict_retry(retry)
    if (
        pool.state.deadline_at != original.verification_deadline_at
        or retry.task_id != original.identity.task_id
        or retry.scene_version != original.contract.scene_version
        or retry_deadline(retry) > original.effective_deadline_at
        or pool.state.remaining_retries > retry.remaining_retries
    ):
        raise ValueError("initial source pool definition differs from original")
    key = operation_hash(
        original_hash=original.digest(),
        checkpoint=checkpoint,
        verification_definition=verification_definition(pool),
        retry_definition=retry_definition(retry),
    )
    return original, checkpoint, pool, retry, key


def monotonic_pools(
    record: VisualOwnerPublicationRecord, pool: VerificationBudgetRecord, retry: RecoveryBudget
) -> bool:
    before_pool, before_retry = record.verification_budget, record.retry_budget
    if (
        verification_definition(pool) != verification_definition(before_pool)
        or retry_definition(retry) != retry_definition(before_retry)
        or pool.revision < before_pool.revision
        or pool.state.remaining_reobservations > before_pool.state.remaining_reobservations
        or pool.state.remaining_retries > before_pool.state.remaining_retries
        or pool.state.verification_rounds < before_pool.state.verification_rounds
        or retry.remaining_retries > before_retry.remaining_retries
        or retry.task_retry_count < before_retry.task_retry_count
        or retry.retry_count_used < before_retry.retry_count_used
        or retry.created_at != before_retry.created_at
        or retry.updated_at < before_retry.updated_at
    ):
        return False
    for name in ("step_retry_counts", "skill_retry_counts", "event_retry_counts"):
        if any(
            getattr(retry, name).get(key, 0) < value
            for key, value in getattr(before_retry, name).items()
        ):
            return False
    return True


def validate_grounding(
    original: VisualOriginalPlan,
    previous: VisualOwnerPublicationRecord,
    checkpoint: ExecutionCheckpoint,
    grounding: StepGroundingBinding | None,
    generation: int,
    *,
    at: datetime | None = None,
) -> StepGroundingBinding | None:
    if grounding is None:
        return None
    copied = grounding_from_payload(json.loads(canonical(grounding.to_payload())))
    requirement = original.requirements.get(copied.grounded_step.step_id)
    if (
        copied.current_identity != original.identity
        or copied.original_plan_hash != original.digest()
        or copied.owner_revision != previous.owner_revision
        or copied.state_generation != generation
        or copied.source_checkpoint_hash != previous.checkpoint.checkpoint_hash
        or (copied.plan_version, copied.command_seq)
        != (checkpoint.plan_version, checkpoint.command_seq)
        or copied.grounded_step.step_id != checkpoint.current_step_id
        or requirement is None
        or copied.original_requirements.digest() != requirement.digest()
        or copied.valid_until > original.effective_deadline_at
        or (aware(at) if at is not None else datetime.now(UTC)) >= copied.valid_until
        or copied.created_at > checkpoint.updated_at
        or checkpoint.safety_state.get("grounding_binding_hash") != copied.binding_hash
        or checkpoint.safety_state.get("original_requirements_hash") != requirement.digest()
        or any(
            original.source_hashes.get(name) != value
            for name, value in copied.grounding_source_hashes.items()
        )
    ):
        raise ValueError("grounding original/current boundary binding differs")
    return copied
