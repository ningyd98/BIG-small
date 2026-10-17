"""Strict detached Stage-B histories. Serialization never grants live authority."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from math import ceil as math_ceil, isfinite
from typing import TYPE_CHECKING, ClassVar, Self

from pydantic import BaseModel

if TYPE_CHECKING:
    from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
    from cloud_edge_robot_arm.vision.owner_registration import VisualOriginalPlan

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


def _lease_segment_receipt(value: JSONValue) -> dict[str, JSONValue]:
    """Validate and preserve a detached raw broker receipt, without issuing one."""
    receipt = _object(value, frozenset(
        "domain event_id lower_ns upper_ns deadline_ns budget_ns end_exclusive".split()
    ))
    _domain(receipt["domain"])
    _text(receipt["event_id"])
    lower = _integer(receipt["lower_ns"])
    upper = _integer(receipt["upper_ns"])
    budget = _integer(receipt["budget_ns"], positive=True)
    deadline = _integer(receipt["deadline_ns"], positive=True)
    if lower > upper or deadline != lower + budget or receipt["end_exclusive"] is not True:
        raise ValueError("exact detached broker HARD_OPEN receipt required")
    return receipt


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
    if not bootstrap and not any(
        _object(raw)["event_id"] == ref["event_id"]
        and _object(raw)["max_age_ns"] == ref["budget_ns"] for raw in ages
    ):
        raise ValueError("own AGE_CLOSED event/budget source linkage required")
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
    acquisition = _lease_segment_receipt(identity["original_acquisition"])
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
        if ref["fencing"] != task["fencing"]:
            raise ValueError("immutable original references must retain the same fence")
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
    _text(app["status"])
    observation = _object(decision["lease_observation"], frozenset(
        "status reasons domain original_acquisition segment current job_id lease_id worker_id attempt generation source_identity schema stage_label".split()
    ))
    if observation["schema"] != "simulation.operational-lease-observation.v1" or observation["stage_label"] != "LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO":
        raise ValueError("exact unchanged broker observation schema/stage required")
    _text(observation["status"])
    lease_domain = _domain(observation["domain"])
    if lease_domain == domain:
        raise ValueError("never merge D_app and D_lease")
    if _integer(observation["generation"], positive=True) != decision["lease_generation"] or any(observation[key] != decision[key] for key in ("job_id", "worker_id", "lease_id", "attempt", "source_identity")):
        raise ValueError("decision current lease/fence mismatch")
    acquisition = _lease_segment_receipt(observation["original_acquisition"])
    segment = _lease_segment_receipt(observation["segment"])
    lease_current = _bracket(observation["current"], event=False)
    if any(item["domain"] != lease_domain for item in (acquisition, segment, lease_current)):
        raise ValueError("broker acquisition/current segment/current bracket domain changed")
    if acquisition["budget_ns"] != segment["budget_ns"]:
        raise ValueError("renewal cannot change the frozen broker TTL")
    if decision["disposition"] not in {"VALID", "REJECTED", "UNKNOWN"}:
        raise ValueError("detached disposition required")
    for raw in (decision["reasons"], app["reasons"], observation["reasons"]):
        for reason in _array(raw):
            _text(reason)
    if decision["disposition"] == "VALID":
        if app["status"] != "VALID" or observation["status"] != "VALID":
            raise ValueError("both independent recorded authorities must be valid")
        app_upper = _integer(current["upper_ns"])
        for ref in refs:
            for raw in _array(ref["hard_deadlines"]):
                hard = _object(raw)
                if app_upper < _integer(hard["deadline_ns"]) - _integer(hard["budget_ns"]):
                    raise ValueError("recorded app current precedes original hard source lower bound")
            for raw in _array(ref["age_constraints"]):
                if app_upper < _integer(_object(raw)["lower_ns"]):
                    raise ValueError("recorded app current precedes causal age source lower bound")
            effective = _object(ref["effective_upper"])
            endpoint = _integer(effective["value_ns"])
            if app_upper >= _integer(ref["deadline_ns"], positive=True) or app_upper > endpoint or (app_upper == endpoint and effective["inclusive"] is not True):
                raise ValueError("recorded D_app decision crosses original HARD_OPEN/AGE_CLOSED bounds")
        if _integer(lease_current["upper_ns"]) >= _integer(segment["deadline_ns"], positive=True):
            raise ValueError("recorded D_lease decision crosses current segment HARD_OPEN bound")
        if (_integer(lease_current["upper_ns"]) < _integer(acquisition["lower_ns"])
                or _integer(segment["upper_ns"]) < _integer(acquisition["lower_ns"])):
            raise ValueError("recorded lease evidence precedes original acquisition lower bound")
        if _integer(lease_current["upper_ns"]) < _integer(segment["lower_ns"]):
            raise ValueError("recorded lease current precedes segment causal lower bound")
    return decision


def _join_decision(original: dict[str, JSONValue], decision: dict[str, JSONValue]) -> None:
    identity = _object(original["lease_identity"])
    if decision["original_time_hash"] != _hash(original) or decision["app_domain"] != original["app_domain"]:
        raise ValueError("decision must bind the exact immutable original")
    for name in ("job_id", "run_id", "worker_id", "lease_id", "attempt", "source_identity"):
        if decision[name] != identity[name]:
            raise ValueError("current decision cannot replace original identity")
    if decision["lease_epoch"] != identity["epoch"]:
        raise ValueError("original lease epoch changed")
    if _object(decision["lease_observation"])["original_acquisition"] != identity["original_acquisition"]:
        raise ValueError("renewal cannot replace the immutable raw original acquisition")
    task = _object(original["task_reference"])
    for raw in _array(decision["app_references"]):
        reference = _object(raw)
        if reference["task_origin_event_id"] != original["task_origin_event_id"] or reference["source_hashes"] != original["source_hashes"] or reference["source_identity"] != identity["source_identity"] or reference["hard_deadlines"] != task["hard_deadlines"] or reference["fencing"] != task["fencing"]:
            raise ValueError("current app evidence cannot replace original obligations/source/fence")
        for name in ("job_id", "run_id", "worker_id", "lease_id", "attempt"):
            if reference[name] != identity[name]:
                raise ValueError("current app reference job identity changed")


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


def _audit_original(value: JSONValue) -> VisualOriginalPlan:
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import original_from_payload

    return original_from_payload(_object(value))


def semantic_projection(value: JSONValue) -> JSONValue:
    """Project complete local envelopes only; all other semantic keys survive."""
    if isinstance(value, list):
        return [semantic_projection(item) for item in value]
    if isinstance(value, dict):
        tag = value.get("schema_version")
        if isinstance(tag, str) and tag in FIELDS:
            envelope = LocalEnvelope.from_payload(value)
            return {"schema_version": tag, "payload": semantic_projection(envelope.semantic),
                    "original_time": envelope.local_time.to_payload()}
        return {key: semantic_projection(item) for key, item in value.items()}
    return value


def _validate_nested_local(value: JSONValue) -> None:
    """Validate strict descendants, including envelopes in descriptive JSON."""
    if isinstance(value, list):
        for item in value:
            _validate_nested_local(item)
    elif isinstance(value, dict):
        tag = value.get("schema_version")
        if isinstance(tag, str) and tag in FIELDS:
            # The child validates its own descendants; never revisit its parent.
            LocalEnvelope.from_payload(value)
        else:
            for item in value.values():
                _validate_nested_local(item)


def _semantic_child_original(
    value: JSONValue, tag: str, original: dict[str, JSONValue],
) -> None:
    """Only an explicitly supported semantic edge binds a child's original."""
    if value is None:
        return
    raw = _object(value)
    if raw.get("schema_version") == tag:
        child = decode_local_payload(raw, tag)
        if child.local_time.to_payload() != original:
            raise ValueError("semantic child must retain exact enclosing original reference")


def _local_publication_hash(body: dict[str, JSONValue], original: dict[str, JSONValue]) -> str:
    content = dict(body)
    content.pop("publication_hash")
    return _hash({"schema_version": "visual.owner.publication.local.v1",
                  "payload": semantic_projection(content), "original_time": original})


def _audit_publication(
    value: JSONValue, original: VisualOriginalPlan | None = None,
    *, enclosing: dict[str, JSONValue] | None = None,
) -> dict[str, JSONValue]:
    """Exact tag dispatch, with local original joins and unchanged legacy hashes."""
    raw = _object(value)
    local_original: dict[str, JSONValue] | None = None
    if raw.get("schema_version") == "visual.owner.publication.local.v1":
        envelope = LocalEnvelope.from_payload(raw)
        local_original = envelope.local_time.to_payload()
        if enclosing is not None and local_original != enclosing:
            raise ValueError("nested publication must retain enclosing original reference")
        raw = envelope.semantic
    else:
        raw = _object(raw, frozenset(
            "schema_version binding_scope mode_scope identity original_plan_hash contract_hash owner_revision state_generation checkpoint verification_budget retry_budget grounding effective_deadline_at operation_hash source_owner_revision published_at publication_hash".split()
        ))
        if raw["schema_version"] != "visual.owner.publication.v1":
            raise ValueError("exact preserved audit publication tag required")
        content = dict(raw)
        declared = content.pop("publication_hash")
        if _sha(declared) != _hash(content):
            raise ValueError("audit publication content hash differs")
        for name in ("effective_deadline_at", "published_at"):
            stamp = datetime.fromisoformat(_text(raw[name]))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("aware preserved audit timestamp required")
    return _publication_body(raw, original, local_original=local_original)


