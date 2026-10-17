"""Initial capture/planning source history, never native or execution authority.

Pure producers for the existing event repository. Effects occur in the worker,
which must recheck live lease/backend/role/hard-stop sources at every boundary.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, ClassVar, Literal, cast

from pydantic import BaseModel

from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
from cloud_edge_robot_arm.contracts.models import (
    FailurePolicy,
    RecoveryBudget,
    RobotState,
    SafetyConstraints,
    TaskContract,
    TaskStep,
    TaskTarget,
)
from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
from cloud_edge_robot_arm.edge.recovery.verification_router import (
    VerificationBudget,
    VerificationBudgetState,
)
from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import (
    aware,
    canonical,
    counter,
    digest,
    original_from_payload,
    serialized_model,
    sha,
    strict_retry,
)
from cloud_edge_robot_arm.vision.observations import RGBDObservation
from cloud_edge_robot_arm.vision.owner_registration import (
    OriginalActionRequirements,
    VisualOriginalPlan,
    _sources,
    freeze_original_visual_plan,
)
from cloud_edge_robot_arm.vision.worker_owner import (
    WorkerLeaseObservation,
    _identity_string,
    compile_worker_original_plan,
)

BOOTSTRAP_SOURCE_PATH = "src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py"

KINDS = frozenset(
    {
        "RESERVE_INITIAL_CAPTURE",
        "COMPLETE_CAPTURE",
        "RESERVE_PLAN",
        "COMPLETE_PLAN",
        "RESERVE_REOBSERVATION",
        "STOP",
    }
)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ValueError("strict string source keys required")
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if isinstance(value, datetime):
        return aware(value).isoformat()
    if value is None or type(value) in (str, bool):
        return value
    if type(value) is int and abs(value) <= 2**63 - 1:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("finite bounded strict JSON source required")


def _load(raw: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate source JSON keys")
            result[key] = value
        return result

    def bad(value: str) -> None:
        raise ValueError(f"nonfinite JSON token {value}")

    if type(raw) is not str:
        raise ValueError("strict source JSON string required")
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)
    if type(result) is not dict:
        raise ValueError("complete JSON source envelope required")
    return cast(dict[str, Any], _plain(result))


def _model[Model: BaseModel](value: Model, model: type[Model]) -> dict[str, Any]:
    if type(value) is not model or set(vars(value)) - set(model.model_fields):
        raise ValueError("concrete complete source model required")
    raw = _plain(value.model_dump(mode="json"))
    checked = serialized_model(raw, model)
    return checked.model_dump(mode="json")


def _lease(raw: dict[str, Any]) -> WorkerLeaseObservation:
    body = dict(_plain(raw))
    if body.pop("scope", None) != "WORKER_LEASE_SOURCE_ONLY":
        raise ValueError("fixed worker lease source scope required")
    for name in ("acquired_at", "observed_at", "expires_at"):
        body[name] = aware(datetime.fromisoformat(body[name]))
    result = WorkerLeaseObservation(**body)
    if canonical(result.to_payload()) != canonical(raw):
        raise ValueError("lease source types or values changed")
    return result


def _lease_key(lease: WorkerLeaseObservation) -> tuple[Any, ...]:
    return lease.job_id, lease.run_id, lease.worker_id, lease.lease_id, lease.attempt


def _state(raw: dict[str, Any]) -> VerificationBudgetState:
    if set(raw) != set(VerificationBudgetState.__dataclass_fields__):
        raise ValueError("complete verification state required")
    for key in (
        "remaining_reobservations",
        "remaining_retries",
        "consecutive_no_progress",
        "verification_rounds",
    ):
        counter(raw[key])
    limits = VerificationBudget(**raw["limits"])
    history = raw["previous_conditions"]
    if type(history) is not dict:
        raise ValueError("strict previous condition map required")
    previous = {}
    for name, pair in history.items():
        _identity_string(name)
        if type(pair) is not list or len(pair) != 2 or pair[0] not in {"UNKNOWN", "FAIL", "PASS"}:
            raise ValueError("strict previous condition source required")
        if pair[1] is not None and (type(pair[1]) not in (int, float) or pair[1] < 0):
            raise ValueError("nonnegative finite condition residual required")
        previous[name] = (pair[0], pair[1])
    if raw["exhausted_reason"] is not None and type(raw["exhausted_reason"]) is not str:
        raise ValueError("strict exhaustion reason required")
    return VerificationBudgetState(
        raw["remaining_reobservations"],
        raw["remaining_retries"],
        raw["consecutive_no_progress"],
        aware(datetime.fromisoformat(raw["deadline_at"])),
        limits,
        previous,
        raw["exhausted_reason"],
        raw["verification_rounds"],
    )


@dataclass(frozen=True)
class VisualBootstrapDefinition:
    lease: WorkerLeaseObservation
    episode_id: str
    user_instruction: str
    task_started_at: datetime
    task_timeout_s: float
    verification_limits: VerificationBudget
    role_bundle_hash: str
    model_snapshot_hash: str
    source_hashes: Mapping[str, str]
    registered_at: datetime
    scope: ClassVar[str] = "BOOTSTRAP_SOURCE_ONLY"

    def __post_init__(self) -> None:
        if (
            type(self.lease) is not WorkerLeaseObservation
            or type(self.verification_limits) is not VerificationBudget
        ):
            raise ValueError("concrete bootstrap lease and original limits required")
        object.__setattr__(self, "lease", _lease(self.lease.to_payload()))
        object.__setattr__(
            self, "verification_limits", VerificationBudget(**asdict(self.verification_limits))
        )
        _identity_string(self.episode_id)
        if type(self.user_instruction) is not str or not self.user_instruction.strip():
            raise ValueError("original instruction required")
        if (
            type(self.task_timeout_s) not in (float, int)
            or not math.isfinite(self.task_timeout_s)
            or self.task_timeout_s <= 0
        ):
            raise ValueError("finite positive original task timeout required")
        if (
            not self.lease.acquired_at
            <= aware(self.task_started_at)
            <= self.lease.observed_at
            <= aware(self.registered_at)
            < self.lease.expires_at
        ):
            raise ValueError("bootstrap source/task/registration clock order invalid")
        # Deadline arithmetic is bounded separately from JSON encoding.
        try:
            task_deadline = self.task_deadline_at
            verification_deadline = self.verification_deadline_at
        except OverflowError as error:
            raise ValueError("original bootstrap deadline exceeds clock range") from error
        if self.registered_at >= min(task_deadline, verification_deadline):
            raise ValueError("bootstrap registration deadline already expired")
        sha(self.role_bundle_hash)
        sha(self.model_snapshot_hash)
        object.__setattr__(self, "source_hashes", _sources(self.source_hashes))
        _plain(self.to_payload())

    @property
    def task_deadline_at(self) -> datetime:
        return self.task_started_at + timedelta(seconds=self.task_timeout_s)

    @property
    def verification_deadline_at(self) -> datetime:
        return min(
            self.task_deadline_at,
            self.task_started_at + timedelta(seconds=self.verification_limits.deadline_s),
        )

    @property
    def bootstrap_id(self) -> str:
        return digest(["visual.bootstrap.job-run.v1", self.lease.job_id, self.lease.run_id])

    def to_payload(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            _plain(
                dict(
                    schema_version="visual.bootstrap.definition.v1",
                    scope=self.scope,
                    lease=self.lease.to_payload(),
                    episode_id=self.episode_id,
                    user_instruction=self.user_instruction,
                    task_started_at=self.task_started_at,
                    task_timeout_s=self.task_timeout_s,
                    verification_limits=asdict(self.verification_limits),
                    role_bundle_hash=self.role_bundle_hash,
                    model_snapshot_hash=self.model_snapshot_hash,
                    source_hashes=dict(self.source_hashes),
                    registered_at=self.registered_at,
                )
            ),
        )

    def digest(self) -> str:
        return digest(self.to_payload())

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> VisualBootstrapDefinition:
        body = dict(_plain(raw))
        if (
            body.pop("schema_version", None) != "visual.bootstrap.definition.v1"
            or body.pop("scope", None) != cls.scope
        ):
            raise ValueError("fixed bootstrap definition schema/scope required")
        body["lease"] = _lease(body["lease"])
        body["verification_limits"] = VerificationBudget(**body["verification_limits"])
        for name in ("task_started_at", "registered_at"):
            body[name] = aware(datetime.fromisoformat(body[name]))
        result = cls(**body)
        if canonical(result.to_payload()) != canonical(raw):
            raise ValueError("bootstrap definition changed during decoding")
        return result


class _FrozenJSON:
    __slots__ = ("_json",)
    _json: str
    scope: ClassVar[str] = "BOOTSTRAP_SOURCE_ONLY"

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("immutable detached bootstrap source")

    def to_payload(self) -> dict[str, Any]:
        return _load(self._json)

    def to_json(self) -> str:
        return self._json

    def digest(self) -> str:
        return hashlib.sha256(self._json.encode()).hexdigest()


class VisualBootstrapRecord(_FrozenJSON):
    @classmethod
    def _make(cls, body: dict[str, Any]) -> VisualBootstrapRecord:
        result = object.__new__(cls)
        object.__setattr__(result, "_json", canonical(_plain(body)))
        return result

    @classmethod
    def start(cls, definition: VisualBootstrapDefinition) -> VisualBootstrapRecord:
        if type(definition) is not VisualBootstrapDefinition:
            raise ValueError("concrete original bootstrap definition required")
        definition = VisualBootstrapDefinition.from_payload(definition.to_payload())
        state = VerificationBudgetState.start(
            definition.verification_limits, now=definition.task_started_at
        )
        state.deadline_at = definition.verification_deadline_at
        return cls._make(
            dict(
                schema_version="visual.bootstrap.record.v1",
                scope=cls.scope,
                definition=definition.to_payload(),
                revision=0,
                updated_at=definition.registered_at,
                state=asdict(state),
                initial_capture_claimed=False,
                pending=None,
                observation=None,
                camera_descriptor_hash=None,
                draft=None,
                planning_source_usable=False,
                proposal_hash=None,
                terminal_reason=None,
                adopted_original_hash=None,
                history=[],
            )
        )

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> VisualBootstrapRecord:
        raw = cast(dict[str, Any], _plain(raw))
        if (
            raw.get("schema_version") != "visual.bootstrap.record.v1"
            or raw.get("scope") != cls.scope
        ):
            raise ValueError("fixed bootstrap record schema/scope required")
        definition = VisualBootstrapDefinition.from_payload(raw["definition"])
        _state(raw["state"])
        counter(raw["revision"])
        if (
            type(raw["history"]) is not list
            or len(raw["history"]) > 4 * (definition.verification_limits.max_reobservations + 1) + 2
        ):
            raise ValueError("complete bounded bootstrap transition history required")
        record = cls.start(definition)
        for event in raw["history"]:
            if set(event) == {"promotion", "state", "retry", "committed_at"}:
                record = _promote(
                    record,
                    VisualBootstrapPromotionInput.from_payload(event["promotion"]),
                    _state(event["state"]),
                    serialized_model(event["retry"], RecoveryBudget),
                    now=aware(datetime.fromisoformat(event["committed_at"])),
                )
                continue
            if set(event) != {"request", "committed_at"}:
                raise ValueError("complete original bootstrap history event required")
            request = VisualBootstrapTransitionInput.from_payload(event["request"])
            record = _derive(
                record, request, now=aware(datetime.fromisoformat(event["committed_at"]))
            )
        if canonical(record.to_payload()) != canonical(raw):
            raise ValueError("bootstrap history does not reproduce exact record state")
        return record

    @classmethod
    def from_json(cls, raw: str) -> VisualBootstrapRecord:
        return cls.from_payload(_load(raw))

    @property
    def definition(self) -> VisualBootstrapDefinition:
        return VisualBootstrapDefinition.from_payload(self.to_payload()["definition"])

    @property
    def revision(self) -> int:
        return cast(int, self.to_payload()["revision"])

    @property
    def verification_state(self) -> VerificationBudgetState:
        return _state(self.to_payload()["state"])

    @property
    def task_deadline_at(self) -> datetime:
        return self.definition.task_deadline_at

    @property
    def pending_claim_id(self) -> str | None:
        pending = self.to_payload()["pending"]
        return cast(str, pending["claim_id"]) if pending is not None else None

    @property
    def terminal_reason(self) -> str | None:
        return cast(str | None, self.to_payload()["terminal_reason"])

    @property
    def observation(self) -> RGBDObservation | None:
        raw = self.to_payload()["observation"]
        return serialized_model(raw, RGBDObservation) if raw is not None else None

    @property
    def draft(self) -> PlannerDraft | None:
        raw = self.to_payload()["draft"]
        return serialized_model(raw, PlannerDraft) if raw is not None else None

    @property
    def planning_source_usable(self) -> bool:
        return cast(bool, self.to_payload()["planning_source_usable"])

    @property
    def proposal_hash(self) -> str | None:
        return cast(str | None, self.to_payload()["proposal_hash"])


class VisualBootstrapTransitionInput(_FrozenJSON):
    def __init__(
        self,
        *,
        record: VisualBootstrapRecord,
        kind: str,
        event_key: str,
        current_lease: WorkerLeaseObservation,
        robot_state: RobotState,
        claim_id: str | None = None,
        observation: RGBDObservation | None = None,
        draft: PlannerDraft | None = None,
    ) -> None:
        if (
            type(record) is not VisualBootstrapRecord
            or type(current_lease) is not WorkerLeaseObservation
        ):
            raise ValueError("concrete current bootstrap and lease source required")
        record = VisualBootstrapRecord.from_json(record.to_json())
        body = dict(
            schema_version="visual.bootstrap.transition.v1",
            scope=self.scope,
            bootstrap_id=record.definition.bootstrap_id,
            definition_hash=record.definition.digest(),
            expected_record_hash=record.digest(),
            kind=kind,
            event_key=event_key,
            current_lease=current_lease.to_payload(),
            robot_state=_model(robot_state, RobotState),
            claim_id=claim_id,
            observation=_model(observation, RGBDObservation) if observation is not None else None,
            draft=_model(draft, PlannerDraft) if draft is not None else None,
        )
        checked = self.from_payload(body)
        object.__setattr__(self, "_json", checked.to_json())

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> VisualBootstrapTransitionInput:
        raw = cast(dict[str, Any], _plain(raw))
        if set(raw) != {
            "schema_version",
            "scope",
            "bootstrap_id",
            "definition_hash",
            "expected_record_hash",
            "kind",
            "event_key",
            "current_lease",
            "robot_state",
            "claim_id",
            "observation",
            "draft",
        }:
            raise ValueError("complete bootstrap transition source required")
        if (
            raw["schema_version"] != "visual.bootstrap.transition.v1"
            or raw["scope"] != cls.scope
            or raw["kind"] not in KINDS
        ):
            raise ValueError("declared bootstrap source phase required")
        for name in ("bootstrap_id", "definition_hash", "expected_record_hash"):
            sha(raw[name])
        _identity_string(raw["event_key"])
        _lease(raw["current_lease"])
        serialized_model(raw["robot_state"], RobotState)
        if raw["claim_id"] is not None:
            sha(raw["claim_id"])
        if raw["observation"] is not None:
            serialized_model(raw["observation"], RGBDObservation)
        if raw["draft"] is not None:
            serialized_model(raw["draft"], PlannerDraft)
        kind = raw["kind"]
        if (kind == "COMPLETE_CAPTURE") != (raw["observation"] is not None) or (
            kind == "COMPLETE_PLAN"
        ) != (raw["draft"] is not None):
            raise ValueError("exact phase-specific completion source required")
        if (kind in {"COMPLETE_CAPTURE", "COMPLETE_PLAN"}) != (raw["claim_id"] is not None):
            raise ValueError("exact completed claim source required")
        result = object.__new__(cls)
        object.__setattr__(result, "_json", canonical(raw))
        return result


def _camera_hash(observation: dict[str, Any]) -> str:
    return digest(
        dict(
            schema_version="visual.rgbd.camera-source-descriptor.v1",
            **{
                name: observation[name]
                for name in (
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


def _proposal_usable(
    draft: dict[str, Any], definition: VisualBootstrapDefinition, now: datetime
) -> bool:
    proposal = draft["parsed_json"]
    if (
        draft["parse_error"] is not None
        or not isinstance(proposal, dict)
        or not proposal
        or "_sentinel" in proposal
    ):
        return False
    try:
        # Identity filling must not erase malformed values in the original
        # adapter receipt. The adapter declares integer zero/empty string
        # placeholders; complete typed proposals may already contain values.
        if type(proposal.get("task_id")) is not str:
            return False
        for name in ("plan_version", "command_seq"):
            counter(proposal.get(name))
        for name in ("timestamp", "issued_at", "valid_until"):
            value = proposal.get(name)
            if type(value) is not str:
                return False
            if value:
                aware(datetime.fromisoformat(value))
        # Only the adapter's declared identity/clock placeholders are supplied.
        # This source check never grounds parameters or certifies conditions.
        payload = {
            **proposal,
            "task_id": definition.episode_id,
            "plan_version": 1,
            "command_seq": 1,
            "timestamp": now.isoformat(),
            "issued_at": now.isoformat(),
            "valid_until": min(
                definition.task_deadline_at, definition.verification_deadline_at
            ).isoformat(),
        }
        if set(payload) - set(TaskContract.model_fields):
            return False
        for name, model in (
            ("task_target", TaskTarget),
            ("safety_constraints", SafetyConstraints),
            ("failure_policy", FailurePolicy),
        ):
            if not isinstance(payload.get(name), dict) or set(payload[name]) - set(
                model.model_fields
            ):
                return False
        if not isinstance(payload.get("steps"), list) or any(
            not isinstance(step, dict) or set(step) - set(TaskStep.model_fields)
            for step in payload["steps"]
        ):
            return False
        # This is the schema-owned adapter proposal, not a stored full model.
        # Allow declared defaults and datetime wire normalization only here;
        # strict JSON mode rejects coercion of counters/bools/enum semantics.
        TaskContract.model_validate_json(canonical(payload), strict=True)
        if payload["user_instruction"] != definition.user_instruction:
            return False
    except (ValueError, TypeError, KeyError):
        return False
    return True


def _derive(
    record: VisualBootstrapRecord, request: VisualBootstrapTransitionInput, *, now: datetime
) -> VisualBootstrapRecord:
    body, raw = record.to_payload(), request.to_payload()
    definition = record.definition
    now = aware(now)
    if (
        raw["bootstrap_id"] != definition.bootstrap_id
        or raw["definition_hash"] != definition.digest()
        or raw["expected_record_hash"] != record.digest()
    ):
        raise ValueError("bootstrap current source/CAS mismatch")
    if now < aware(datetime.fromisoformat(body["updated_at"])):
        raise ValueError("bootstrap transaction clock rollback")
    if body["terminal_reason"] is not None:
        raise ValueError("bootstrap already terminal; no replay or refill")
    lease = _lease(raw["current_lease"])
    if _lease_key(lease) != _lease_key(definition.lease) or lease.observed_at > now:
        raise ValueError("bootstrap current job/run/attempt/lease source mismatch")
    state = record.verification_state
    kind, pending = raw["kind"], body["pending"]
    robot = serialized_model(raw["robot_state"], RobotState)
    reason = (
        "hard_safety_fault"
        if robot.estop_engaged or robot.collision_detected or not robot.connected
        else "deadline_exhausted"
        if now >= min(definition.task_deadline_at, state.deadline_at)
        else "worker_lease_expired"
        if now >= lease.expires_at
        else "bootstrap_stopped"
        if kind == "STOP"
        else None
    )
    if reason is not None:
        body["terminal_reason"] = state.exhausted_reason = reason
        # Any existing claim remains in history and is never refunded/replayed.
        body["pending"] = None
    elif kind.startswith("RESERVE_"):
        if pending is not None:
            raise ValueError("pending effect claim cannot be replayed or refunded")
        if kind == "RESERVE_INITIAL_CAPTURE":
            if body["initial_capture_claimed"]:
                raise ValueError("initial capture already claimed")
            body["initial_capture_claimed"] = True
            effect = "CAPTURE"
        elif kind == "RESERVE_PLAN":
            if body["observation"] is None or body["draft"] is not None:
                raise ValueError("one planning request per newly completed capture required")
            effect = "PLAN"
        else:
            if body["draft"] is None or body["planning_source_usable"]:
                raise ValueError("completed unusable planning source required for reobservation")
            if state.remaining_reobservations == 0:
                body["terminal_reason"] = state.exhausted_reason = "reobservation_exhausted"
                effect = None
            elif (
                state.verification_rounds > 0
                and state.consecutive_no_progress + 1 >= state.limits.max_no_progress
            ):
                body["terminal_reason"] = state.exhausted_reason = "no_progress_exhausted"
                effect = None
            elif state.limits.max_no_progress == 0:
                body["terminal_reason"] = state.exhausted_reason = "no_progress_exhausted"
                effect = None
            else:
                state.remaining_reobservations -= 1
                if state.verification_rounds > 0:
                    state.consecutive_no_progress += 1
                state.verification_rounds += 1
                state.previous_conditions["bootstrap_plan_source"] = ("UNKNOWN", None)
                effect = "CAPTURE"
        if effect is not None:
            body["pending"] = dict(
                claim_id=digest([definition.bootstrap_id, record.digest(), kind]),
                effect=effect,
                claimed_at=now.isoformat(),
            )
    elif kind == "COMPLETE_CAPTURE":
        if (
            pending is None
            or pending["effect"] != "CAPTURE"
            or pending["claim_id"] != raw["claim_id"]
        ):
            raise ValueError("capture completion must bind exact current claim")
        observation = serialized_model(raw["observation"], RGBDObservation)
        captured_at = aware(observation.captured_at)
        if (
            observation.episode_id != definition.episode_id
            or not observation.calibration_version
            or not aware(datetime.fromisoformat(pending["claimed_at"])) <= captured_at <= now
        ):
            raise ValueError("registered capture episode/calibration/claim clock mismatch")
        previous = body["observation"]
        camera_hash = _camera_hash(raw["observation"])
        if previous is not None and (
            observation.frame_id == previous["frame_id"]
            or captured_at <= datetime.fromisoformat(previous["captured_at"])
            or camera_hash != body["camera_descriptor_hash"]
        ):
            raise ValueError("new capture/frame/calibration camera source required")
        body.update(
            observation=raw["observation"],
            camera_descriptor_hash=camera_hash,
            draft=None,
            planning_source_usable=False,
            proposal_hash=None,
            pending=None,
        )
    elif kind == "COMPLETE_PLAN":
        if pending is None or pending["effect"] != "PLAN" or pending["claim_id"] != raw["claim_id"]:
            raise ValueError("planning completion must bind exact current claim")
        observation = serialized_model(body["observation"], RGBDObservation)
        draft = raw["draft"]
        evidence = draft["observation_evidence"]
        if (
            any(
                canonical(evidence.get(key)) != canonical(value)
                for key, value in observation.evidence().items()
            )
            or evidence.get("model_snapshot_hash") != definition.model_snapshot_hash
            or evidence.get("role_bundle_hash") != definition.role_bundle_hash
        ):
            raise ValueError("planning receipt/frame/model/role source mismatch")
        usable = _proposal_usable(draft, definition, now)
        body.update(
            draft=draft,
            planning_source_usable=usable,
            proposal_hash=bootstrap_proposal_hash(draft["parsed_json"]) if usable else None,
            pending=None,
        )
    else:
        raise ValueError("unsupported bootstrap source transition")
    body["state"] = _plain(asdict(state))
    body["revision"] += 1
    body["updated_at"] = now.isoformat()
    body["history"].append(dict(request=raw, committed_at=now.isoformat()))
    return VisualBootstrapRecord._make(body)


@dataclass(frozen=True)
class VisualBootstrapTransitionResult:
    record: VisualBootstrapRecord
    write_disposition: Literal["NEW_COMMIT", "HISTORICAL_DUPLICATE"]
    scope: ClassVar[str] = "BOOTSTRAP_SOURCE_ONLY"


def derive_bootstrap(
    record: VisualBootstrapRecord,
    request: VisualBootstrapTransitionInput,
    *,
    now: datetime,
) -> VisualBootstrapTransitionResult:
    if (
        type(record) is not VisualBootstrapRecord
        or type(request) is not VisualBootstrapTransitionInput
    ):
        raise ValueError("concrete frozen bootstrap transition sources required")
    record = VisualBootstrapRecord.from_json(record.to_json())
    request = VisualBootstrapTransitionInput.from_payload(request.to_payload())
    for event in record.to_payload()["history"]:
        if (
            "request" in event
            and event["request"]["event_key"] == request.to_payload()["event_key"]
        ):
            if canonical(event["request"]) != request.to_json():
                raise ValueError("bootstrap event key changed original source")
            return VisualBootstrapTransitionResult(record, "HISTORICAL_DUPLICATE")
    return VisualBootstrapTransitionResult(_derive(record, request, now=now), "NEW_COMMIT")


def bootstrap_proposal_hash(proposal: Mapping[str, Any]) -> str:
    """Hash the complete adapter semantic proposal before identity filling."""
    if not isinstance(proposal, Mapping):
        raise ValueError("complete semantic proposal map required")
    return digest(_plain(proposal))


def bootstrap_contract(record: VisualBootstrapRecord, *, issued_at: datetime) -> TaskContract:
    record = VisualBootstrapRecord.from_json(record.to_json())
    definition, body = record.definition, record.to_payload()
    issued_at = aware(issued_at)
    if (
        not record.planning_source_usable
        or record.pending_claim_id is not None
        or record.terminal_reason is not None
        or issued_at < datetime.fromisoformat(body["updated_at"])
        or issued_at >= min(record.task_deadline_at, record.verification_state.deadline_at)
        or not _proposal_usable(body["draft"], definition, issued_at)
    ):
        raise ValueError("completed current usable planning source required")
    payload = dict(body["draft"]["parsed_json"])
    payload.update(
        task_id=definition.episode_id,
        plan_version=1,
        command_seq=1,
        timestamp=issued_at.isoformat(),
        issued_at=issued_at.isoformat(),
        valid_until=min(record.task_deadline_at, record.verification_state.deadline_at).isoformat(),
    )
    # Only the adapter's explicitly declared simulation identities are bound.
    # All skills, parameters, conditions, durations and safety limits survive.
    aliases = {"visual_target": "object", "visual_destination": "target_region"}
    target = payload["task_target"]
    for name in ("object_id", "target_region_id"):
        if target.get(name) in aliases:
            target[name] = aliases[target[name]]
    for step in payload["steps"]:
        for name in ("object_id", "region_id"):
            value = step.get("parameters", {}).get(name)
            if type(value) is str and value in aliases:
                step["parameters"][name] = aliases[value]
    return TaskContract.model_validate_json(canonical(payload), strict=True)


def compile_bootstrap_original_plan(
    record: VisualBootstrapRecord,
    *,
    current_lease: WorkerLeaseObservation,
    plan_id: str,
    robot_id: str,
    registered_at: datetime,
) -> VisualOriginalPlan:
    """Register full original/camera consistency inputs; no execution authority."""
    record = VisualBootstrapRecord.from_json(record.to_json())
    definition = record.definition
    current_lease = _lease(current_lease.to_payload())
    if (
        _lease_key(current_lease) != _lease_key(definition.lease)
        or current_lease.acquired_at != definition.lease.acquired_at
        or BOOTSTRAP_SOURCE_PATH not in definition.source_hashes
    ):
        raise ValueError("current bootstrap lease and compiler source inventory required")
    contract = bootstrap_contract(record, issued_at=registered_at)
    observation = record.observation
    if observation is None or record.proposal_hash is None:
        raise ValueError("complete capture and proposal source required")
    original = compile_worker_original_plan(
        lease_source=current_lease,
        identity=current_lease.identity(
            episode_id=definition.episode_id,
            task_id=contract.task_id,
            plan_id=plan_id,
            robot_id=robot_id,
        ),
        contract=contract,
        observation=observation,
        proposal_hash=record.proposal_hash,
        role_bundle_hash=definition.role_bundle_hash,
        source_hashes=definition.source_hashes,
        registered_at=registered_at,
        task_deadline_at=record.task_deadline_at,
        verification_deadline_at=record.verification_state.deadline_at,
    )
    descriptor = record.to_payload()["camera_descriptor_hash"]

    def condition(source: ConditionSpec) -> ConditionSpec:
        return ConditionSpec(
            source.name,
            source.target_id,
            {**source.tolerances, "camera_source_descriptor_sha256": descriptor},
            source.sensor_requirements,
        )

    requirements = {
        name: OriginalActionRequirements(
            source.original_step,
            tuple(condition(c) for c in source.preconditions),
            tuple(condition(c) for c in source.postconditions),
            source.allowed_error_m,
            source.sensor_requirements,
            source.ordinary_ttl_s,
            source.expected_duration_s,
            source.policy_source_hashes,
        )
        for name, source in original.requirements.items()
    }
    return freeze_original_visual_plan(**{**original.freeze_inputs(), "requirements": requirements})


def bootstrap_retry_budget(
    record: VisualBootstrapRecord, original: VisualOriginalPlan, *, created_at: datetime
) -> RecoveryBudget:
    """The original, unspent retry definition; bootstrap never executes a retry."""
    state, contract = record.verification_state, original.contract
    created_at = aware(created_at)
    if state.remaining_retries != state.limits.max_retries or (
        state.limits.max_retries > contract.failure_policy.local_retry_limit
    ):
        raise ValueError("bootstrap retry state differs from original policy")
    return RecoveryBudget(
        budget_id=f"bootstrap-retry-{record.definition.bootstrap_id[:32]}",
        task_id=contract.task_id,
        per_step_retry_limit=max(step.retry_limit for step in contract.steps),
        per_skill_retry_limit=contract.failure_policy.local_retry_limit,
        task_total_retry_limit=state.limits.max_retries,
        effective_retry_limit=state.limits.max_retries,
        remaining_retries=state.remaining_retries,
        retry_deadline=original.effective_deadline_at,
        scene_version=contract.scene_version,
        created_at=created_at,
        updated_at=created_at,
    )


class VisualBootstrapPromotionInput(_FrozenJSON):
    def __init__(
        self,
        *,
        record: VisualBootstrapRecord,
        original: VisualOriginalPlan,
        event_key: str,
        current_lease: WorkerLeaseObservation,
        robot_state: RobotState,
    ) -> None:
        if type(record) is not VisualBootstrapRecord or type(original) is not VisualOriginalPlan:
            raise ValueError("concrete bootstrap and full original source required")
        checked = self.from_payload(
            dict(
                schema_version="visual.bootstrap.promotion.v1",
                scope=self.scope,
                bootstrap_id=record.definition.bootstrap_id,
                definition_hash=record.definition.digest(),
                expected_record_hash=record.digest(),
                event_key=event_key,
                original=original.to_payload(),
                current_lease=current_lease.to_payload(),
                robot_state=_model(robot_state, RobotState),
            )
        )
        object.__setattr__(self, "_json", checked.to_json())

    @classmethod
    def from_payload(cls, raw: dict[str, Any]) -> VisualBootstrapPromotionInput:
        raw = cast(dict[str, Any], _plain(raw))
        if (
            set(raw)
            != {
                "schema_version",
                "scope",
                "bootstrap_id",
                "definition_hash",
                "expected_record_hash",
                "event_key",
                "original",
                "current_lease",
                "robot_state",
            }
            or raw["schema_version"] != "visual.bootstrap.promotion.v1"
            or raw["scope"] != cls.scope
        ):
            raise ValueError("complete separate bootstrap promotion source required")
        for name in ("bootstrap_id", "definition_hash", "expected_record_hash"):
            sha(raw[name])
        _identity_string(raw["event_key"])
        original_from_payload(raw["original"])
        _lease(raw["current_lease"])
        serialized_model(raw["robot_state"], RobotState)
        result = object.__new__(cls)
        object.__setattr__(result, "_json", canonical(raw))
        return result


def _promote(
    record: VisualBootstrapRecord,
    promotion: VisualBootstrapPromotionInput,
    verification_state: VerificationBudgetState,
    retry_budget: RecoveryBudget,
    *,
    now: datetime,
) -> VisualBootstrapRecord:
    raw, body, now = promotion.to_payload(), record.to_payload(), aware(now)
    if (
        raw["bootstrap_id"] != record.definition.bootstrap_id
        or raw["definition_hash"] != record.definition.digest()
        or raw["expected_record_hash"] != record.digest()
        or record.terminal_reason is not None
        or now < datetime.fromisoformat(body["updated_at"])
    ):
        raise ValueError("current bootstrap promotion source/CAS/clock differs")
    if any(
        event.get("request", event.get("promotion", {})).get("event_key") == raw["event_key"]
        for event in body["history"]
    ):
        raise ValueError("bootstrap event key already belongs to another source")
    if (
        type(verification_state) is not VerificationBudgetState
        or type(retry_budget) is not RecoveryBudget
    ):
        raise ValueError("complete concrete original pools required")
    state = _plain(asdict(verification_state))
    _state(state)
    if canonical(state) != canonical(body["state"]):
        raise ValueError("complete spent verification state must survive promotion")
    lease, robot = _lease(raw["current_lease"]), serialized_model(raw["robot_state"], RobotState)
    if (
        robot.estop_engaged
        or robot.collision_detected
        or not robot.connected
        or lease.observed_at > now
        or now >= lease.expires_at
        or now >= min(record.task_deadline_at, record.verification_state.deadline_at)
        or record.verification_state.exhausted_reason is not None
    ):
        raise ValueError("hard stop, current clock or exhausted source prevents promotion")
    original = original_from_payload(raw["original"])
    if original.registered_at > now:
        raise ValueError("original registration after promotion clock")
    expected = compile_bootstrap_original_plan(
        record,
        current_lease=lease,
        plan_id=original.identity.plan_id,
        robot_id=original.identity.robot_id,
        registered_at=original.registered_at,
    )
    if original.digest() != expected.digest():
        raise ValueError("full original semantics/requirements/camera/source differ")
    retry = strict_retry(retry_budget)
    expected_retry = bootstrap_retry_budget(record, expected, created_at=original.registered_at)
    if canonical(retry.model_dump(mode="json")) != canonical(
        expected_retry.model_dump(mode="json")
    ):
        raise ValueError("original retry definition/counts/deadline differ")
    body.update(
        terminal_reason="original_adopted",
        adopted_original_hash=original.digest(),
        revision=record.revision + 1,
        updated_at=now.isoformat(),
    )
    body["history"].append(
        dict(
            promotion=raw,
            state=state,
            retry=retry.model_dump(mode="json"),
            committed_at=now.isoformat(),
        )
    )
    return VisualBootstrapRecord._make(body)


def promote_bootstrap(
    record: VisualBootstrapRecord,
    promotion: VisualBootstrapPromotionInput,
    verification_state: VerificationBudgetState,
    retry_budget: RecoveryBudget,
    *,
    now: datetime,
) -> VisualBootstrapRecord:
    """Pure adoption to be committed atomically with the existing owner group."""
    if (
        type(record) is not VisualBootstrapRecord
        or type(promotion) is not VisualBootstrapPromotionInput
    ):
        raise ValueError("concrete separate bootstrap promotion required")
    record = VisualBootstrapRecord.from_json(record.to_json())
    promotion = VisualBootstrapPromotionInput.from_payload(promotion.to_payload())
    for event in record.to_payload()["history"]:
        if (
            "promotion" in event
            and event["promotion"]["event_key"] == promotion.to_payload()["event_key"]
        ):
            if (
                canonical(event["promotion"]) != promotion.to_json()
                or canonical(event["state"]) != canonical(_plain(asdict(verification_state)))
                or canonical(event["retry"]) != canonical(_model(retry_budget, RecoveryBudget))
            ):
                raise ValueError("promotion event key changed original source or pools")
            return record
    return _promote(record, promotion, verification_state, retry_budget, now=now)
