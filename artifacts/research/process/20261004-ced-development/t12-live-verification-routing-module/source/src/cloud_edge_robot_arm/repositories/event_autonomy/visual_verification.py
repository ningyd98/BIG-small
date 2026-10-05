"""Pure SOURCE_ROUTE_ONLY verification records. No source authentication or execution.

The repository samples the transaction clock. No callback, provider, sensor or
executor is called here. LEGACY's router and pool behavior remain unchanged.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import asdict, replace
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal, cast

from pydantic import BaseModel

from cloud_edge_robot_arm.contracts.models import (
    ActiveTaskContractRecord,
    ExecutionCheckpoint,
    RecoveryBudget,
    RobotState,
    SkillExecutionResult,
    TaskContract,
)
from cloud_edge_robot_arm.edge.evidence.conditions import (
    ConditionStatus,
    ConditionVerdict,
    OnlineEvidenceSnapshot,
    evaluate_conditions,
)
from cloud_edge_robot_arm.edge.evidence.models import ActionEvidenceContract
from cloud_edge_robot_arm.edge.evidence.validator import validate_evidence
from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord, copy_budget
from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudgetState
from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
    VisualOwnerPublicationRecord,
    aware,
    canonical,
    counter,
    current_publication,
    digest,
    grounding_from_payload,
    operation_hash,
    original_from_payload,
    publication,
    serialized_model,
    sha,
)
from cloud_edge_robot_arm.vision.action_evidence import native_action_contract
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import VisualOriginalPlan

PHASES = frozenset(
    {
        "PRECONDITION",
        "NATIVE_PRE_SAFETY",
        "NATIVE_PRE_SKILL",
        "CLOUD_RETURN",
        "AFTER_EFFECT",
        "POST_HOLD",
        "TERMINAL",
    }
)
NATIVE_PHASES = frozenset({"NATIVE_PRE_SAFETY", "NATIVE_PRE_SKILL", "CLOUD_RETURN"})
EFFECT_PHASES = frozenset({"AFTER_EFFECT", "POST_HOLD", "TERMINAL"})


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(type(k) is not str for k in value):
            raise ValueError("string source keys required")
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return aware(value).isoformat()
    if value is None or type(value) in (str, bool):
        return value
    if type(value) is int and abs(value) <= 2**63 - 1:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("finite strict JSON source required")


def _load(raw: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate source JSON key")
            result[key] = value
        return result

    def bad(value: str) -> None:
        raise ValueError(f"nonfinite JSON token {value}")

    if type(raw) is not str:
        raise ValueError("original source JSON string required")
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)
    if type(result) is not dict:
        raise ValueError("full source envelope required")
    return cast(dict[str, Any], _plain(result))


def _identifier(value: Any) -> str:
    if type(value) is not str or not value.strip() or len(value) > 200:
        raise ValueError("bounded source identity required")
    return value


def _pool(raw: dict[str, Any]) -> VerificationBudgetRecord:
    raw = _plain(raw)
    if set(raw) != {
        "schema_version",
        "task_id",
        "state",
        "revision",
        "created_at",
        "updated_at",
        "content_hash",
    }:
        raise ValueError("complete verification pool required")
    state = raw["state"]
    if set(state) != {
        "remaining_reobservations",
        "remaining_retries",
        "consecutive_no_progress",
        "deadline_at",
        "limits",
        "previous_conditions",
        "exhausted_reason",
        "verification_rounds",
    }:
        raise ValueError("complete verification state required")
    for name in (
        "remaining_reobservations",
        "remaining_retries",
        "consecutive_no_progress",
        "verification_rounds",
    ):
        counter(state[name])
    if set(state["limits"]) != {
        "max_reobservations",
        "max_retries",
        "max_no_progress",
        "deadline_s",
    }:
        raise ValueError("complete original verification limits required")
    for name in ("max_reobservations", "max_retries", "max_no_progress"):
        counter(state["limits"][name])
    for key, pair in state["previous_conditions"].items():
        _identifier(key)
        if (
            not isinstance(pair, list)
            or len(pair) != 2
            or pair[0] not in {"UNKNOWN", "FAIL", "PASS"}
        ):
            raise ValueError("strict best verified condition history required")
        if pair[1] is not None and (type(pair[1]) not in (float, int) or pair[1] < 0):
            raise ValueError("finite nonnegative progress residual required")
    result = VerificationBudgetRecord.from_payload(raw)
    if canonical(result.to_payload()) != canonical(raw):
        raise ValueError("pool source types changed")
    return result


def strict_source_json_model(raw: str, model: type[BaseModel]) -> BaseModel:
    """Read current source bytes before Pydantic can discard unknown/coerced fields."""
    return serialized_model(_load(raw), model)


def current_models_exact(*models: BaseModel | None) -> bool:
    def walk(value: Any) -> None:
        if isinstance(value, BaseModel):
            if set(vars(value)) - set(type(value).model_fields):
                raise ValueError("undeclared current source model fields")
            serialized_model(value.model_dump(mode="json"), type(value))
            for name in type(value).model_fields:
                walk(getattr(value, name))
        elif isinstance(value, Mapping):
            for item in value.values():
                walk(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                walk(item)

    try:
        for model in models:
            if model is None:
                return False
            walk(model)
    except (ValueError, TypeError):
        return False
    return True


def evidence_content_hash(online: OnlineEvidenceSnapshot) -> str:
    """v1 exact frozen evidence body excluding its separately named context domain."""
    return digest(
        dict(
            schema_version="visual.verification.evidence-content.v1",
            observation=online.observation.model_dump(mode="json"),
            robot_state=online.robot_state.model_dump(mode="json"),
            visual_facts=_plain(online.visual_facts),
            plan_version=online.plan_version,
            command_seq=online.command_seq,
        )
    )


def native_action_context_hash(role_bundle_hash: str, contract: TaskContract, step_id: str) -> str:
    """Existing native v1 hash payload; domain name lives in the route schema."""
    step = next((s for s in contract.steps if s.step_id == step_id), None)
    if step is None:
        raise ValueError("current native step missing")
    return digest(
        dict(
            role_bundle_hash=sha(role_bundle_hash),
            contract=contract.model_dump(mode="json"),
            step=step.model_dump(mode="json"),
        )
    )


def camera_source_descriptor_sha256(observation: RGBDObservation) -> str:
    """Fixed v1 descriptor content identity; never calibration authentication."""
    return digest(
        dict(
            schema_version="visual.rgbd.camera-source-descriptor.v1",
            **{
                k: observation.model_dump(mode="json")[k]
                for k in (
                    "source",
                    "width",
                    "height",
                    "intrinsics",
                    "camera_to_world",
                    "depth_convention",
                    "calibration_version",
                )
            },
        )
    )


class _FrozenJSON:
    __slots__ = ("_json",)
    _json: str
    scope: ClassVar[str] = "SOURCE_ROUTE_ONLY"

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("immutable source record")

    def to_payload(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self._json))

    def to_json(self) -> str:
        return self._json

    def digest(self) -> str:
        return digest(self.to_payload())


class VisualEffectCompletion(_FrozenJSON):
    """Typed result/return source carrier only; public construction authenticates nothing."""

    def __init__(
        self,
        *,
        result: SkillExecutionResult,
        task_id: str,
        plan_id: str,
        robot_id: str,
        step_id: str,
        attempt: int,
        plan_version: int,
        command_seq: int,
        started_at: datetime,
        returned_at: datetime,
        before_observation_id: str,
        execution_payload_hash: str,
        source_checkpoint_hash: str,
        source_hashes: Mapping[str, str],
    ) -> None:
        raw = dict(
            schema_version="visual.verification.effect-completion.v1",
            scope=self.scope,
            result=result.model_dump(mode="json"),
            task_id=task_id,
            plan_id=plan_id,
            robot_id=robot_id,
            step_id=step_id,
            attempt=attempt,
            plan_version=plan_version,
            command_seq=command_seq,
            started_at=aware(started_at).isoformat(),
            returned_at=aware(returned_at).isoformat(),
            before_observation_id=before_observation_id,
            execution_payload_hash=execution_payload_hash,
            source_checkpoint_hash=source_checkpoint_hash,
            source_hashes=_plain(source_hashes),
        )
        self._store(raw)

    def _store(self, raw: dict[str, Any]) -> None:
        if (
            set(raw)
            != {
                "schema_version",
                "scope",
                "result",
                "task_id",
                "plan_id",
                "robot_id",
                "step_id",
                "attempt",
                "plan_version",
                "command_seq",
                "started_at",
                "returned_at",
                "before_observation_id",
                "execution_payload_hash",
                "source_checkpoint_hash",
                "source_hashes",
            }
            or raw["schema_version"] != "visual.verification.effect-completion.v1"
            or raw["scope"] != "SOURCE_ROUTE_ONLY"
        ):
            raise ValueError("strict effect completion source schema required")
        serialized_model(raw["result"], SkillExecutionResult)
        for name in ("task_id", "plan_id", "robot_id", "step_id", "before_observation_id"):
            _identifier(raw[name])
        for name in ("attempt", "plan_version", "command_seq"):
            counter(raw[name])
        if raw["attempt"] < 1 or raw["command_seq"] < 1:
            raise ValueError("positive attempt/sequence required")
        if aware(datetime.fromisoformat(raw["started_at"])) > aware(
            datetime.fromisoformat(raw["returned_at"])
        ):
            raise ValueError("effect return predates start")
        for name in ("execution_payload_hash", "source_checkpoint_hash"):
            sha(raw[name])
        if not raw["source_hashes"]:
            raise ValueError("effect source inventory required")
        for name, value in raw["source_hashes"].items():
            _identifier(name)
            sha(value)
        object.__setattr__(self, "_json", canonical(_plain(raw)))

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> VisualEffectCompletion:
        result = object.__new__(cls)
        result._store(_plain(raw))
        return result


class VisualVerificationRouteInput(_FrozenJSON):
    def __init__(
        self,
        *,
        original: VisualOriginalPlan,
        publication: VisualOwnerPublicationRecord,
        online: OnlineEvidenceSnapshot,
        step_id: str,
        attempt: int,
        phase: str,
        event_key: str,
        execution_contract: TaskContract,
        completion: VisualEffectCompletion | None = None,
    ) -> None:
        raw = dict(
            schema_version="visual.verification.route-input.v1",
            scope=self.scope,
            original=original.to_payload(),
            publication=publication.to_payload(),
            online=dict(
                observation=online.observation.model_dump(mode="json"),
                robot_state=online.robot_state.model_dump(mode="json"),
                visual_facts=_plain(online.visual_facts),
                plan_version=online.plan_version,
                command_seq=online.command_seq,
                context_hash=online.context_hash,
            ),
            step_id=step_id,
            attempt=attempt,
            phase=phase,
            event_key=event_key,
            execution_contract=execution_contract.model_dump(mode="json"),
            completion=completion.to_payload() if completion is not None else None,
        )
        self._store(raw)

    def _store(self, raw: dict[str, Any]) -> None:
        if (
            set(raw)
            != {
                "schema_version",
                "scope",
                "original",
                "publication",
                "online",
                "step_id",
                "attempt",
                "phase",
                "event_key",
                "execution_contract",
                "completion",
            }
            or raw["schema_version"] != "visual.verification.route-input.v1"
            or raw["scope"] != "SOURCE_ROUTE_ONLY"
        ):
            raise ValueError("strict source route input/scope required")
        original = original_from_payload(raw["original"])
        publication_ = VisualOwnerPublicationRecord.from_payload(raw["publication"])
        _pool(raw["publication"]["verification_budget"])
        _identifier(raw["step_id"])
        _identifier(raw["event_key"])
        counter(raw["attempt"])
        if raw["attempt"] < 1 or raw["phase"] not in PHASES:
            raise ValueError("registered routing phase/attempt required")
        online = raw["online"]
        if set(online) != {
            "observation",
            "robot_state",
            "visual_facts",
            "plan_version",
            "command_seq",
            "context_hash",
        }:
            raise ValueError("complete evidence body required")
        serialized_model(online["observation"], RGBDObservation)
        serialized_model(online["robot_state"], RobotState)
        if type(online["visual_facts"]) is not dict:
            raise ValueError("full online facts required")
        counter(online["plan_version"])
        counter(online["command_seq"])
        sha(online["context_hash"])
        serialized_model(raw["execution_contract"], TaskContract)
        if raw["completion"] is not None:
            VisualEffectCompletion.from_payload(raw["completion"])
        if original.identity.task_id != publication_.identity.task_id:
            raise ValueError("foreign original/publication task")
        object.__setattr__(self, "_json", canonical(_plain(raw)))

    @classmethod
    def from_json(cls, raw: str) -> VisualVerificationRouteInput:
        result = object.__new__(cls)
        result._store(_load(raw))
        return result

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> VisualVerificationRouteInput:
        return cls.from_json(canonical(_plain(raw)))

    @property
    def task_id(self) -> str:
        return str(self.to_payload()["original"]["identity"]["task_id"])

    @property
    def event_key(self) -> str:
        return str(self.to_payload()["event_key"])

    def source_key(self) -> str:
        p = self.to_payload()
        obs = p["online"]["observation"]
        o = p["original"]
        c = o["contract"]
        requirement = o["requirements"].get(p["step_id"])
        return digest(
            dict(
                schema_version="visual.verification.source-key.v1",
                task_id=self.task_id,
                original_plan_hash=digest(o),
                plan_version=c["plan_version"],
                command_seq=c["command_seq"],
                step_id=p["step_id"],
                attempt=p["attempt"],
                phase=p["phase"],
                frame_id=obs["observation_id"],
                frame_checksum=obs["checksum_sha256"],
                requirements_hash=digest(requirement),
            )
        )

    def semantic_hash(self) -> str:
        p = self.to_payload()
        return digest(
            {
                k: p[k]
                for k in (
                    "original",
                    "online",
                    "step_id",
                    "attempt",
                    "phase",
                    "execution_contract",
                    "completion",
                )
            }
        )

    def online(self) -> OnlineEvidenceSnapshot:
        p = self.to_payload()["online"]
        return OnlineEvidenceSnapshot(
            serialized_model(p["observation"], RGBDObservation),
            serialized_model(p["robot_state"], RobotState),
            p["visual_facts"],
            p["plan_version"],
            p["command_seq"],
            p["context_hash"],
        )


class VisualVerificationRouteRecord(_FrozenJSON):
    def __init__(self, raw: dict[str, Any]) -> None:
        fields = {
            "schema_version",
            "scope",
            "input",
            "input_hash",
            "semantic_hash",
            "source_key",
            "route",
            "reasons",
            "verdicts",
            "created_at",
            "before_verification_budget",
            "after_verification_budget",
            "produced_publication",
            "produced_publication_hash",
            "source_context_hash",
            "native_context_hash",
            "evidence_content_hash",
            "context_domains",
            "capture_claim_id",
            "camera_source_descriptor_sha256",
        }
        if (
            set(raw) != fields
            or raw["schema_version"] != "visual.verification.route.v1"
            or raw["scope"] != "SOURCE_ROUTE_ONLY"
        ):
            raise ValueError("strict source route history schema required")
        request = VisualVerificationRouteInput.from_payload(raw["input"])
        if (
            raw["input_hash"] != request.digest()
            or raw["semantic_hash"] != request.semantic_hash()
            or raw["source_key"] != request.source_key()
        ):
            raise ValueError("routing original input hash differs")
        if raw["route"] not in {"CONTINUE", "REOBSERVE", "STOP"}:
            raise ValueError("no execution/recovery route available")
        if type(raw["reasons"]) is not list or any(type(s) is not str for s in raw["reasons"]):
            raise ValueError("exact routing reasons required")
        aware(datetime.fromisoformat(raw["created_at"]))
        before, after = (
            _pool(raw["before_verification_budget"]),
            _pool(raw["after_verification_budget"]),
        )
        produced = VisualOwnerPublicationRecord.from_payload(raw["produced_publication"])
        p = request.to_payload()
        prior = VisualOwnerPublicationRecord.from_payload(p["publication"])
        original = original_from_payload(p["original"])
        if (
            raw["produced_publication_hash"] != produced.digest()
            or before.content_hash != prior.verification_budget.content_hash
            or after.content_hash != produced.verification_budget.content_hash
            or after.revision != before.revision + 1
            or produced.owner_revision != prior.owner_revision + 1
            or produced.state_generation != prior.state_generation + 1
            or canonical(produced.checkpoint.model_dump(mode="json"))
            != canonical(prior.checkpoint.model_dump(mode="json"))
            or produced.original_plan_hash != original.digest()
            or after.state.limits != before.state.limits
            or after.state.deadline_at != before.state.deadline_at
            or after.state.remaining_reobservations > before.state.remaining_reobservations
            or after.state.remaining_retries != before.state.remaining_retries
            or canonical(produced.retry_budget.model_dump(mode="json"))
            != canonical(prior.retry_budget.model_dump(mode="json"))
        ):
            raise ValueError("route/pool/publication transition differs")
        online = request.online()
        contract = serialized_model(p["execution_contract"], TaskContract)
        if (
            raw["source_context_hash"] != online.context_hash
            or raw["native_context_hash"]
            != native_action_context_hash(original.role_bundle_hash, contract, p["step_id"])
            or raw["evidence_content_hash"] != evidence_content_hash(online)
            or raw["camera_source_descriptor_sha256"]
            != camera_source_descriptor_sha256(online.observation)
            or raw["context_domains"]
            != {
                "source": "visual.checkpoint-context.v1",
                "native": "visual.native-action-context.v1",
                "evidence": "visual.verification.evidence-content.v1",
            }
        ):
            raise ValueError("separate current context domains changed")
        route, state, verdicts, reasons = _computed_route(
            request, original, before, aware(datetime.fromisoformat(raw["created_at"]))
        )
        expected_pool = replace(
            before,
            state=state,
            revision=before.revision + 1,
            updated_at=aware(datetime.fromisoformat(raw["created_at"])),
            content_hash="",
        )
        if (
            raw["route"] != route
            or raw["reasons"] != reasons
            or canonical(raw["verdicts"]) != canonical([_plain(asdict(v)) for v in verdicts])
            or canonical(after.to_payload()) != canonical(expected_pool.to_payload())
        ):
            raise ValueError("history must recompute canonical routing transition")
        claim = raw["capture_claim_id"]
        if (raw["route"] == "REOBSERVE") != (claim is not None):
            raise ValueError("capture claim iff reobservation route")
        if claim is not None and (
            claim
            != digest(
                dict(
                    schema_version="visual.verification.capture-claim.v1",
                    source_key=request.source_key(),
                )
            )
            or after.state.remaining_reobservations != before.state.remaining_reobservations - 1
        ):
            raise ValueError("capture claim/debit changed")
        if (
            claim is None
            and after.state.remaining_reobservations != before.state.remaining_reobservations
        ):
            raise ValueError("unclaimed observation debit")
        for verdict in raw["verdicts"]:
            if set(verdict) != {
                "status",
                "condition_name",
                "observation_id",
                "measured_values",
                "reasons",
            } or verdict["status"] not in {"PASS", "FAIL", "UNKNOWN"}:
                raise ValueError("canonical verdict schema required")
        object.__setattr__(self, "_json", canonical(_plain(raw)))

    @classmethod
    def from_json(cls, raw: str) -> VisualVerificationRouteRecord:
        return cls(_load(raw))

    @property
    def route(self) -> str:
        return str(self.to_payload()["route"])

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(self.to_payload()["reasons"])


class VisualVerificationRouteWriteResult:
    __slots__ = ("record", "write_disposition")

    def __init__(
        self,
        record: VisualVerificationRouteRecord,
        write_disposition: Literal["NEW_COMMIT", "HISTORICAL_DUPLICATE"],
    ) -> None:
        if type(record) is not VisualVerificationRouteRecord or write_disposition not in {
            "NEW_COMMIT",
            "HISTORICAL_DUPLICATE",
        }:
            raise ValueError("strict source write result required")
        object.__setattr__(
            self, "record", VisualVerificationRouteRecord.from_json(record.to_json())
        )
        object.__setattr__(self, "write_disposition", write_disposition)

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("immutable source write result")


def historical_duplicate(
    request: VisualVerificationRouteInput,
    stored: VisualVerificationRouteRecord,
    *,
    same_event: bool,
) -> VisualVerificationRouteWriteResult:
    p = stored.to_payload()
    if p["semantic_hash"] != request.semantic_hash() or (
        same_event and p["input_hash"] != request.digest()
    ):
        from cloud_edge_robot_arm.repositories.event_autonomy.protocol import (
            IdempotencyConflictError,
        )

        raise IdempotencyConflictError("visual verification source/key changed bytes")
    return VisualVerificationRouteWriteResult(stored, "HISTORICAL_DUPLICATE")


def _authorized_execution(
    request: VisualVerificationRouteInput,
    original: VisualOriginalPlan,
    prior: VisualOwnerPublicationRecord,
) -> bool:
    p = request.to_payload()
    contract = serialized_model(p["execution_contract"], TaskContract)
    expected = original.contract.model_dump(mode="json")
    grounding = prior.to_payload()["grounding"]
    if grounding is not None:
        binding = grounding_from_payload(grounding)
        if (
            binding.grounded_step.step_id != p["step_id"]
            or binding.original_requirements.digest()
            != original.requirements[p["step_id"]].digest()
        ):
            return False
        expected["steps"] = [
            binding.grounded_step.model_dump(mode="json") if s["step_id"] == p["step_id"] else s
            for s in expected["steps"]
        ]
    return canonical(contract.model_dump(mode="json")) == canonical(expected)


def _phase_verdicts(
    request: VisualVerificationRouteInput, original: VisualOriginalPlan, now: datetime
) -> tuple[list[ConditionVerdict], list[str]]:
    p = request.to_payload()
    phase = p["phase"]
    online = request.online()
    requirement = original.requirements[p["step_id"]]
    if phase in NATIVE_PHASES:
        contract = serialized_model(p["execution_contract"], TaskContract)
        step = next(s for s in contract.steps if s.step_id == p["step_id"])
        native_online = replace(
            online,
            context_hash=native_action_context_hash(
                original.role_bundle_hash, contract, p["step_id"]
            ),
        )
        native = native_action_contract(native_online, contract, step)
        action = ActionEvidenceContract(
            native.evidence,
            requirement.expected_duration_s,
            requirement.allowed_error_m,
            requirement.sensor_requirements,
            requirement.preconditions,
            requirement.postconditions,
            online.plan_version,
            online.command_seq,
            native_online.context_hash,
        )
        verdict = validate_evidence(
            action,
            now,
            native_online.context_hash,
            online.observation.calibration_version or "",
            online_evidence=native_online,
        )
        status = (
            ConditionStatus.PASS
            if verdict.status == "VALID"
            else ConditionStatus.UNKNOWN
            if verdict.status == "UNKNOWN"
            else ConditionStatus.FAIL
        )
        return [
            ConditionVerdict(
                status,
                "action_submit_evidence",
                online.observation.observation_id,
                reasons=verdict.reasons,
            )
        ], list(verdict.reasons)
    if phase in EFFECT_PHASES:
        completion = p["completion"]
        if completion is None:
            return [], ["effect_completion_source_unavailable"]
        result = serialized_model(completion["result"], SkillExecutionResult)
        if (
            completion["task_id"] != request.task_id
            or completion["step_id"] != p["step_id"]
            or completion["attempt"] != p["attempt"]
            or (completion["plan_version"], completion["command_seq"])
            != (online.plan_version, online.command_seq)
            or completion["source_checkpoint_hash"] != online.context_hash
            or completion["execution_payload_hash"] != digest(p["execution_contract"])
            or result.task_id != request.task_id
            or result.step_id != p["step_id"]
            or result.skill != requirement.original_step.skill
            or completion["plan_id"] != original.identity.plan_id
            or completion["robot_id"] != original.identity.robot_id
            or result.scene_version != original.contract.scene_version
            or not original.registered_at
            <= aware(datetime.fromisoformat(completion["started_at"]))
            <= result.timestamp
            <= aware(datetime.fromisoformat(completion["returned_at"]))
            or result.plan_version != online.plan_version
            or result.command_seq != online.command_seq
            or completion["before_observation_id"] == online.observation.observation_id
            or not aware(datetime.fromisoformat(completion["returned_at"]))
            < online.observation.captured_at
            <= now
            or any(
                original.source_hashes.get(k) != v for k, v in completion["source_hashes"].items()
            )
        ):
            return [], ["effect_completion_source_binding_changed"]
        if not result.success:
            return [], ["effect_execution_failed"]
        names = {c.name for c in requirement.postconditions}
        if phase == "POST_HOLD" and not {"object_held", "object_lifted", "object_stable"} <= names:
            return [], ["phase_full_requirements_unregistered"]
        if phase == "TERMINAL" and (
            p["step_id"] != original.contract.steps[-1].step_id
            or not set(original.contract.completion_criteria) <= names
        ):
            return [], ["phase_full_requirements_unregistered"]
        return evaluate_conditions(requirement.postconditions, online, now=now), []
    return evaluate_conditions(requirement.preconditions, online, now=now), []


def _route_state(
    verdicts: list[ConditionVerdict], state: VerificationBudgetState, namespace: str, phase: str
) -> str:
    if state.exhausted_reason:
        return "STOP"
    current = {}
    for index, verdict in enumerate(verdicts):
        residual = verdict.measured_values.get("residual_m")
        if (
            not isinstance(residual, (int, float))
            or isinstance(residual, bool)
            or residual < 0
            or not math.isfinite(residual)
            or verdict.measured_values.get("source") != "rgbd_estimate"
        ):
            residual = None
        key = namespace + f":{index}:" + verdict.condition_name
        current[key] = (str(verdict.status), residual)
    all_pass = bool(verdicts) and all(v.status == ConditionStatus.PASS for v in verdicts)
    progress = False
    for key, (status, residual) in current.items():
        previous = state.previous_conditions.get(key)
        if previous:
            old, old_residual = previous
            progress |= (
                (old == "UNKNOWN" and status in {"FAIL", "PASS"})
                or (old == "FAIL" and status == "PASS")
                or (
                    status != "UNKNOWN"
                    and residual is not None
                    and old_residual is not None
                    and residual < old_residual - 1e-6
                )
            )
    if state.verification_rounds > 0 and not all_pass:
        state.consecutive_no_progress = 0 if progress else state.consecutive_no_progress + 1
    state.verification_rounds += 1
    rank = {"UNKNOWN": 0, "FAIL": 1, "PASS": 2}
    for key, (status, residual) in current.items():
        old, old_residual = state.previous_conditions.get(key, ("UNKNOWN", None))
        candidates = [v for v in (old_residual, residual) if v is not None]
        state.previous_conditions[key] = (
            status if rank[status] > rank[old] else old,
            min(candidates) if candidates else None,
        )
    if state.consecutive_no_progress >= state.limits.max_no_progress:
        state.exhausted_reason = "no_progress_exhausted"
        return "STOP"
    if all_pass:
        return "CONTINUE"
    if phase == "NATIVE_PRE_SKILL":
        state.exhausted_reason = "post_safety_evidence_invalidated"
        return "STOP"
    if not verdicts or any(v.status == ConditionStatus.UNKNOWN for v in verdicts):
        if state.remaining_reobservations > 0:
            state.remaining_reobservations -= 1
            return "REOBSERVE"
        state.exhausted_reason = "reobservation_unavailable_or_exhausted"
        return "STOP"
    state.exhausted_reason = "recovery_unavailable_or_exhausted"
    return "STOP"


def _computed_route(
    request: VisualVerificationRouteInput,
    original: VisualOriginalPlan,
    pool: VerificationBudgetRecord,
    now: datetime,
) -> tuple[str, VerificationBudgetState, list[ConditionVerdict], list[str]]:
    p, online = request.to_payload(), request.online()
    requirement = original.requirements[p["step_id"]]
    state = copy_budget(pool.state)
    verdicts: list[ConditionVerdict] = []
    reasons: list[str] = []
    if (
        online.robot_state.estop_engaged
        or online.robot_state.collision_detected
        or not online.robot_state.connected
    ):
        route = "STOP"
        state.exhausted_reason = state.exhausted_reason or "hard_safety_fault"
        reasons = ["hard_safety_fault"]
    elif now >= min(state.deadline_at, original.effective_deadline_at):
        route = "STOP"
        state.exhausted_reason = state.exhausted_reason or "deadline_exhausted"
        reasons = ["deadline_exhausted"]
    elif (now - online.observation.captured_at).total_seconds() > requirement.ordinary_ttl_s:
        route = "STOP"
        state.exhausted_reason = state.exhausted_reason or "frame_ttl_expired"
        reasons = ["frame_ttl_expired"]
    elif state.exhausted_reason:
        route = "STOP"
        reasons = [state.exhausted_reason]
    else:
        verdicts, reasons = _phase_verdicts(request, original, now)
        if reasons and p["phase"] in EFFECT_PHASES:
            route = "STOP"
            state.exhausted_reason = reasons[0]
        else:
            namespace = digest(
                dict(
                    schema_version="visual.verification.progress-context.v1",
                    original_plan_hash=original.digest(),
                    step_id=p["step_id"],
                    attempt=p["attempt"],
                    phase=p["phase"],
                    requirements=requirement.to_payload(),
                )
            )
            route = _route_state(verdicts, state, namespace, p["phase"])
            if state.exhausted_reason:
                reasons.append(state.exhausted_reason)
    return route, state, verdicts, list(dict.fromkeys(reasons))


def derive_route(
    request: VisualVerificationRouteInput,
    original: VisualOriginalPlan,
    prior: VisualOwnerPublicationRecord,
    ancestor: VisualOwnerPublicationRecord | None,
    active: ActiveTaskContractRecord | None,
    checkpoint: ExecutionCheckpoint | None,
    pool: VerificationBudgetRecord | None,
    retry: RecoveryBudget | None,
    *,
    cancelled: bool,
    now: datetime,
) -> (
    tuple[VisualVerificationRouteRecord, VerificationBudgetRecord, VisualOwnerPublicationRecord]
    | None
):
    """Transaction-current pure source producer; does not authorize capture or movement."""
    now = aware(now)
    if not current_models_exact(active, checkpoint, retry):
        return None
    p = request.to_payload()
    online = request.online()
    if (
        cancelled
        or original.digest() != digest(p["original"])
        or prior.digest()
        != digest({k: v for k, v in p["publication"].items() if k != "publication_hash"})
        or not current_publication(
            prior, original, active, checkpoint, pool, retry, previous=ancestor
        )
        or checkpoint is None
        or pool is None
        or retry is None
        or p["step_id"] != checkpoint.current_step_id
        or p["step_id"] not in original.requirements
        or p["step_id"] in checkpoint.completed_step_ids
        or p["attempt"] > original.requirements[p["step_id"]].original_step.retry_limit + 1
        or (online.plan_version, online.command_seq)
        != (checkpoint.plan_version, checkpoint.command_seq)
        or online.context_hash != checkpoint.checkpoint_hash
        or online.observation.episode_id != original.identity.episode_id
        or online.observation.captured_at > now
        or checkpoint.updated_at > now
        or not online.observation.calibration_version
        or not _authorized_execution(request, original, prior)
    ):
        return None
    requirement = original.requirements[p["step_id"]]
    descriptor = camera_source_descriptor_sha256(online.observation)
    for spec in (*requirement.preconditions, *requirement.postconditions):
        expected = spec.tolerances.get("camera_source_descriptor_sha256")
        if expected is not None and (sha(expected) != descriptor):
            return None
        calibration = spec.tolerances.get("calibration_version")
        if calibration is not None and calibration != online.observation.calibration_version:
            return None
    grounding = prior.to_payload()["grounding"]
    if (
        grounding is not None
        and grounding["calibration_version"] != online.observation.calibration_version
    ):
        return None
    route, state, verdicts, reasons = _computed_route(request, original, pool, now)
    next_pool = replace(
        pool, state=state, revision=pool.revision + 1, updated_at=now, content_hash=""
    )
    key = operation_hash(
        task_id=request.task_id,
        owner_epoch=prior.identity.owner_epoch,
        expected_owner_revision=prior.owner_revision,
        expected_contract_hash=prior.to_payload()["contract_hash"],
        expected_checkpoint_hash=checkpoint.checkpoint_hash,
        checkpoint=checkpoint,
        grounding=None,
        state_generation=prior.state_generation + 1,
    )
    produced = publication(
        original,
        checkpoint,
        next_pool,
        retry,
        revision=prior.owner_revision + 1,
        generation=prior.state_generation + 1,
        source_revision=prior.owner_revision,
        operation_hash=key,
        grounding=None,
    )
    record = VisualVerificationRouteRecord(
        dict(
            schema_version="visual.verification.route.v1",
            scope="SOURCE_ROUTE_ONLY",
            input=p,
            input_hash=request.digest(),
            semantic_hash=request.semantic_hash(),
            source_key=request.source_key(),
            route=route,
            reasons=list(dict.fromkeys(reasons)),
            verdicts=[_plain(asdict(v)) for v in verdicts],
            created_at=now.isoformat(),
            before_verification_budget=pool.to_payload(),
            after_verification_budget=next_pool.to_payload(),
            produced_publication=produced.to_payload(),
            produced_publication_hash=produced.digest(),
            source_context_hash=online.context_hash,
            native_context_hash=native_action_context_hash(
                original.role_bundle_hash,
                serialized_model(p["execution_contract"], TaskContract),
                p["step_id"],
            ),
            evidence_content_hash=evidence_content_hash(online),
            context_domains={
                "source": "visual.checkpoint-context.v1",
                "native": "visual.native-action-context.v1",
                "evidence": "visual.verification.evidence-content.v1",
            },
            capture_claim_id=digest(
                dict(
                    schema_version="visual.verification.capture-claim.v1",
                    source_key=request.source_key(),
                )
            )
            if route == "REOBSERVE"
            else None,
            camera_source_descriptor_sha256=descriptor,
        )
    )
    return record, next_pool, produced