def _publication_body(
    raw: dict[str, JSONValue], original: VisualOriginalPlan | None = None,
    *, local_original: dict[str, JSONValue] | None = None,
) -> dict[str, JSONValue]:
    """Validate detached audit sources without consulting the current wall clock."""
    from cloud_edge_robot_arm.contracts.models import ExecutionCheckpoint, RecoveryBudget
    from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord
    from cloud_edge_robot_arm.repositories.event_autonomy.hashing import stable_payload_hash
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import grounding_from_payload, strict_retry
    from cloud_edge_robot_arm.vision.owner_registration import local_owner_identity

    if raw["binding_scope"] != "DURABLE_BINDING_ONLY" or raw["mode_scope"] != "NOT_INCLUDED":
        raise ValueError("publication remains a durable binding only")
    identity = local_owner_identity(_object(raw["identity"]))
    if local_original is not None:
        lease = _object(local_original["lease_identity"])
        if ((identity.job_id, identity.run_id, identity.worker_id, identity.lease_id,
             identity.attempt, identity.owner_epoch)
                != (lease["job_id"], lease["run_id"], lease["worker_id"], lease["lease_id"],
                    lease["attempt"], lease["epoch"])):
            raise ValueError("publication original task lease/fence/epoch differs")
    checkpoint = _model(raw["checkpoint"], ExecutionCheckpoint)
    checkpoint_body = _object(raw["checkpoint"])
    checkpoint_body["checkpoint_hash"] = ""
    if checkpoint.checkpoint_hash != stable_payload_hash(checkpoint_body):
        raise ValueError("audit checkpoint content hash differs")
    if (checkpoint.task_id, checkpoint.plan_id, checkpoint.robot_id) != (identity.task_id, identity.plan_id, identity.robot_id):
        raise ValueError("publication checkpoint identity differs")
    pool = _object(raw["verification_budget"])
    if pool.get("schema_version") == "recovery.verification-budget.local.v1":
        envelope = LocalEnvelope.from_payload(pool)
        if local_original is not None and envelope.local_time.to_payload() != local_original:
            raise ValueError("publication verification pool original reference differs")
        pool_task = envelope.string("task_id")
    else:
        pool_task = VerificationBudgetRecord.from_payload(pool).task_id
    retry_raw = _object(raw["retry_budget"])
    if retry_raw.get("schema_version") == "recovery.retry-budget.local.v1":
        retry_envelope = LocalEnvelope.from_payload(retry_raw)
        if local_original is not None and retry_envelope.local_time.to_payload() != local_original:
            raise ValueError("publication retry pool original recovery reference differs")
        retry_task = retry_envelope.string("task_id")
    elif "schema_version" in retry_raw:
        raise ValueError("unsupported publication retry budget schema/tag")
    else:
        retry_task = strict_retry(_model(retry_raw, RecoveryBudget)).task_id
    if pool_task != identity.task_id or retry_task != identity.task_id:
        raise ValueError("publication budget task binding differs")
    _integer(raw["owner_revision"], positive=True)
    _integer(raw["state_generation"])
    if raw["source_owner_revision"] is not None:
        _integer(raw["source_owner_revision"])
    for name in ("original_plan_hash", "contract_hash", "operation_hash", "publication_hash"):
        _sha(raw[name])
    if raw["grounding"] is not None:
        grounding_from_payload(_object(raw["grounding"]))
        if local_original is not None:
            _semantic_child_original(raw["grounding"], "visual.owner.grounding.local.v1", local_original)
    if original is not None and (identity != original.identity or raw["original_plan_hash"] != original.digest() or raw["contract_hash"] != stable_payload_hash(original.contract)):
        raise ValueError("publication must retain its complete original source")
    return raw


def _audit_supervision_definition(value: JSONValue) -> tuple[str, int]:
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import _lease
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import _bundle

    raw = _object(value)
    if raw.get("schema_version") == "visual.supervision.definition.local.v1":
        envelope = LocalEnvelope.from_payload(raw)
        prior = _audit_original(envelope.semantic["original"])
        reference = _object(envelope.local_time.to_payload()["verification_reference"])
        lengths = [_integer(_object(item)["budget_ns"], positive=True) for item in _array(reference["hard_deadlines"])]
        period = envelope.semantic["supervision_period_s"]
        maximum = 0 if period is None else max(0, math_ceil(min(lengths) / 1_000_000_000 / _number(period, positive=True)) - 1)
        return prior.identity.task_id, maximum
    required = frozenset("schema_version scope original publication lease task_started_at task_timeout_s supervision_period_s model_snapshot_hash role_bundle job_configuration_hash".split())
    _object(raw, required | ({"operational_windows"} if "operational_windows" in raw else set()))
    if raw["schema_version"] != "visual.supervision.definition.v1" or raw["scope"] != "SUPERVISION_SOURCE_ONLY":
        raise ValueError("exact preserved supervision definition required")
    prior = _audit_original(raw["original"])
    _audit_publication(raw["publication"], prior)
    lease = _lease(_object(raw["lease"]))
    if lease.identity(episode_id=prior.identity.episode_id, task_id=prior.identity.task_id, plan_id=prior.identity.plan_id, robot_id=prior.identity.robot_id) != prior.identity:
        raise ValueError("audit supervision lease/original identity differs")
    if _bundle(_object(raw["role_bundle"])).digest() != prior.role_bundle_hash:
        raise ValueError("audit supervision role policy differs")
    start = datetime.fromisoformat(_text(raw["task_started_at"]))
    if start.tzinfo is None or start.utcoffset() is None:
        raise ValueError("aware original audit timestamp required")
    _number(raw["task_timeout_s"], positive=True)
    _sha(raw["model_snapshot_hash"])
    if raw["job_configuration_hash"] is not None:
        _sha(raw["job_configuration_hash"])
    period = raw["supervision_period_s"]
    duration = (prior.effective_deadline_at - start).total_seconds()
    maximum = 0 if period is None else max(0, math_ceil(duration / _number(period, positive=True)) - 1)
    return prior.identity.task_id, maximum


def _audit_pool(value: JSONValue, *, enclosing: dict[str, JSONValue] | None = None) -> dict[str, JSONValue]:
    from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord

    raw = _object(value)
    if raw.get("schema_version") == "recovery.verification-budget.local.v1":
        envelope = LocalEnvelope.from_payload(raw)
        if enclosing is not None and envelope.local_time.to_payload() != enclosing:
            raise ValueError("route nested pool original reference differs")
        return envelope.semantic
    _object(raw, frozenset("schema_version task_id state revision created_at updated_at content_hash".split()))
    if raw["schema_version"] != "recovery.verification-budget.v1":
        raise ValueError("exact preserved budget source required")
    VerificationBudgetRecord.from_payload(raw)
    return raw


def _join_audit_original(prior: VisualOriginalPlan, original: dict[str, JSONValue]) -> None:
    lease = _object(original["lease_identity"])
    identity = prior.identity
    if ((identity.job_id, identity.run_id, identity.worker_id, identity.lease_id,
         identity.attempt, identity.owner_epoch)
            != (lease["job_id"], lease["run_id"], lease["worker_id"], lease["lease_id"],
                lease["attempt"], lease["epoch"])):
        raise ValueError("audit original task lease/fence/epoch binding differs")
    if (_copy(dict(prior.source_hashes)) != original["source_hashes"]
            or _object(original["contract_provenance"])["content_sha256"]
            != _hash(_copy(prior.contract.model_dump(mode="json")))):
        raise ValueError("audit original source/contract binding differs")


def _route_parts(value: JSONValue) -> tuple[str, dict[str, JSONValue], dict[str, JSONValue] | None]:
    raw = _object(value)
    tag = _text(raw["schema_version"])
    if tag == "visual.verification.route-input.local.v1":
        request = LocalEnvelope.from_payload(raw)
        return tag, request.semantic, request.local_time.to_payload()
    if tag not in {"visual.verification.route-input.v1", "visual.verification.route-input.v2"}:
        raise ValueError("exact local or preserved legacy route request tag required")
    fields = FIELDS["visual.verification.route-input.local.v1"] | {"schema_version"}
    if tag == "visual.verification.route-input.v1":
        fields = fields - {"grounding_receipt"}
    _object(raw, fields)
    if raw["scope"] != "SOURCE_ROUTE_ONLY":
        raise ValueError("exact preserved route request scope required")
    return tag, raw, None


def route_source_key(value: JSONValue) -> str:
    """Exact immutable source-key recipe, without constructing a live/UTC request."""
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    tag, body, original_time = _route_parts(value)
    prior = _audit_original(body["original"])
    online = _object(body["online"], frozenset(
        "observation robot_state visual_facts plan_version command_seq context_hash".split()
    ))
    observation = _model(online["observation"], RGBDObservation)
    step = _text(body["step_id"])
    if step not in prior.requirements:
        raise ValueError("route source step is outside original requirements")
    result: dict[str, JSONValue] = {
        "schema_version": "visual.verification.source-key.local.v1" if original_time is not None
                          else "visual.verification.source-key.v1",
        "task_id": prior.identity.task_id, "original_plan_hash": prior.digest(),
        "plan_version": prior.contract.plan_version, "command_seq": prior.contract.command_seq,
        "step_id": step, "attempt": _integer(body["attempt"], positive=True),
        "phase": _text(body["phase"]), "frame_id": observation.observation_id,
        "frame_checksum": observation.checksum_sha256,
        "requirements_hash": prior.requirements[step].digest(),
    }
    if tag == "visual.verification.route-input.local.v1":
        if original_time is None:
            raise ValueError("local route original required")
        result["original_time_hash"] = _hash(original_time)
    return _hash(result)


