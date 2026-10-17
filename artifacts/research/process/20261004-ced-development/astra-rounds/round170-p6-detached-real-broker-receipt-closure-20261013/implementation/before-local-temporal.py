"""Strict detached Stage-B histories. Serialization never grants live authority."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from math import isfinite
from typing import ClassVar, Self

from pydantic import BaseModel

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]

FIELDS: dict[str, frozenset[str]] = {
    "visual.bootstrap.definition.local.v1": frozenset("scope episode_id user_instruction task_timeout_s verification_limits role_bundle_hash model_snapshot_hash source_hashes".split()),
    "visual.bootstrap.record.local.v1": frozenset("scope definition revision state initial_capture_claimed pending observation camera_descriptor_hash draft planning_source_usable proposal_hash terminal_reason adopted_original_hash history".split()),
    "visual.bootstrap.transition.local.v1": frozenset("scope bootstrap_id definition_hash expected_record_hash kind event_key robot_state claim_id observation draft".split()),
    "visual.bootstrap.promotion.local.v1": frozenset("scope bootstrap_id definition_hash expected_record_hash event_key original robot_state".split()),
    "visual.supervision.definition.local.v1": frozenset("scope original publication task_timeout_s supervision_period_s model_snapshot_hash role_bundle job_configuration_hash".split()),
    "visual.supervision.record.local.v1": frozenset("scope definition revision max_periodic_captures max_supervisor_calls captures_reserved supervisor_calls_reserved last_capture_cursor last_wait_cursor wait_seconds_reserved claims history".split()),
    "visual.supervision.transition.local.v1": frozenset("scope task_id definition_hash expected_revision expected_record_hash original publication robot_state step_id cursor kind event_key model_snapshot_hash role_bundle claim_id observation context decision wait_duration_s wait_elapsed_s".split()),
    "visual.owner.original.local.v1": frozenset("binding_scope identity contract contract_provenance proposal_hash role_bundle_hash compiler_source_hashes source_hashes requirements dependencies".split()),
    "visual.owner.grounding.local.v1": frozenset("binding_scope original_plan_hash current_identity original_requirements owner_revision state_generation source_checkpoint_hash observation_id observation_checksum_sha256 calibration_version plan_version command_seq grounding_policy_hash grounding_inputs_hash duration_check_hash grounding_source_hashes grounded_step expected_duration_s".split()),
    "visual.owner.publication.local.v1": frozenset("binding_scope mode_scope identity original_plan_hash contract_hash owner_revision state_generation checkpoint verification_budget retry_budget grounding operation_hash source_owner_revision publication_hash".split()),
    "visual.verification.route-input.local.v1": frozenset("scope original publication online step_id attempt phase event_key execution_contract completion grounding_receipt".split()),
    "visual.verification.route.local.v1": frozenset("scope input input_hash semantic_hash source_key route reasons verdicts before_verification_budget after_verification_budget produced_publication produced_publication_hash source_context_hash native_context_hash evidence_content_hash context_domains capture_claim_id camera_source_descriptor_sha256".split()),
    "visual.verification.effect-completion.local.v1": frozenset("scope result task_id plan_id robot_id step_id attempt plan_version command_seq before_observation_id execution_payload_hash source_checkpoint_hash source_hashes".split()),
    "recovery.verification-budget.local.v1": frozenset("task_id state revision content_hash".split()),
    "recovery.retry-budget.local.v1": frozenset("budget_id task_id per_step_retry_limit per_skill_retry_limit task_total_retry_limit retry_count_used task_retry_count step_retry_counts skill_retry_counts event_retry_counts retry_cooldown_ms retry_backoff_policy effective_retry_limit remaining_retries scene_version".split()),
}
OUTER_FIELDS = frozenset("schema_version payload original_time decision transaction diagnostics".split())
ORIGINAL_FIELDS = frozenset("schema_version app_domain task_origin_event_id task_reference verification_reference recovery_reference lease_identity source_hashes contract_provenance".split())
LEASE_IDENTITY_FIELDS = frozenset("job_id run_id worker_id lease_id attempt epoch source_identity original_acquisition".split())
REFERENCE_FIELDS = frozenset("schema_version window_id kind kind_policy budget_semantics budget_ns domain origin_domain task_origin_event_id event_id source_hashes source_identity job_id run_id worker_id lease_id attempt fencing episode_id parents age_constraints hard_deadlines deadline_ns deadline_semantics effective_upper lease_deadline_domain live_authority".split())
DECISION_FIELDS = frozenset("schema_version operation_id operation_sha256 original_time_hash app_domain app_current app_verdict app_references lease_observation lease_epoch lease_generation lease_row_revision lease_row_digest source_identity job_id run_id worker_id lease_id attempt disposition reasons".split())
TRANSACTION_FIELDS = frozenset("schema_version operation_id operation_sha256 job_id attempt lease_id epoch generation row_revision job_database_id event_repository_id event_kind event_key expected_event_revision event_revision event_record_hash job_receipt_hash event_receipt_hash phase failure_reason".split())
STATE_FIELDS = frozenset("remaining_reobservations remaining_retries consecutive_no_progress limits previous_conditions exhausted_reason verification_rounds original_budget_reference".split())
LIMIT_FIELDS = frozenset("max_reobservations max_retries max_no_progress deadline_s".split())


def _copy(value: object) -> JSONValue:
    if value is None or type(value) in (bool, str):
        if isinstance(value, (bool, str)) or value is None:
            return value
    if type(value) is int:
        if not -(2**63) < value < 2**63:
            raise ValueError("bounded integral JSON required")
        return value
    if type(value) is float:
        if not isfinite(value):
            raise ValueError("finite JSON required")
        return value
    if isinstance(value, Mapping):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if type(key) is not str or key in result:
                raise ValueError("unique strict JSON keys required")
            result[key] = _copy(item)
        return result
    if type(value) is list:
        return [_copy(item) for item in value]
    raise ValueError("detached JSON data required; live objects are forbidden")


def _object(value: object, fields: frozenset[str] | None = None) -> dict[str, JSONValue]:
    copied = _copy(value)
    if not isinstance(copied, dict) or (fields is not None and set(copied) != fields):
        raise ValueError("exact complete object fields required")
    return copied


def _array(value: JSONValue) -> list[JSONValue]:
    if not isinstance(value, list):
        raise ValueError("strict JSON array required")
    return value


def _text(value: JSONValue) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError("nonempty text required")
    return value


def _integer(value: JSONValue, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError("strict nonnegative integer required")
    return value


def _number(value: JSONValue, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("strict finite number required")
    if value < 0 or (positive and value <= 0):
        raise ValueError("positive policy duration required")
    return float(value)


def _sha(value: JSONValue) -> str:
    text = _text(value)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError("SHA256 required")
    return text


def _canonical(value: JSONValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: JSONValue) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _hashes(value: JSONValue) -> dict[str, JSONValue]:
    hashes = _object(value)
    if not hashes:
        raise ValueError("nonempty source inventory required")
    for name, digest in hashes.items():
        _text(name)
        _sha(digest)
    return hashes


def _domain(value: JSONValue) -> dict[str, JSONValue]:
    # The frozen P5 pure domain validator has no issuer/registry side effect.
    from cloud_edge_robot_arm.vision.operational_windows import _validate_domain

    domain = _object(value)
    _validate_domain(domain)
    return domain


def _bracket(value: JSONValue, *, event: bool = True) -> dict[str, JSONValue]:
    fields = frozenset("domain event_identity lower_ns upper_ns".split()) if event else frozenset("domain lower_ns upper_ns".split())
    bracket = _object(value, fields)
    _domain(bracket["domain"])
    if event:
        _text(bracket["event_identity"])
    if _integer(bracket["lower_ns"]) > _integer(bracket["upper_ns"]):
        raise ValueError("reversed detached bracket")
    return bracket


def _reference(value: JSONValue) -> dict[str, JSONValue]:
    ref = _object(value, REFERENCE_FIELDS)
    if ref["schema_version"] != "simulation.operational-window.local.v1":
        raise ValueError("exact local window tag required")
    if ref["lease_deadline_domain"] != "SEPARATE_D_LEASE_DECISION" or ref["live_authority"] != "NOT_EXPORTED":
        raise ValueError("D_app reference must exclude renewable D_lease authority")
    if ref["origin_domain"] != "ORIGINAL_TASK_D" or ref["deadline_semantics"] != "HARD_OPEN":
        raise ValueError("fixed original task causality required")
    _domain(ref["domain"])
    for key in ("window_id", "event_id", "task_origin_event_id", "job_id", "run_id", "worker_id", "lease_id", "fencing"):
        _text(ref[key])
    _sha(ref["source_identity"])
    _integer(ref["attempt"], positive=True)
    _hashes(ref["source_hashes"])
    budget = _integer(ref["budget_ns"], positive=True)
    parents = [_text(parent) for parent in _array(ref["parents"])]
    if len(parents) != len(set(parents)) or ref["window_id"] in parents:
        raise ValueError("duplicate/self parent identity")
    bootstrap = ref["kind"] == "bootstrap"
    if ref["kind"] not in {"bootstrap", "capture", "plan", "grounding", "supervision", "marker", "condition"}:
        raise ValueError("known local window kind required")
    if ref["kind_policy"] != ("HARD_ORIGINAL_TASK_LIFECYCLE" if bootstrap else "AGE_CLOSED") or ref["budget_semantics"] != ("HARD_OPEN" if bootstrap else "AGE_CLOSED"):
        raise ValueError("exact original window policy required")
    if bootstrap and (parents or ref["event_id"] != ref["task_origin_event_id"]):
        raise ValueError("original task window has no unissued parent")
    ages = _array(ref["age_constraints"])
    hard = _array(ref["hard_deadlines"])
    if not hard or (not bootstrap and (not ages or budget > 5_000_000_000)):
        raise ValueError("original hard/age constraints required")
    endpoints: list[int] = []
    origins: set[int] = set()
    for raw in hard:
        item = _object(raw, frozenset("origin_event_id source_id budget_ns deadline_ns end_exclusive".split()))
        if item["origin_event_id"] != ref["task_origin_event_id"] or item["end_exclusive"] is not True:
            raise ValueError("fixed original HARD_OPEN origin required")
        _text(item["source_id"])
        end = _integer(item["deadline_ns"], positive=True)
        length = _integer(item["budget_ns"], positive=True)
        if end < length:
            raise ValueError("hard origin cannot precede domain counter")
        origins.add(end - length)
        endpoints.append(end)
    if len(origins) != 1:
        raise ValueError("all obligations must retain original task origin")
    hard_end = min(endpoints)
    if _integer(ref["deadline_ns"], positive=True) != hard_end:
        raise ValueError("original deadline minimum changed")
    for raw in ages:
        item = _object(raw, frozenset("event_id source_id lower_ns upper_ns max_age_ns upper_age_inclusive expiry_upper_ns".split()))
        _text(item["event_id"]); _text(item["source_id"])
        lower = _integer(item["lower_ns"]); upper = _integer(item["upper_ns"])
        maximum = _integer(item["max_age_ns"], positive=True)
        expiry = _integer(item["expiry_upper_ns"], positive=True)
        if lower > upper or maximum > 5_000_000_000 or expiry != lower + maximum or item["upper_age_inclusive"] is not True:
            raise ValueError("inconsistent AGE_CLOSED constraint")
        endpoints.append(expiry)
    effective = _object(ref["effective_upper"], frozenset(("value_ns", "inclusive")))
    if effective["value_ns"] != min(endpoints) or type(effective["inclusive"]) is not bool or effective["inclusive"] != (min(endpoints) < hard_end):
        raise ValueError("effective original bound changed")
    return ref


def _original(value: JSONValue) -> dict[str, JSONValue]:
    original = _object(value, ORIGINAL_FIELDS)
    if original["schema_version"] != "visual.local-original-time.v1":
        raise ValueError("exact immutable original tag required")
    app_domain = _domain(original["app_domain"])
    origin = _text(original["task_origin_event_id"])
    hashes = _hashes(original["source_hashes"])
    identity = _object(original["lease_identity"], LEASE_IDENTITY_FIELDS)
    for key in ("job_id", "run_id", "worker_id", "lease_id", "epoch"):
        _text(identity[key])
    _integer(identity["attempt"], positive=True); _sha(identity["source_identity"])
    acquisition = _bracket(identity["original_acquisition"])
    if acquisition["domain"] == app_domain:
        raise ValueError("app and broker authority domains must remain distinct")
    references = [_reference(original[name]) for name in ("task_reference", "verification_reference", "recovery_reference")]
    task = references[0]
    available = {_text(ref["window_id"]) for ref in references}
    for ref in references:
        if ref["domain"] != app_domain or ref["task_origin_event_id"] != origin or ref["source_hashes"] != hashes:
            raise ValueError("immutable original domain/origin/source changed")
        if ref["source_identity"] != identity["source_identity"] or any(ref[key] != identity[key] for key in ("job_id", "run_id", "worker_id", "lease_id", "attempt")):
            raise ValueError("reference original job/fence changed")
        if any(_text(parent) not in available for parent in _array(ref["parents"])):
            raise ValueError("unissued detached original parent")
        if ref["hard_deadlines"] != task["hard_deadlines"]:
            raise ValueError("original obligations cannot be extended or rebound")
    provenance = _object(original["contract_provenance"], frozenset(("kind", "content_sha256")))
    if provenance["kind"] not in {"LOCAL_APP_PRODUCED", "EXTERNAL_UTC"}:
        raise ValueError("explicit immutable contract provenance required")
    _sha(provenance["content_sha256"])
    return original


def _decision(value: JSONValue) -> dict[str, JSONValue]:
    decision = _object(value, DECISION_FIELDS)
    if decision["schema_version"] != "visual.local-two-authority-decision.v1":
        raise ValueError("exact two-authority decision tag required")
    for key in ("operation_id", "lease_epoch", "job_id", "run_id", "worker_id", "lease_id"):
        _text(decision[key])
    for key in ("operation_sha256", "original_time_hash", "lease_row_digest", "source_identity"):
        _sha(decision[key])
    for key in ("lease_generation", "lease_row_revision", "attempt"):
        _integer(decision[key], positive=True)
    domain = _domain(decision["app_domain"])
    current = _bracket(decision["app_current"])
    if current["domain"] != domain:
        raise ValueError("current app event belongs to another domain")
    refs = [_reference(raw) for raw in _array(decision["app_references"])]
    if not refs or any(ref["domain"] != domain for ref in refs):
        raise ValueError("same original D_app references required")
    app = _object(decision["app_verdict"], frozenset(("status", "reasons")))
    observation = _object(decision["lease_observation"])
    if observation.get("schema") != "simulation.operational-lease-observation.v1":
        raise ValueError("detached actual broker observation shape required")
    lease_domain = _domain(observation["domain"])
    if lease_domain == domain:
        raise ValueError("never merge D_app and D_lease")
    if observation["generation"] != decision["lease_generation"] or any(observation[key] != decision[key] for key in ("job_id", "worker_id", "lease_id", "attempt", "source_identity")):
        raise ValueError("decision current lease/fence mismatch")
    if _object(observation["current"])["domain"] != lease_domain:
        raise ValueError("broker current domain changed")
    if _bracket(observation["original_acquisition"])["domain"] != lease_domain:
        raise ValueError("broker original acquisition domain changed")
    if decision["disposition"] not in {"VALID", "REJECTED", "UNKNOWN"}:
        raise ValueError("detached disposition required")
    for raw in (decision["reasons"], app["reasons"], observation["reasons"]):
        for reason in _array(raw):
            _text(reason)
    if decision["disposition"] == "VALID":
        if app["status"] != "VALID" or observation["status"] != "VALID":
            raise ValueError("both independent recorded authorities must be valid")
        if any(_integer(current["upper_ns"]) >= _integer(ref["deadline_ns"], positive=True) for ref in refs):
            raise ValueError("recorded app decision expired at original hard bound")
    return decision


def _transaction(value: JSONValue) -> dict[str, JSONValue]:
    transaction = _object(value, TRANSACTION_FIELDS)
    if transaction["schema_version"] != "visual.local-publication-transaction.v1":
        raise ValueError("exact transaction history tag required")
    for key in ("operation_id", "job_id", "lease_id", "epoch", "job_database_id", "event_repository_id", "event_kind", "event_key"):
        _text(transaction[key])
    for key in ("operation_sha256", "event_record_hash"):
        _sha(transaction[key])
    for key in ("attempt", "generation"):
        _integer(transaction[key], positive=True)
    for key in ("row_revision", "expected_event_revision", "event_revision"):
        _integer(transaction[key])
    if transaction["phase"] not in {"PENDING", "EVENT_COMMITTED", "COMPLETE", "REJECTED", "UNKNOWN"}:
        raise ValueError("transaction phase must remain descriptive")
    for key in ("job_receipt_hash", "event_receipt_hash"):
        if transaction[key] is not None:
            _sha(transaction[key])
    if transaction["phase"] == "COMPLETE" and (transaction["job_receipt_hash"] is None or transaction["event_receipt_hash"] is None):
        raise ValueError("completed history requires both durable receipt hashes")
    if transaction["failure_reason"] is not None:
        _text(transaction["failure_reason"])
    return transaction


def _state(value: JSONValue) -> dict[str, JSONValue]:
    state = _object(value, STATE_FIELDS)
    limits = _object(state["limits"], LIMIT_FIELDS)
    for name in ("max_reobservations", "max_retries", "max_no_progress"):
        _integer(limits[name])
    deadline_s = _number(limits["deadline_s"], positive=True)
    for name in ("remaining_reobservations", "remaining_retries", "consecutive_no_progress", "verification_rounds"):
        _integer(state[name])
    if _integer(state["remaining_reobservations"]) > _integer(limits["max_reobservations"]) or _integer(state["remaining_retries"]) > _integer(limits["max_retries"]):
        raise ValueError("spent counters cannot exceed frozen limits")
    reference = _reference(state["original_budget_reference"])
    hard = [_object(raw) for raw in _array(reference["hard_deadlines"])]
    if int(deadline_s * 1_000_000_000) > min(_integer(item["budget_ns"], positive=True) for item in hard):
        raise ValueError("budget duration cannot extend the original obligation")
    for name, raw in _object(state["previous_conditions"]).items():
        _text(name)
        pair = _array(raw)
        if len(pair) != 2 or pair[0] not in {"UNKNOWN", "FAIL", "PASS"}:
            raise ValueError("complete typed condition history required")
        if pair[1] is not None:
            _number(pair[1])
    if state["exhausted_reason"] is not None:
        _text(state["exhausted_reason"])
    return state


def _model[Model: BaseModel](value: JSONValue, model: type[Model]) -> Model:
    parsed = model.model_validate_json(_canonical(value))
    if _canonical(_copy(parsed.model_dump(mode="json"))) != _canonical(value):
        raise ValueError("complete strict semantic model required")
    return parsed


def _semantic(tag: str, body: dict[str, JSONValue], original: dict[str, JSONValue]) -> None:
    from cloud_edge_robot_arm.contracts.models import RobotState, SkillExecutionResult, TaskContract, TaskStep
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    scope = body.get("scope")
    expected_scope = "BOOTSTRAP_SOURCE_ONLY" if tag.startswith("visual.bootstrap.") else "SUPERVISION_SOURCE_ONLY" if tag.startswith("visual.supervision.") else "SOURCE_ROUTE_ONLY"
    if scope is not None and scope != expected_scope:
        raise ValueError("exact detached semantic scope required")
    for name, value in body.items():
        if (name.endswith("_hash") or name.endswith("_sha256")) and value is not None:
            _sha(value)
        if name in {"revision", "owner_revision", "state_generation", "expected_revision", "attempt", "plan_version", "command_seq", "cursor", "max_periodic_captures", "max_supervisor_calls", "captures_reserved", "supervisor_calls_reserved", "last_capture_cursor", "last_wait_cursor"}:
            _integer(value)
    if "robot_state" in body:
        _model(body["robot_state"], RobotState)
    if body.get("observation") is not None:
        _model(body["observation"], RGBDObservation)
    if tag.endswith(".definition.local.v1"):
        _number(body["task_timeout_s"], positive=True)
        if tag.startswith("visual.bootstrap."):
            _object(body["verification_limits"], LIMIT_FIELDS)
            _text(body["episode_id"]); _text(body["user_instruction"])
        elif body["supervision_period_s"] is not None:
            _number(body["supervision_period_s"], positive=True)
    if "state" in body:
        state = _state(body["state"])
        if state["original_budget_reference"] != original["verification_reference"]:
            raise ValueError("budget must retain exact immutable original reference")
    if tag == "recovery.verification-budget.local.v1":
        binding = {"schema_version": tag, "task_id": body["task_id"], "state": body["state"], "revision": body["revision"]}
        if body["content_hash"] != _hash(binding):
            raise ValueError("new budget hash must cover new schema/task/state/revision")
    if tag == "visual.owner.original.local.v1":
        contract = _model(body["contract"], TaskContract)
        if body["contract_provenance"] != original["contract_provenance"] or _object(body["contract_provenance"])["content_sha256"] != _hash(body["contract"]):
            raise ValueError("original contract provenance/content changed")
        identity = _object(body["identity"])
        if identity["task_id"] != contract.task_id:
            raise ValueError("semantic task identity changed")
        requirements = _object(body["requirements"])
        if set(requirements) != {step.step_id for step in contract.steps}:
            raise ValueError("complete immutable action requirements required")
        for step in contract.steps:
            requirement = _object(requirements[step.step_id])
            if _model(requirement["original_step"], TaskStep).model_dump(mode="json") != step.model_dump(mode="json"):
                raise ValueError("original action policy changed")
        _hashes(body["source_hashes"]); _hashes(body["compiler_source_hashes"])
    if tag == "visual.owner.grounding.local.v1":
        step = _model(body["grounded_step"], TaskStep)
        requirement = _object(body["original_requirements"])
        prior = _model(requirement["original_step"], TaskStep)
        if (step.step_id, step.skill, step.timeout_ms, step.retry_limit) != (prior.step_id, prior.skill, prior.timeout_ms, prior.retry_limit):
            raise ValueError("grounding cannot weaken original action policy")
        if _number(body["expected_duration_s"], positive=True) < _number(requirement["expected_duration_s"], positive=True):
            raise ValueError("grounding cannot shorten immutable horizon")
    if tag == "visual.verification.effect-completion.local.v1":
        result = _model(body["result"], SkillExecutionResult)
        if (result.task_id, result.step_id, result.plan_version, result.command_seq) != (body["task_id"], body["step_id"], body["plan_version"], body["command_seq"]):
            raise ValueError("effect result/source identity changed")
    if tag == "recovery.retry-budget.local.v1":
        for name in ("per_step_retry_limit", "per_skill_retry_limit", "task_total_retry_limit", "retry_count_used", "task_retry_count", "retry_cooldown_ms", "effective_retry_limit", "remaining_retries", "scene_version"):
            _integer(body[name])
        for name in ("step_retry_counts", "skill_retry_counts", "event_retry_counts"):
            for count in _object(body[name]).values():
                _integer(count)
        if body["retry_count_used"] != body["task_retry_count"] or _integer(body["remaining_retries"]) > _integer(body["task_total_retry_limit"]) - _integer(body["task_retry_count"]):
            raise ValueError("retry history cannot refill original pool")


@dataclass(frozen=True, init=False)
class _DetachedValue:
    _json: str
    _kind: ClassVar[str] = ""

    @classmethod
    def from_payload(cls, payload: Mapping[str, JSONValue]) -> Self:
        raw = _object(payload)
        if cls._kind == "original":
            _original(raw)
        elif cls._kind == "decision":
            _decision(raw)
        elif cls._kind == "transaction":
            _transaction(raw)
        elif cls._kind == "state":
            _state(raw)
        else:
            raise ValueError("known detached value kind required")
        result = object.__new__(cls)
        object.__setattr__(result, "_json", _canonical(raw))
        return result

    def to_payload(self) -> dict[str, JSONValue]:
        return _object(json.loads(self._json))

    def digest(self) -> str:
        return hashlib.sha256(self._json.encode()).hexdigest()


class LocalOriginalTime(_DetachedValue):
    _kind = "original"


class LocalAuthorityDecision(_DetachedValue):
    _kind = "decision"


class LocalTransactionReceipt(_DetachedValue):
    _kind = "transaction"


class LocalVerificationBudgetState(_DetachedValue):
    _kind = "state"

    @property
    def remaining_reobservations(self) -> int:
        return _integer(self.to_payload()["remaining_reobservations"])

    @property
    def remaining_retries(self) -> int:
        return _integer(self.to_payload()["remaining_retries"])

    @property
    def original_budget_reference(self) -> dict[str, JSONValue]:
        return _reference(self.to_payload()["original_budget_reference"])


@dataclass(frozen=True, init=False)
class LocalEnvelope:
    _json: str

    @classmethod
    def from_payload(cls, payload: Mapping[str, JSONValue]) -> Self:
        raw = _object(payload, OUTER_FIELDS)
        tag = _text(raw["schema_version"])
        if tag not in FIELDS:
            raise ValueError("exact local semantic tag required")
        body = _object(raw["payload"], FIELDS[tag])
        original = _original(raw["original_time"])
        diagnostics = _object(raw["diagnostics"], frozenset(("utc", "monotonic")))
        for name, value in _object(diagnostics["utc"]).items():
            _text(name)
            if value is not None:
                stamp = datetime.fromisoformat(_text(value))
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    raise ValueError("typed diagnostic UTC required")
        if diagnostics["monotonic"] is not None:
            _number(diagnostics["monotonic"])
        original_or_request = tag.endswith((".definition.local.v1", ".original.local.v1", ".transition.local.v1", ".promotion.local.v1", ".route-input.local.v1"))
        if original_or_request:
            if raw["decision"] is not None or raw["transaction"] is not None:
                raise ValueError("original/request cannot self-install a current decision")
        else:
            decision = _decision(raw["decision"])
            transaction = _transaction(raw["transaction"])
            identity = _object(original["lease_identity"])
            if decision["original_time_hash"] != _hash(original) or decision["app_domain"] != original["app_domain"]:
                raise ValueError("decision must bind exact immutable original")
            for name in ("job_id", "run_id", "worker_id", "lease_id", "attempt", "source_identity"):
                if decision[name] != identity[name]:
                    raise ValueError("current decision cannot replace original identity")
            if decision["lease_epoch"] != identity["epoch"]:
                raise ValueError("original lease epoch changed")
            for current_name, decision_name in (("operation_id", "operation_id"), ("operation_sha256", "operation_sha256"), ("job_id", "job_id"), ("attempt", "attempt"), ("lease_id", "lease_id"), ("epoch", "lease_epoch"), ("generation", "lease_generation"), ("row_revision", "lease_row_revision")):
                if transaction[current_name] != decision[decision_name]:
                    raise ValueError("transaction and two-authority evidence disagree")
        _semantic(tag, body, original)
        result = object.__new__(cls)
        object.__setattr__(result, "_json", _canonical(raw))
        return result

    def to_payload(self) -> dict[str, JSONValue]:
        return _object(json.loads(self._json))

    def digest(self) -> str:
        return hashlib.sha256(self._json.encode()).hexdigest()

    @property
    def semantic(self) -> dict[str, JSONValue]:
        return _object(self.to_payload()["payload"])

    @property
    def local_time(self) -> LocalOriginalTime:
        return LocalOriginalTime.from_payload(_object(self.to_payload()["original_time"]))

    @property
    def decision(self) -> LocalAuthorityDecision | None:
        value = self.to_payload()["decision"]
        return None if value is None else LocalAuthorityDecision.from_payload(_object(value))

    @property
    def transaction(self) -> LocalTransactionReceipt | None:
        value = self.to_payload()["transaction"]
        return None if value is None else LocalTransactionReceipt.from_payload(_object(value))

    def detached(self) -> Self:
        return type(self).from_payload(self.to_payload())

    def string(self, name: str) -> str:
        return _text(self.semantic[name])

    def counter(self, name: str) -> int:
        return _integer(self.semantic[name])

    def object(self, name: str) -> dict[str, JSONValue]:
        return _object(self.semantic[name])

    def number(self, name: str, *, positive: bool = False) -> float:
        return _number(self.semantic[name], positive=positive)

    def boolean(self, name: str) -> bool:
        value = self.semantic[name]
        if type(value) is not bool:
            raise ValueError("strict semantic boolean required")
        return value

    def optional_string(self, name: str) -> str | None:
        value = self.semantic[name]
        return None if value is None else _text(value)

    def model[Model: BaseModel](self, name: str, model: type[Model]) -> Model:
        return _model(self.semantic[name], model)

    def optional_model[Model: BaseModel](self, name: str, model: type[Model]) -> Model | None:
        value = self.semantic[name]
        return None if value is None else _model(value, model)

    def strings(self, name: str) -> tuple[str, ...]:
        return tuple(_text(value) for value in _array(self.semantic[name]))

    def hashes(self, name: str) -> dict[str, str]:
        return {key: _sha(value) for key, value in _hashes(self.semantic[name]).items()}

    @classmethod
    def _from_local_payload(cls, payload: object, tag: str) -> Self:
        envelope = decode_local_payload(_object(payload), tag)
        result = object.__new__(cls)
        object.__setattr__(result, "_json", envelope._json)
        return result


def is_local_payload(payload: Mapping[str, object], tag: str) -> bool:
    return payload.get("schema_version") == tag


def decode_local_payload(payload: Mapping[str, JSONValue], tag: str) -> LocalEnvelope:
    envelope = LocalEnvelope.from_payload(payload)
    if envelope.to_payload()["schema_version"] != tag:
        raise ValueError("wrong domain local tag")
    return envelope


class LocalDomainEnvelope(LocalEnvelope):
    """Domain codec carrier; its base-class UTC paths are never constructors."""

    _tag: ClassVar[str] = ""

    def __init__(
        self,
        payload: Mapping[str, JSONValue],
        *,
        local_time: LocalOriginalTime | None = None,
    ) -> None:
        envelope = decode_local_payload(payload, self._tag)
        if local_time is not None and local_time.to_payload() != envelope.local_time.to_payload():
            raise ValueError("local time cannot replace the immutable original")
        object.__setattr__(self, "_json", envelope._json)

    @classmethod
    def from_payload(cls, payload: Mapping[str, JSONValue]) -> Self:
        return cls._from_local_payload(payload, cls._tag)

    def to_json(self) -> str:
        return self._json

    @classmethod
    def from_json(cls, raw: str) -> Self:
        def pairs(items: list[tuple[str, JSONValue]]) -> dict[str, JSONValue]:
            values: dict[str, JSONValue] = {}
            for key, value in items:
                if key in values:
                    raise ValueError("duplicate local JSON field")
                values[key] = value
            return values

        return cls.from_payload(_object(json.loads(raw, object_pairs_hook=pairs)))

    def legacy_deadline(self) -> datetime:
        raise ValueError("local history has no UTC authority deadline")