def route_semantic_hash(value: JSONValue) -> str:
    tag, body, original_time = _route_parts(value)
    if tag == "visual.verification.route-input.local.v1":
        content = dict(body)
        content.pop("event_key")
        return _hash({"schema_version": tag, "payload": semantic_projection(content),
                      "original_time": original_time})
    names = ("original", "online", "step_id", "attempt", "phase",
             "execution_contract", "completion")
    content = {name: body[name] for name in names}
    if tag == "visual.verification.route-input.v2":
        content["grounding_receipt"] = body["grounding_receipt"]
    return _hash(content)


def _history_state_hash(tag: str, body: dict[str, JSONValue], original: dict[str, JSONValue]) -> str:
    content = dict(body)
    content.pop("history")
    return _hash({"schema_version": tag, "payload": semantic_projection(content),
                  "original_time": original})


def _history_definition(
    value: JSONValue, original: dict[str, JSONValue], *, bootstrap: bool,
) -> tuple[dict[str, JSONValue], str, int]:
    raw = _object(value)
    local_tag = "visual.bootstrap.definition.local.v1" if bootstrap else "visual.supervision.definition.local.v1"
    legacy_tag = local_tag.replace(".local.v1", ".v1")
    if raw.get("schema_version") == local_tag:
        envelope = LocalEnvelope.from_payload(raw)
        if envelope.local_time.to_payload() != original:
            raise ValueError("history definition original reference differs")
        source = envelope.semantic
    elif raw.get("schema_version") == legacy_tag:
        if bootstrap:
            from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import VisualBootstrapDefinition

            VisualBootstrapDefinition.from_payload(raw)
        else:
            _audit_supervision_definition(raw)
        source = raw
    else:
        raise ValueError("unsupported history definition source tag")
    identity = _object(original["lease_identity"])
    if bootstrap:
        if source["source_hashes"] != original["source_hashes"]:
            raise ValueError("bootstrap definition source inventory differs")
        if source["episode_id"] != _object(original["task_reference"])["episode_id"]:
            raise ValueError("bootstrap definition episode source differs")
        if raw["schema_version"] == legacy_tag:
            lease = _object(source["lease"])
            if any(lease[key] != identity[key] for key in
                   ("job_id", "run_id", "worker_id", "lease_id", "attempt")):
                raise ValueError("bootstrap definition task lease differs")
        definition_id = _hash(["visual.bootstrap.job-run.v1", identity["job_id"], identity["run_id"]])
        return source, definition_id, 0
    prior = _audit_original(source["original"])
    _join_audit_original(prior, original)
    _, maximum = _audit_supervision_definition(raw)
    return source, prior.identity.task_id, maximum


def _initial_history_state(
    definition: JSONValue, original: dict[str, JSONValue], *, bootstrap: bool,
) -> dict[str, JSONValue]:
    source, _, maximum = _history_definition(definition, original, bootstrap=bootstrap)
    if bootstrap:
        limits = _object(source["verification_limits"], LIMIT_FIELDS)
        state: dict[str, JSONValue] = {
            "remaining_reobservations": _integer(limits["max_reobservations"]),
            "remaining_retries": _integer(limits["max_retries"]),
            "consecutive_no_progress": 0, "limits": limits, "previous_conditions": {},
            "exhausted_reason": None, "verification_rounds": 0,
            "original_budget_reference": _object(original["verification_reference"]),
        }
        _state(state)
        return {
            "scope": "BOOTSTRAP_SOURCE_ONLY", "definition": _copy(definition), "revision": 0,
            "state": state, "initial_capture_claimed": False, "pending": None,
            "observation": None, "camera_descriptor_hash": None, "draft": None,
            "planning_source_usable": False, "proposal_hash": None, "terminal_reason": None,
            "adopted_original_hash": None, "history": [],
        }
    return {
        "scope": "SUPERVISION_SOURCE_ONLY", "definition": _copy(definition), "revision": 0,
        "max_periodic_captures": maximum, "max_supervisor_calls": maximum,
        "captures_reserved": 0, "supervisor_calls_reserved": 0,
        "last_capture_cursor": 0, "last_wait_cursor": 0, "wait_seconds_reserved": 0.0,
        "claims": {}, "history": [],
    }


def _proposal_projection(draft: dict[str, JSONValue], source: dict[str, JSONValue]) -> dict[str, JSONValue] | None:
    """Validate the adapter's semantic fields without filling identity/time placeholders."""
    from copy import deepcopy
    from pydantic import ConfigDict, create_model
    from cloud_edge_robot_arm.contracts.models import (
        FailurePolicy, SafetyConstraints, TaskContract, TaskStep, TaskTarget,
    )

    if draft["parse_error"] is not None or not isinstance(draft["parsed_json"], dict):
        return None
    proposal = _object(draft["parsed_json"])
    if not proposal or "_sentinel" in proposal or set(proposal) - set(TaskContract.model_fields):
        return None
    bound = {"task_id", "plan_version", "command_seq", "timestamp", "issued_at", "valid_until"}
    try:
        if type(proposal.get("task_id")) is not str:
            return None
        for name in ("plan_version", "command_seq"):
            _integer(proposal.get(name))
        for name in ("timestamp", "issued_at", "valid_until"):
            value = proposal.get(name)
            if type(value) is not str:
                return None
            if isinstance(value, str) and value:
                stamp = datetime.fromisoformat(value)
                if stamp.tzinfo is None or stamp.utcoffset() is None:
                    return None
        for name, nested_model in (("task_target", TaskTarget),
                                   ("safety_constraints", SafetyConstraints),
                                   ("failure_policy", FailurePolicy)):
            nested = proposal.get(name)
            if not isinstance(nested, dict) or set(nested) - set(nested_model.model_fields):
                return None
        raw_steps = proposal.get("steps")
        if not isinstance(raw_steps, list) or any(
            not isinstance(step, dict) or set(step) - set(TaskStep.model_fields)
            for step in raw_steps
        ):
            return None
        # Copy FieldInfo so declared defaults/constraints survive without changing
        # the source model while separating its identity and UTC-only fields.
        fields = {name: (field.annotation, deepcopy(field))
                  for name, field in TaskContract.model_fields.items() if name not in bound}
        model = create_model("DetachedBootstrapProposal", __config__=ConfigDict(strict=True, extra="forbid"),
                             **fields)
        content = {name: value for name, value in proposal.items() if name not in bound}
        checked = model.model_validate_json(_canonical(content), strict=True)
        result = _object(_copy(checked.model_dump(mode="json")))
        steps = [_object(item) for item in _array(result["steps"])]
        ids = [_text(step["step_id"]) for step in steps]
        if (len(ids) != len(set(ids)) or result["user_instruction"] != source["user_instruction"]
                or (result["current_step_id"] is not None and result["current_step_id"] not in ids)):
            return None
        return result
    except (ValueError, TypeError, KeyError):
        return None


def _camera_descriptor(observation: dict[str, JSONValue]) -> str:
    return _hash({"schema_version": "visual.rgbd.camera-source-descriptor.v1",
                  **{name: observation[name] for name in (
                      "source", "width", "height", "intrinsics", "camera_to_world",
                      "depth_convention", "calibration_version")}})


def _bootstrap_promotion_source(
    prior: VisualOriginalPlan, source: dict[str, JSONValue],
    budget: dict[str, JSONValue], observation: JSONValue, descriptor: str,
) -> None:
    """Rebuild the compiler's source policy, without a lease issuer or UTC fill."""
    from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency
    from cloud_edge_robot_arm.edge.evidence.conditions import ConditionSpec
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.owner_registration import OriginalActionRequirements
    from cloud_edge_robot_arm.vision.worker_owner import (
        REQUIRED_COMPILER_SOURCES, WORKER_CONDITION_REGISTRY,
        WORKER_CONDITION_REGISTRY_VERSION, _POST, _PRE,
    )

    frame = _model(observation, RGBDObservation)
    sources = {name: _sha(value) for name, value in _hashes(source["source_hashes"]).items()}
    if (not REQUIRED_COMPILER_SOURCES <= sources.keys()
            or "src/cloud_edge_robot_arm/repositories/event_autonomy/visual_bootstrap.py" not in sources
            or dict(prior.compiler_source_hashes) != sources or dict(prior.source_hashes) != sources):
        raise ValueError("bootstrap promotion full compiler/source inventory differs")
    if (frame.episode_id != source["episode_id"] or not frame.calibration_version
            or prior.identity.episode_id != frame.episode_id
            or prior.contract.timestamp != prior.registered_at
            or prior.contract.issued_at != prior.registered_at
            or prior.contract.valid_until != prior.effective_deadline_at):
        raise ValueError("bootstrap promotion archived frame/contract source differs")
    contract = prior.contract
    requirements: dict[str, OriginalActionRequirements] = {}
    graph: list[StepDependency] = []
    for index, step in enumerate(contract.steps):
        if step.skill not in _PRE:
            raise ValueError("unsupported bootstrap original skill policy")

        def condition(name: str) -> ConditionSpec:
            if name not in WORKER_CONDITION_REGISTRY:
                raise ValueError("bootstrap original condition has no versioned policy")
            tolerances: dict[str, str | float] = {
                "max_age_s": 5.0, "calibration_version": frame.calibration_version,
                "minimum_safe_height": contract.safety_constraints.minimum_safe_height,
                "condition_registry_version": WORKER_CONDITION_REGISTRY_VERSION,
                "camera_source_descriptor_sha256": descriptor,
            }
            if name == "object_held":
                tolerances["holding_feedback_required"] = True
            if name == "tcp_at_resolved_target":
                tolerances.update(target_reference="grounded_step.parameters.target_pose", max_distance_m=0.02)
            target_id = (contract.task_target.target_region_id
                         if WORKER_CONDITION_REGISTRY[name] == "region"
                         else contract.task_target.object_id)
            return ConditionSpec(name, target_id, tolerances, ("rgbd",))

        requirements[step.step_id] = OriginalActionRequirements(
            step,
            tuple(condition(name) for name in dict.fromkeys((*step.preconditions, *_PRE[step.skill]))),
            tuple(condition(name) for name in dict.fromkeys((
                *step.success_conditions, *_POST[step.skill],
                *(contract.completion_criteria if index == len(contract.steps) - 1 else ()),
            ))),
            0.01, ("rgbd",), 5.0, max(step.timeout_ms, step.expected_duration_ms) / 1000, sources,
        )
        graph.append(StepDependency(
            step.step_id, () if index == 0 else (contract.steps[index - 1].step_id,),
            (frame.observation_id,), f"{step.step_id}:effect", False,
        ))
    if dict(prior.requirements) != requirements or tuple(prior.dependencies) != tuple(graph):
        raise ValueError("bootstrap promotion complete requirements/camera/dependency source differs")
    limits = _object(budget["limits"], LIMIT_FIELDS)
    # The local promotion has no caller retry-pool field: its original retry
    # allocation is derived from this replayed, unrefunded definition state.
    if (_integer(budget["remaining_retries"]) != _integer(limits["max_retries"])
            or _integer(limits["max_retries"]) > contract.failure_policy.local_retry_limit):
        raise ValueError("bootstrap promotion original retry definition/counts differ")


def _history_temporal_source(
    decision: dict[str, JSONValue], prior: dict[str, JSONValue] | None,
    *, maximum_age_ns: int | None = None,
) -> dict[str, JSONValue]:
    current = _bracket(decision["app_current"])
    if prior is not None:
        if current["domain"] != prior["domain"]:
            raise ValueError("history phase evidence domains differ")
        if _integer(current["upper_ns"]) < _integer(prior["lower_ns"]):
            raise ValueError("history phase current precedes causal source lower")
        if maximum_age_ns is not None and _integer(current["upper_ns"]) - _integer(prior["lower_ns"]) > maximum_age_ns:
            raise ValueError("history phase source age is exhausted")
    return current


def _replay_bootstrap(
    state: dict[str, JSONValue], request: dict[str, JSONValue], original: dict[str, JSONValue],
    decision: dict[str, JSONValue], phases: dict[str, dict[str, JSONValue]],
) -> None:
    from cloud_edge_robot_arm.contracts.models import RobotState
    from cloud_edge_robot_arm.vision.observations import RGBDObservation

    source, bootstrap_id, _ = _history_definition(state["definition"], original, bootstrap=True)
    body = _object(request["payload"])
    if body["bootstrap_id"] != bootstrap_id:
        raise ValueError("bootstrap request original identifier differs")
    if state["terminal_reason"] is not None:
        raise ValueError("bootstrap terminal history cannot issue another positive transition")
    budget = _state(state["state"])
    robot = _model(body["robot_state"], RobotState)
    promotion = request["schema_version"] == "visual.bootstrap.promotion.local.v1"
    kind = "PROMOTE" if promotion else _text(body["kind"])
    if robot.estop_engaged or robot.collision_detected or not robot.connected or kind == "STOP":
        if promotion:
            raise ValueError("hard stop prevents bootstrap promotion")
        reason = "bootstrap_stopped" if kind == "STOP" else "hard_safety_fault"
        state["terminal_reason"] = budget["exhausted_reason"] = reason
        state["pending"] = None
        state["state"] = budget
        return
    if decision["disposition"] == "REJECTED":
        raise ValueError("rejected bootstrap evidence cannot describe a positive phase")
    pending = state["pending"]
    if promotion:
        prior = _audit_original(body["original"])
        _join_audit_original(prior, original)
        if (pending is not None or state["planning_source_usable"] is not True
                or state["draft"] is None or state["observation"] is None
                or budget["exhausted_reason"] is not None):
            raise ValueError("bootstrap promotion requires complete usable unexhausted source")
        draft = _object(state["draft"])
        proposal = _proposal_projection(draft, source)
        if proposal is None:
            raise ValueError("bootstrap promotion proposal semantic source invalid")
        actual = _object(_copy(prior.contract.model_dump(mode="json")))
        for name in ("task_id", "plan_version", "command_seq", "timestamp", "issued_at", "valid_until"):
            actual.pop(name)
        aliases = {"visual_target": "object", "visual_destination": "target_region"}
        target = _object(proposal["task_target"])
        for name in ("object_id", "target_region_id"):
            value = target.get(name)
            if isinstance(value, str) and value in aliases:
                target[name] = aliases[value]
        proposal["task_target"] = target
        steps = _array(proposal["steps"])
        for raw_step in steps:
            step = _object(raw_step)
            parameters = _object(step["parameters"])
            for name in ("object_id", "region_id"):
                value = parameters.get(name)
                if isinstance(value, str) and value in aliases:
                    parameters[name] = aliases[value]
            step["parameters"] = parameters
            if not isinstance(raw_step, dict):
                raise ValueError("complete promotion step required")
            raw_step.update(step)
        if (_canonical(actual) != _canonical(proposal)
                or prior.contract.task_id != source["episode_id"]
                or prior.contract.plan_version != 1 or prior.contract.command_seq != 1
                or prior.role_bundle_hash != source["role_bundle_hash"]
                or prior.proposal_hash != state["proposal_hash"]
                or prior.proposal_hash != _hash(draft["parsed_json"])):
            raise ValueError("bootstrap promotion full contract/role/proposal relation differs")
        descriptor = _sha(state["camera_descriptor_hash"])
        _bootstrap_promotion_source(prior, source, budget, state["observation"], descriptor)
        state["terminal_reason"] = "original_adopted"
        state["adopted_original_hash"] = prior.digest()
    elif kind.startswith("RESERVE_"):
        if pending is not None:
            raise ValueError("bootstrap pending claim cannot be replayed or refunded")
        effect: str | None = None
        if kind == "RESERVE_INITIAL_CAPTURE":
            if state["initial_capture_claimed"] is True:
                raise ValueError("bootstrap initial capture already claimed")
            state["initial_capture_claimed"] = True
            effect = "CAPTURE"
        elif kind == "RESERVE_PLAN":
            if state["observation"] is None or state["draft"] is not None:
                raise ValueError("bootstrap plan needs exactly one completed new capture")
            effect = "PLAN"
        elif kind == "RESERVE_REOBSERVATION":
            if state["draft"] is None or state["planning_source_usable"] is True:
                raise ValueError("bootstrap reobservation needs completed unusable plan source")
            limits = _object(budget["limits"])
            no_progress = _integer(budget["consecutive_no_progress"])
            rounds = _integer(budget["verification_rounds"])
            if _integer(budget["remaining_reobservations"]) == 0:
                reason = "reobservation_exhausted"
            elif _integer(limits["max_no_progress"]) == 0 or (rounds > 0 and no_progress + 1 >= _integer(limits["max_no_progress"])):
                reason = "no_progress_exhausted"
            else:
                reason = None
                budget["remaining_reobservations"] = _integer(budget["remaining_reobservations"]) - 1
                budget["consecutive_no_progress"] = no_progress + (1 if rounds > 0 else 0)
                budget["verification_rounds"] = rounds + 1
                conditions = _object(budget["previous_conditions"])
                conditions["bootstrap_plan_source"] = ["UNKNOWN", None]
                budget["previous_conditions"] = conditions
                effect = "CAPTURE"
            if reason is not None:
                state["terminal_reason"] = budget["exhausted_reason"] = reason
        else:
            raise ValueError("unsupported bootstrap reserve phase")
        if effect is not None:
            claim_id = _hash([bootstrap_id, _text(body["expected_record_hash"]), kind])
            state["pending"] = {"claim_id": claim_id, "effect": effect}
            phases[claim_id] = _history_temporal_source(decision, None)
    elif kind == "COMPLETE_CAPTURE":
        claim = _object(pending)
        claim_id = _text(body["claim_id"])
        if claim["effect"] != "CAPTURE" or claim["claim_id"] != claim_id or claim_id not in phases:
            raise ValueError("bootstrap capture completion must bind exact reserved claim")
        _history_temporal_source(decision, phases[claim_id])
        observation = _model(body["observation"], RGBDObservation)
        raw_observation = _object(body["observation"])
        if observation.episode_id != source["episode_id"] or not observation.calibration_version:
            raise ValueError("bootstrap capture episode/calibration source differs")
        descriptor = _camera_descriptor(raw_observation)
        if state["observation"] is not None:
            previous = _model(state["observation"], RGBDObservation)
            if (observation.frame_id == previous.frame_id or observation.captured_at <= previous.captured_at
                    or descriptor != state["camera_descriptor_hash"]):
                raise ValueError("bootstrap capture must retain camera and use a new frame")
        state.update(observation=raw_observation, camera_descriptor_hash=descriptor,
                     draft=None, planning_source_usable=False, proposal_hash=None, pending=None)
    elif kind == "COMPLETE_PLAN":
        claim = _object(pending)
        claim_id = _text(body["claim_id"])
        if claim["effect"] != "PLAN" or claim["claim_id"] != claim_id or claim_id not in phases:
            raise ValueError("bootstrap plan completion must bind exact reserved claim")
        _history_temporal_source(decision, phases[claim_id])
        observation = _model(state["observation"], RGBDObservation)
        draft = _object(body["draft"])
        evidence = _object(draft["observation_evidence"])
        if (any(_canonical(evidence.get(key)) != _canonical(_copy(value))
                for key, value in observation.evidence().items())
                or evidence.get("model_snapshot_hash") != source["model_snapshot_hash"]
                or evidence.get("role_bundle_hash") != source["role_bundle_hash"]):
            raise ValueError("bootstrap plan receipt frame/model/role source differs")
        usable = _proposal_projection(draft, source) is not None
        state.update(draft=draft, planning_source_usable=usable,
                     proposal_hash=_hash(draft["parsed_json"]) if usable else None, pending=None)
    else:
        raise ValueError("unsupported bootstrap replay phase")
    state["state"] = budget


def _replay_supervision(
    state: dict[str, JSONValue], request: dict[str, JSONValue], original: dict[str, JSONValue],
    decision: dict[str, JSONValue], phases: dict[str, dict[str, JSONValue]],
) -> None:
    from cloud_edge_robot_arm.contracts.models import RobotState
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import _bundle
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.supervision import SupervisionContext

    source, task_id, _ = _history_definition(state["definition"], original, bootstrap=False)
    body = _object(request["payload"])
    prior = _audit_original(body["original"])
    _join_audit_original(prior, original)
    if (body["task_id"] != task_id or _hash(body["original"]) != _hash(source["original"])
            or body["role_bundle"] != source["role_bundle"]
            or body["model_snapshot_hash"] != source["model_snapshot_hash"]):
        raise ValueError("supervision frozen task/original/role/model relation differs")
    publication = _audit_publication(body["publication"], prior, enclosing=original)
    checkpoint = _object(publication["checkpoint"])
    step_id = _text(body["step_id"])
    robot = _model(body["robot_state"], RobotState)
    pool = _audit_pool(publication["verification_budget"], enclosing=original)
    if (step_id != checkpoint["current_step_id"] or step_id not in prior.requirements
            or step_id in _array(checkpoint["completed_step_ids"])
            or _object(pool["state"])["exhausted_reason"] is not None
            or robot.estop_engaged or robot.collision_detected or not robot.connected
            or decision["disposition"] == "REJECTED"):
        raise ValueError("supervision current step/safety/budget source invalid")
    cursor = _integer(body["cursor"], positive=True)
    kind = _text(body["kind"])
    claim_id = _hash(["visual.supervision.claim.v1", body["definition_hash"],
                     "WAIT" if "WAIT" in kind else "SUPERVISION", cursor])
    claims = _object(state["claims"])
    if kind in {"RESERVE_CAPTURE", "RESERVE_WAIT"}:
        if claim_id in claims:
            raise ValueError("supervision source claim cannot reserve again")
        cloud = _bundle(_object(source["role_bundle"])).cloud_snapshot
        claim: dict[str, JSONValue] = {
            "kind": "WAIT" if kind == "RESERVE_WAIT" else "SUPERVISION", "cursor": cursor,
            "step_id": step_id, "publication_hash": publication["publication_hash"],
            "checkpoint_hash": checkpoint["checkpoint_hash"],
            "state_generation": publication["state_generation"], "observation": None,
            "context": None, "decision": None, "model_snapshot_hash": body["model_snapshot_hash"],
            "cloud_snapshot": _object(source["role_bundle"])["cloud_snapshot"],
            "cloud_snapshot_hash": cloud.digest(), "source_hashes": _copy(dict(prior.source_hashes)),
            "wait_duration_s": None, "wait_elapsed_s": None,
        }
        current = _history_temporal_source(decision, None)
        if kind == "RESERVE_CAPTURE":
            period = source["supervision_period_s"]
            if (period is None or cursor <= _integer(state["last_capture_cursor"])
                    or cursor > _integer(state["max_periodic_captures"])
                    or _integer(state["captures_reserved"]) >= _integer(state["max_periodic_captures"])):
                raise ValueError("supervision periodic capture original allowance unavailable")
            hard = _object(_array(_object(original["verification_reference"])["hard_deadlines"])[0])
            origin = _integer(hard["deadline_ns"]) - _integer(hard["budget_ns"])
            if _integer(current["upper_ns"]) - origin < cursor * _number(period, positive=True) * 1_000_000_000:
                raise ValueError("supervision capture precedes original cadence source lower")
            state["captures_reserved"] = _integer(state["captures_reserved"]) + 1
            state["last_capture_cursor"] = cursor
            claim["status"] = "CAPTURE_PENDING"
        else:
            duration = _number(body["wait_duration_s"], positive=True)
            lengths = [_integer(_object(item)["budget_ns"], positive=True)
                       for item in _array(_object(original["verification_reference"])["hard_deadlines"])]
            window = min(lengths) / 1_000_000_000
            raw_definition = _object(state["definition"])
            if raw_definition["schema_version"] == "visual.supervision.definition.v1":
                start = datetime.fromisoformat(_text(source["task_started_at"]))
                window = min(window, (prior.effective_deadline_at - start).total_seconds())
            reserved = _number(state["wait_seconds_reserved"])
            if cursor <= _integer(state["last_wait_cursor"]) or reserved + duration > window:
                raise ValueError("supervision original wait allocation/cursor exhausted")
            state["wait_seconds_reserved"] = reserved + duration
            state["last_wait_cursor"] = cursor
            claim.update(status="WAIT_PENDING", wait_duration_s=duration)
        claims[claim_id] = claim
        phases[claim_id] = current
    else:
        if body["claim_id"] != claim_id or claim_id not in claims:
            raise ValueError("supervision completion must retain deterministic owned claim")
        claim = _object(claims[claim_id])
        if (claim["step_id"] != step_id or claim["publication_hash"] != publication["publication_hash"]
                or claim["checkpoint_hash"] != checkpoint["checkpoint_hash"]):
            raise ValueError("supervision claim source context cannot be rebound")
        requirement = prior.requirements[step_id]
        current = _history_temporal_source(
            decision, phases.get(claim_id),
            maximum_age_ns=int(requirement.ordinary_ttl_s * 1_000_000_000)
            if kind in {"RESERVE_PLAN", "COMPLETE_PLAN"} else None)
        if kind == "COMPLETE_CAPTURE":
            if claim["status"] != "CAPTURE_PENDING":
                raise ValueError("supervision capture claim not pending")
            observation = _model(body["observation"], RGBDObservation)
            context = _model(body["context"], SupervisionContext)
            if (observation.episode_id != prior.identity.episode_id or not observation.calibration_version
                    or context.episode_id != observation.episode_id
                    or context.plan_version != prior.contract.plan_version
                    or context.state_version != publication["state_generation"]
                    or context.next_step_id != step_id
                    or context.next_skill != requirement.original_step.skill.value
                    or context.observation_id != observation.observation_id
                    or context.captured_at != observation.captured_at):
                raise ValueError("supervision capture receipt exact frame/step/context differs")
            descriptor = _camera_descriptor(_object(body["observation"]))
            for condition in (*requirement.preconditions, *requirement.postconditions):
                wanted = condition.tolerances.get("camera_source_descriptor_sha256")
                calibration = condition.tolerances.get("calibration_version")
                if (wanted is not None and wanted != descriptor) or (
                        calibration is not None and calibration != observation.calibration_version):
                    raise ValueError("supervision original camera/calibration policy differs")
            if publication["grounding"] is not None:
                grounding = _object(publication["grounding"])
                if grounding.get("schema_version") == "visual.owner.grounding.local.v1":
                    grounding = decode_local_payload(grounding, "visual.owner.grounding.local.v1").semantic
                if grounding["calibration_version"] != observation.calibration_version:
                    raise ValueError("supervision current grounded calibration changed")
            if any(_object(item)["observation"] is not None
                   and _object(_object(item)["observation"])["observation_id"] == observation.observation_id
                   for item in claims.values()):
                raise ValueError("supervision frame cannot bind a second source claim")
            claim.update(status="CAPTURED", observation=body["observation"], context=body["context"])
            phases[claim_id] = current
        elif kind == "RESERVE_PLAN":
            if claim["status"] != "CAPTURED" or _integer(state["supervisor_calls_reserved"]) >= _integer(state["max_supervisor_calls"]):
                raise ValueError("supervision planning original allowance/frame unavailable")
            state["supervisor_calls_reserved"] = _integer(state["supervisor_calls_reserved"]) + 1
            claim["status"] = "PLAN_PENDING"
        elif kind == "COMPLETE_PLAN":
            if claim["status"] != "PLAN_PENDING":
                raise ValueError("supervision planning claim not pending")
            context = _object(claim["context"])
            result = _object(body["decision"])
            if any(result[name] != context[name] for name in (
                    "episode_id", "plan_version", "state_version", "observation_id", "next_step_id")):
                raise ValueError("supervision planning receipt changed captured source context")
            claim.update(status="PLAN_COMPLETE", decision=result)
        elif kind == "COMPLETE_WAIT":
            if claim["status"] != "WAIT_PENDING" or _number(body["wait_elapsed_s"]) > _number(claim["wait_duration_s"], positive=True):
                raise ValueError("supervision wait completion original allocation differs")
            claim.update(status="WAIT_COMPLETE", wait_elapsed_s=body["wait_elapsed_s"])
        else:
            raise ValueError("unsupported supervision replay phase")
        claims[claim_id] = claim
    state["claims"] = claims


def _archive_history(value: JSONValue, original: dict[str, JSONValue], *, bootstrap: bool) -> int:
    """New D histories and explicitly preserved legacy audit history stay distinct."""
    from cloud_edge_robot_arm.contracts.models import RecoveryBudget
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import (
        VisualBootstrapPromotionInput, VisualBootstrapTransitionInput,
    )
    events = _array(value)
    keys: set[str] = set()
    for item in events:
        event = _object(item)
        if set(event) == {"request", "committed_at"} or (bootstrap and set(event) == {"promotion", "state", "retry", "committed_at"}):
            # These untouched UTC inputs are archival source evidence only.
            stamp = datetime.fromisoformat(_text(event["committed_at"]))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("aware historical audit timestamp required")
            if "promotion" in event:
                request_raw = _object(event["promotion"])
                VisualBootstrapPromotionInput.from_payload(request_raw)
                _model(event["retry"], RecoveryBudget)
                _object(event["state"])
            else:
                request_raw = _object(event["request"])
                if bootstrap:
                    VisualBootstrapTransitionInput.from_payload(request_raw)
                else:
                    # Do not replay the legacy publication codec's current-UTC gate.
                    expected = FIELDS["visual.supervision.transition.local.v1"] | {"schema_version", "lease"}
                    _object(request_raw, expected)
                    if request_raw["schema_version"] != "visual.supervision.transition.v1":
                        raise ValueError("exact preserved supervision audit request required")
                    from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import _lease
                    _lease(_object(request_raw["lease"]))
                    semantic = {name: request_raw[name] for name in FIELDS["visual.supervision.transition.local.v1"]}
                    _semantic("visual.supervision.transition.local.v1", semantic, original, {"utc": {}, "monotonic": None})
            key = _text(request_raw["event_key"])
        else:
            raise ValueError("complete new history or exact preserved legacy audit event required")
        if key in keys:
            raise ValueError("historical event identity cannot be replayed")
        keys.add(key)
    return len(events)


def _history(
    value: JSONValue, original: dict[str, JSONValue], *, bootstrap: bool,
    body: dict[str, JSONValue], decision: dict[str, JSONValue] | None,
    transaction: dict[str, JSONValue] | None,
) -> int:
    events = _array(value)
    archival = [{"request", "committed_at"}]
    if bootstrap:
        archival.append({"promotion", "state", "retry", "committed_at"})
    shapes = [set(_object(event)) for event in events]
    if shapes and all(shape in archival for shape in shapes):
        if decision is not None and decision["disposition"] == "VALID":
            raise ValueError("legacy archival history cannot become current VALID local evidence")
        return _archive_history(value, original, bootstrap=bootstrap)
    if any(shape in archival for shape in shapes):
        raise ValueError("mixed archival/local history cannot implicitly promote sources")
    if any(shape != {"request", "decision", "transaction", "resulting_record_hash"} for shape in shapes):
        raise ValueError("four-field local history event required")
    tag = "visual.bootstrap.record.local.v1" if bootstrap else "visual.supervision.record.local.v1"
    state = _initial_history_state(body["definition"], original, bootstrap=bootstrap)
    phases: dict[str, dict[str, JSONValue]] = {}
    ids: set[str] = set()
    for raw_event in events:
        event = _object(raw_event)
        raw_request = _object(event["request"])
        allowed = {"visual.bootstrap.transition.local.v1", "visual.bootstrap.promotion.local.v1"} if bootstrap else {"visual.supervision.transition.local.v1"}
        if raw_request.get("schema_version") not in allowed:
            raise ValueError("history request kind/tag differs from its record domain")
        request = LocalEnvelope.from_payload(raw_request)
        if request.local_time.to_payload() != original:
            raise ValueError("history request original reference differs")
        request_body = request.semantic
        event_id = request.string("event_key")
        if event_id in ids:
            raise ValueError("history event identity cannot be replayed")
        ids.add(event_id)
        revision = _integer(state["revision"])
        pre_hash = _history_state_hash(tag, state, original)
        if (request_body["expected_record_hash"] != pre_hash
                or request_body["definition_hash"] != _hash(body["definition"])):
            raise ValueError("history request definition/CAS prestate hash differs")
        if not bootstrap and request_body["expected_revision"] != revision:
            raise ValueError("supervision history skipped or reordered revision")
        current_decision = _decision(event["decision"])
        current_transaction = _transaction(event["transaction"])
        _join_decision(original, current_decision)
        operation = _hash({"schema_version": "visual.local-history-operation.v1",
                           "request": semantic_projection(raw_request)})
        if any(evidence["operation_id"] != event_id or evidence["operation_sha256"] != operation
               for evidence in (current_decision, current_transaction)):
            raise ValueError("history operation digest/id must bind exact request")
        for target, source in (
            ("job_id", "job_id"), ("attempt", "attempt"), ("lease_id", "lease_id"),
            ("epoch", "lease_epoch"), ("generation", "lease_generation"),
            ("row_revision", "lease_row_revision"),
        ):
            if current_transaction[target] != current_decision[source]:
                raise ValueError("history transaction original task/fence/current generation differs")
        if (current_transaction["event_key"] != event_id
                or current_transaction["event_kind"] != raw_request["schema_version"]
                or current_transaction["expected_event_revision"] != revision
                or current_transaction["event_revision"] != revision + 1):
            raise ValueError("history transaction event kind/id/CAS revision differs")
        if bootstrap:
            _replay_bootstrap(state, raw_request, original, current_decision, phases)
        else:
            _replay_supervision(state, raw_request, original, current_decision, phases)
        state["revision"] = revision + 1
        result = _history_state_hash(tag, state, original)
        if event["resulting_record_hash"] != result or current_transaction["event_record_hash"] != result:
            raise ValueError("history result hash differs from computed poststate")
        history = _array(state["history"])
        history.append(event)
        state["history"] = history
    expected = dict(state)
    declared = dict(body)
    expected.pop("history")
    declared.pop("history")
    if _canonical(expected) != _canonical(declared):
        raise ValueError("history final semantic state differs from definition-derived replay")
    if events:
        final = _object(events[-1])
        if decision != final["decision"] or transaction != final["transaction"]:
            raise ValueError("enclosing history decision/transaction differs from final event")
    return len(events)


def _semantic(
    tag: str, body: dict[str, JSONValue], original: dict[str, JSONValue],
    diagnostics: dict[str, JSONValue], *, evidence_decision: dict[str, JSONValue] | None = None,
    evidence_transaction: dict[str, JSONValue] | None = None,
) -> None:
    from cloud_edge_robot_arm.cloud.planning.models import PlannerDraft
    from cloud_edge_robot_arm.cloud.replanning.visual_dependencies import StepDependency, find_repair_window
    from cloud_edge_robot_arm.contracts.models import RobotState, SkillExecutionResult, TaskContract, TaskStep
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_bootstrap import VisualBootstrapDefinition
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import requirement_from_payload
    from cloud_edge_robot_arm.repositories.event_autonomy.visual_supervision import _bundle
    from cloud_edge_robot_arm.vision.observations import RGBDObservation
    from cloud_edge_robot_arm.vision.owner_registration import local_owner_identity
    from cloud_edge_robot_arm.vision.supervision import SupervisionContext, SupervisionDecision

    scope = body.get("scope")
    expected_scope = "BOOTSTRAP_SOURCE_ONLY" if tag.startswith("visual.bootstrap.") else "SUPERVISION_SOURCE_ONLY" if tag.startswith("visual.supervision.") else "SOURCE_ROUTE_ONLY"
    if "scope" in FIELDS[tag] and scope != expected_scope:
        raise ValueError("exact detached semantic scope required")
    if "binding_scope" in body and body["binding_scope"] != ("DURABLE_BINDING_ONLY" if tag == "visual.owner.publication.local.v1" else "SOURCE_BINDING_ONLY"):
        raise ValueError("exact source binding scope required")
    for name, value in body.items():
        if (name.endswith("_hash") or name.endswith("_sha256")) and value is not None:
            _sha(value)
        if name in {"revision", "owner_revision", "state_generation", "expected_revision", "attempt", "plan_version", "command_seq", "cursor", "max_periodic_captures", "max_supervisor_calls", "captures_reserved", "supervisor_calls_reserved", "last_capture_cursor", "last_wait_cursor"}:
            _integer(value)
        if name in {"task_id", "step_id", "event_key", "bootstrap_id", "observation_id", "calibration_version", "plan_id", "robot_id", "before_observation_id"}:
            _text(value)
        if name in {"initial_capture_claimed", "planning_source_usable"} and type(value) is not bool:
            raise ValueError("strict semantic boolean required")
    if "robot_state" in body:
        _model(body["robot_state"], RobotState)
    if body.get("observation") is not None:
        _model(body["observation"], RGBDObservation)
    if body.get("draft") is not None:
        _model(body["draft"], PlannerDraft)
    if "state" in body:
        state = _state(body["state"])
        if state["original_budget_reference"] != original["verification_reference"]:
            raise ValueError("budget must retain exact immutable original reference")
    if tag == "visual.bootstrap.definition.local.v1":
        from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget
        limits = _object(body["verification_limits"], LIMIT_FIELDS)
        VerificationBudget(_integer(limits["max_reobservations"]), _integer(limits["max_retries"]), _integer(limits["max_no_progress"]), _number(limits["deadline_s"], positive=True))
        _number(body["task_timeout_s"], positive=True)
        _text(body["episode_id"]); _text(body["user_instruction"])
        _hashes(body["source_hashes"])
        if body["source_hashes"] != original["source_hashes"]:
            raise ValueError("bootstrap source inventory changed")
    if tag == "visual.bootstrap.record.local.v1":
        definition = VisualBootstrapDefinition.from_payload(_object(body["definition"]))
        state = _state(body["state"])
        limits = _object(state["limits"])
        if (limits["max_reobservations"], limits["max_retries"], limits["max_no_progress"], limits["deadline_s"]) != (definition.verification_limits.max_reobservations, definition.verification_limits.max_retries, definition.verification_limits.max_no_progress, definition.verification_limits.deadline_s):
            raise ValueError("bootstrap cannot replace original budget policy")
        if _integer(body["revision"]) != _history(
            body["history"], original, bootstrap=True, body=body,
            decision=evidence_decision, transaction=evidence_transaction,
        ):
            raise ValueError("bootstrap revision/history count differs")
        pending = body["pending"]
        if pending is not None:
            item = _object(pending)
            _sha(item["claim_id"])
            if item["effect"] not in {"CAPTURE", "PLAN"}:
                raise ValueError("exact pending bootstrap effect required")
        for name in ("terminal_reason", "adopted_original_hash", "camera_descriptor_hash", "proposal_hash"):
            if body[name] is not None:
                _text(body[name])
    if tag == "visual.bootstrap.transition.local.v1":
        kind = body["kind"]
        if kind not in {"RESERVE_INITIAL_CAPTURE", "COMPLETE_CAPTURE", "RESERVE_PLAN", "COMPLETE_PLAN", "RESERVE_REOBSERVATION", "STOP"}:
            raise ValueError("exact bootstrap transition kind required")
        if (kind == "COMPLETE_CAPTURE") != (body["observation"] is not None) or (kind == "COMPLETE_PLAN") != (body["draft"] is not None):
            raise ValueError("exact bootstrap phase-specific source required")
        if (kind in {"COMPLETE_CAPTURE", "COMPLETE_PLAN"}) != (body["claim_id"] is not None):
            raise ValueError("completed bootstrap source must bind its exact claim")
        if body["claim_id"] is not None:
            _sha(body["claim_id"])
    if tag == "visual.bootstrap.promotion.local.v1":
        promoted = _audit_original(body["original"])
        if _object(original["contract_provenance"])["content_sha256"] != _hash(_copy(promoted.contract.model_dump(mode="json"))):
            raise ValueError("promotion must preserve the original contract source")
    if tag.startswith("visual.supervision."):
        if tag.endswith(".definition.local.v1") or tag.endswith(".transition.local.v1"):
            prior = _audit_original(body["original"])
            _join_audit_original(prior, original)
            _audit_publication(body["publication"], prior, enclosing=original)
            if _bundle(_object(body["role_bundle"])).digest() != prior.role_bundle_hash:
                raise ValueError("supervision must preserve the original role policy")
        if tag.endswith(".definition.local.v1"):
            _number(body["task_timeout_s"], positive=True)
            if body["supervision_period_s"] is not None:
                _number(body["supervision_period_s"], positive=True)
        elif tag.endswith(".transition.local.v1"):
            if _integer(body["cursor"], positive=True) < 1:
                raise ValueError("positive supervision cursor required")
            kind = _text(body["kind"])
            required_by_kind = {
                "RESERVE_CAPTURE": set(), "COMPLETE_CAPTURE": {"claim_id", "observation", "context"},
                "RESERVE_PLAN": {"claim_id"}, "COMPLETE_PLAN": {"claim_id", "decision"},
                "RESERVE_WAIT": {"wait_duration_s"}, "COMPLETE_WAIT": {"claim_id", "wait_elapsed_s"},
            }
            if kind not in required_by_kind:
                raise ValueError("exact supervision phase required")
            optional = {"claim_id", "observation", "context", "decision", "wait_duration_s", "wait_elapsed_s"}
            if {name for name in optional if body[name] is not None} != required_by_kind[kind]:
                raise ValueError("exact phase-specific supervision source required")
            if body["claim_id"] is not None:
                _sha(body["claim_id"])
            if body["context"] is not None:
                _model(body["context"], SupervisionContext)
            if body["decision"] is not None:
                _model(body["decision"], SupervisionDecision)
            if body["wait_duration_s"] is not None:
                _number(body["wait_duration_s"], positive=True)
            if body["wait_elapsed_s"] is not None:
                _number(body["wait_elapsed_s"])
            if body["task_id"] != prior.identity.task_id:
                raise ValueError("supervision task binding differs")
        else:
            _, maximum = _audit_supervision_definition(body["definition"])
            if body["max_periodic_captures"] != maximum or body["max_supervisor_calls"] != maximum:
                raise ValueError("supervision limits must retain original cadence")
            if _integer(body["captures_reserved"]) > maximum or _integer(body["supervisor_calls_reserved"]) > maximum:
                raise ValueError("supervision cannot refill or exceed frozen allowances")
            _number(body["wait_seconds_reserved"])
            for key, claim in _object(body["claims"]).items():
                _sha(key); _object(claim)
            if body["revision"] != _history(
                body["history"], original, bootstrap=False, body=body,
                decision=evidence_decision, transaction=evidence_transaction,
            ):
                raise ValueError("supervision revision/history count differs")
    if tag == "visual.owner.original.local.v1":
        contract = _model(body["contract"], TaskContract)
        identity = local_owner_identity(_object(body["identity"]))
        if body["contract_provenance"] != original["contract_provenance"] or _object(body["contract_provenance"])["content_sha256"] != _hash(body["contract"]):
            raise ValueError("original contract provenance/content changed")
        if identity.task_id != contract.task_id:
            raise ValueError("semantic task identity changed")
        requirements = _object(body["requirements"])
        if set(requirements) != {step.step_id for step in contract.steps}:
            raise ValueError("complete immutable action requirements required")
        hashes = _hashes(body["source_hashes"])
        compiler = _hashes(body["compiler_source_hashes"])
        if hashes != original["source_hashes"] or any(hashes.get(name) != value for name, value in compiler.items()):
            raise ValueError("original/compiler source inventory changed")
        for step in contract.steps:
            requirement = requirement_from_payload(_object(requirements[step.step_id]))
            if requirement.original_step.model_dump(mode="json") != step.model_dump(mode="json"):
                raise ValueError("original action policy changed")
            if any(hashes.get(name) != value for name, value in requirement.policy_source_hashes.items()):
                raise ValueError("original requirement policy/source changed")
            if any(condition.target_id is not None and condition.target_id not in {contract.task_target.object_id, contract.task_target.target_region_id} for condition in (*requirement.preconditions, *requirement.postconditions)):
                raise ValueError("original condition target changed")
        graph: list[StepDependency] = []
        for raw in _array(body["dependencies"]):
            item = _object(raw, frozenset("step_id depends_on evidence_ids physical_effect_id completed".split()))
            completed = item["completed"]
            if type(completed) is not bool:
                raise ValueError("strict dependency completion required")
            effect = item["physical_effect_id"]
            graph.append(StepDependency(_text(item["step_id"]), tuple(_text(value) for value in _array(item["depends_on"])), tuple(_text(value) for value in _array(item["evidence_ids"])), None if effect is None else _text(effect), completed))
        if [item.step_id for item in graph] != [step.step_id for step in contract.steps]:
            raise ValueError("complete ordered original dependency graph required")
        find_repair_window(graph, set(), expected_plan_version=contract.plan_version, expected_command_seq=contract.command_seq)
        lease = _object(original["lease_identity"])
        if (identity.job_id, identity.run_id, identity.worker_id, identity.lease_id, identity.attempt, identity.owner_epoch) != (lease["job_id"], lease["run_id"], lease["worker_id"], lease["lease_id"], lease["attempt"], lease["epoch"]):
            raise ValueError("original job/fence/epoch changed")
    if tag == "visual.owner.grounding.local.v1":
        identity = local_owner_identity(_object(body["current_identity"]))
        lease = _object(original["lease_identity"])
        if (identity.job_id, identity.run_id, identity.worker_id, identity.lease_id, identity.attempt, identity.owner_epoch) != (lease["job_id"], lease["run_id"], lease["worker_id"], lease["lease_id"], lease["attempt"], lease["epoch"]):
            raise ValueError("grounding cannot replace original job/fence/epoch")
        step = _model(body["grounded_step"], TaskStep)
        requirement = requirement_from_payload(_object(body["original_requirements"]))
        prior_step = requirement.original_step
        if (step.step_id, step.skill, step.timeout_ms, step.retry_limit, step.expected_duration_ms) != (prior_step.step_id, prior_step.skill, prior_step.timeout_ms, prior_step.retry_limit, prior_step.expected_duration_ms) or step.preconditions or step.success_conditions:
            raise ValueError("grounding cannot replace original action policy")
        if _number(body["expected_duration_s"], positive=True) < requirement.expected_duration_s:
            raise ValueError("grounding cannot shorten immutable horizon")
        _hashes(body["grounding_source_hashes"])
    if tag == "visual.owner.publication.local.v1":
        _publication_body(body, local_original=original)
        if _sha(body["publication_hash"]) != _local_publication_hash(body, original):
            raise ValueError("local publication canonical content hash differs")
    if tag == "visual.verification.route-input.local.v1":
        prior = _audit_original(body["original"])
        _join_audit_original(prior, original)
        _audit_publication(body["publication"], prior, enclosing=original)
        online = _object(body["online"], frozenset("observation robot_state visual_facts plan_version command_seq context_hash".split()))
        _model(online["observation"], RGBDObservation); _model(online["robot_state"], RobotState)
        _object(online["visual_facts"]); _integer(online["plan_version"]); _integer(online["command_seq"]); _sha(online["context_hash"])
        _model(body["execution_contract"], TaskContract)
        if body["phase"] not in {"PRECONDITION", "NATIVE_PRE_SAFETY", "NATIVE_PRE_SKILL", "CLOUD_RETURN", "AFTER_EFFECT", "POST_HOLD", "TERMINAL"} or _integer(body["attempt"], positive=True) < 1:
            raise ValueError("exact verification phase/attempt required")
        if body["completion"] is not None:
            from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import VisualEffectCompletion
            VisualEffectCompletion.from_payload(_object(body["completion"]))
            _semantic_child_original(body["completion"], "visual.verification.effect-completion.local.v1", original)
        if body["grounding_receipt"] is not None:
            from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import grounding_from_payload
            grounding_from_payload(_object(body["grounding_receipt"]))
            _semantic_child_original(body["grounding_receipt"], "visual.owner.grounding.local.v1", original)
    if tag == "visual.verification.route.local.v1":
        from cloud_edge_robot_arm.auto_mode.runtime_events import DecisionAction
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_verification import PHASES
        request = _object(body["input"])
        if request.get("schema_version") == "visual.verification.route-input.local.v1":
            _semantic_child_original(request, "visual.verification.route-input.local.v1", original)
        else:
            _audit_original(request["original"])
            _audit_publication(request["publication"])
            if request["phase"] not in PHASES:
                raise ValueError("exact historical route phase required")
        if body["input_hash"] != _hash(request):
            raise ValueError("route input content hash differs")
        if body["semantic_hash"] != route_semantic_hash(request):
            raise ValueError("route semantic hash differs from exact request")
        if body["source_key"] != route_source_key(request):
            raise ValueError("route source key differs from original request sources")
        DecisionAction(_text(body["route"]))
        for reason in _array(body["reasons"]):
            _text(reason)
        for verdict in _array(body["verdicts"]):
            item = _object(verdict, frozenset("condition_name status reasons observation_id measured_values".split()))
            _text(item["condition_name"]); _text(item["observation_id"]); _object(item["measured_values"])
            if item["status"] not in {"PASS", "FAIL", "UNKNOWN"}:
                raise ValueError("exact condition verdict status required")
            for reason in _array(item["reasons"]):
                _text(reason)
        _object(body["context_domains"], frozenset("source native evidence".split()))
        for domain_name in _object(body["context_domains"]).values():
            _text(domain_name)
        before_pool = _audit_pool(body["before_verification_budget"], enclosing=original)
        after_pool = _audit_pool(body["after_verification_budget"], enclosing=original)
        before_state = _object(before_pool["state"])
        after_state = _object(after_pool["state"])
        if before_pool["task_id"] != after_pool["task_id"] or _integer(after_pool["revision"]) != _integer(before_pool["revision"]) + 1:
            raise ValueError("route must bind exact task budget CAS revisions")
        for counter_name in ("remaining_reobservations", "remaining_retries"):
            if _integer(after_state[counter_name]) > _integer(before_state[counter_name]):
                raise ValueError("route history cannot refund a consumed allowance")
        before_limits = _object(before_state["limits"])
        after_limits = _object(after_state["limits"])
        for limit_name in LIMIT_FIELDS:
            if _number(after_limits[limit_name]) > _number(before_limits[limit_name]):
                raise ValueError("route cannot extend an original budget policy")
        if body["produced_publication"] is not None:
            produced = _audit_publication(body["produced_publication"], enclosing=original)
            if body["produced_publication_hash"] != produced["publication_hash"]:
                raise ValueError("route produced publication hash differs")
    if tag == "visual.verification.effect-completion.local.v1":
        result = _model(body["result"], SkillExecutionResult)
        if (result.task_id, result.step_id, result.plan_version, result.command_seq) != (body["task_id"], body["step_id"], body["plan_version"], body["command_seq"]):
            raise ValueError("effect result/source identity changed")
        _integer(body["attempt"], positive=True); _hashes(body["source_hashes"])
    if tag == "recovery.verification-budget.local.v1":
        binding = {"schema_version": tag, "task_id": body["task_id"], "state": body["state"], "revision": body["revision"]}
        if body["content_hash"] != _hash(binding):
            raise ValueError("new budget hash must cover new schema/task/state/revision")
    if tag == "recovery.retry-budget.local.v1":
        _text(body["budget_id"]); _text(body["task_id"]); _text(body["retry_backoff_policy"])
        for name in ("per_step_retry_limit", "per_skill_retry_limit", "task_total_retry_limit", "retry_count_used", "task_retry_count", "retry_cooldown_ms", "effective_retry_limit", "remaining_retries", "scene_version"):
            _integer(body[name])
        for name in ("step_retry_counts", "skill_retry_counts", "event_retry_counts"):
            for key, count in _object(body[name]).items():
                _text(key); _integer(count)
        if body["retry_count_used"] != body["task_retry_count"] or _integer(body["remaining_retries"]) > min(_integer(body["effective_retry_limit"]), _integer(body["task_total_retry_limit"]) - _integer(body["task_retry_count"])):
            raise ValueError("retry history cannot refill the original pool")


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


class _StrictDetachedValue(_DetachedValue):
    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("immutable detached value")


class LocalOriginalTime(_StrictDetachedValue):
    _kind = "original"


class LocalAuthorityDecision(_StrictDetachedValue):
    _kind = "decision"


class LocalTransactionReceipt(_StrictDetachedValue):
    _kind = "transaction"


class LocalVerificationBudgetState(_StrictDetachedValue):
    _kind = "state"

    @property
    def limits(self) -> VerificationBudget:
        from cloud_edge_robot_arm.edge.recovery.verification_router import VerificationBudget

        values = _object(self.to_payload()["limits"])
        return VerificationBudget(
            _integer(values["max_reobservations"]), _integer(values["max_retries"]),
            _integer(values["max_no_progress"]), _number(values["deadline_s"], positive=True),
        )

    @property
    def remaining_reobservations(self) -> int:
        return _integer(self.to_payload()["remaining_reobservations"])

    @property
    def remaining_retries(self) -> int:
        return _integer(self.to_payload()["remaining_retries"])

    @property
    def consecutive_no_progress(self) -> int:
        return _integer(self.to_payload()["consecutive_no_progress"])

    @property
    def verification_rounds(self) -> int:
        return _integer(self.to_payload()["verification_rounds"])

    @property
    def previous_conditions(self) -> dict[str, tuple[str, float | None]]:
        conditions: dict[str, tuple[str, float | None]] = {}
        for name, raw in _object(self.to_payload()["previous_conditions"]).items():
            pair = _array(raw)
            conditions[name] = (_text(pair[0]), None if pair[1] is None else _number(pair[1]))
        return conditions

    @property
    def exhausted_reason(self) -> str | None:
        value = self.to_payload()["exhausted_reason"]
        return None if value is None else _text(value)

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
        decision: dict[str, JSONValue] | None = None
        transaction: dict[str, JSONValue] | None = None
        if original_or_request:
            if raw["decision"] is not None or raw["transaction"] is not None:
                raise ValueError("original/request cannot self-install a current decision")
        else:
            decision = _decision(raw["decision"])
            transaction = _transaction(raw["transaction"])
            _join_decision(original, decision)
            for current_name, decision_name in (("operation_id", "operation_id"), ("operation_sha256", "operation_sha256"), ("job_id", "job_id"), ("attempt", "attempt"), ("lease_id", "lease_id"), ("epoch", "lease_epoch"), ("generation", "lease_generation"), ("row_revision", "lease_row_revision")):
                if transaction[current_name] != decision[decision_name]:
                    raise ValueError("transaction and two-authority evidence disagree")
        _semantic(tag, body, original, diagnostics,
                  evidence_decision=decision, evidence_transaction=transaction)
        _validate_nested_local(body)
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

    def __setattr__(self, name: str, value: object) -> None:
        raise TypeError("immutable detached domain carrier")

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
