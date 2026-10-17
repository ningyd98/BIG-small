"""R196 detached promotion/original/task regressions; no live authority fixture."""

import copy
import hashlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests import test_operational_runtime_closure as _frozen


def _r196_plain(value):
    return json.loads(json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")))


def _r196_hash(value):
    return hashlib.sha256(json.dumps(
        value, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


@contextmanager
def _r196_case(request, tmp_path, category):
    evidence = {
        "schema_version": "bigsmall.r196-case.v1", "nodeid": request.node.nodeid,
        "category": category, "decoder_calls": [], "baseline_payload": None,
        "changed_payload": None, "mutation": None,
        "hash_kind": "CANONICAL_RAW_ENVELOPE_SHA256",
        "no_live_authority_created_by_test": True,
    }
    try:
        yield evidence
    finally:
        kind, error, _ = sys.exc_info()
        evidence["test_exit_exception"] = None if kind is None else {
            "type": kind.__name__, "message": str(error),
        }
        for key in ("baseline_payload", "changed_payload"):
            evidence[key + "_sha256"] = (
                None if evidence[key] is None else _r196_hash(evidence[key])
            )
        sink = os.environ.get("BIGSMALL_R175_RESOURCE_DIR")
        directory = Path(sink).parent / "cases" if sink else tmp_path / "cases"
        directory.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha256(request.node.nodeid.encode()).hexdigest() + ".json"
        with (directory / name).open("x", encoding="utf-8") as stream:
            json.dump(evidence, stream, allow_nan=False, sort_keys=True, indent=2)
            stream.write("\n")


def _r196_decode(raw, evidence, label):
    from cloud_edge_robot_arm.vision.local_temporal import LocalEnvelope

    observation = {"label": label, "raw_sha256": _r196_hash(raw),
                   "entry": "LocalEnvelope.from_payload -> frozen concrete domain decoder"}
    evidence["decoder_calls"].append(observation)
    try:
        generic = LocalEnvelope.from_payload(copy.deepcopy(raw))
        domain = _frozen._b_decode_domain(raw["schema_version"], copy.deepcopy(raw))
    except ValueError as error:
        observation.update(returned=False, exception_type="ValueError", message=str(error))
        raise
    assert generic.to_payload() == raw
    assert domain.to_payload() == raw
    observation.update(returned=True, exception_type=None, message=None)
    return domain


def _r196_local_original(legacy, original):
    raw = _r196_plain(legacy.to_payload())
    names = ("binding_scope", "identity", "contract", "proposal_hash", "role_bundle_hash",
             "compiler_source_hashes", "source_hashes", "requirements", "dependencies")
    body = {name: copy.deepcopy(raw[name]) for name in names}
    body["contract_provenance"] = copy.deepcopy(original["contract_provenance"])
    return {"schema_version": "visual.owner.original.local.v1", "payload": body,
            "original_time": copy.deepcopy(original), "decision": None, "transaction": None,
            "diagnostics": {"utc": {}, "monotonic": None}}


def _r196_alternate_original(raw):
    changed = copy.deepcopy(raw)
    original = changed["original_time"]
    previous = original["verification_reference"]["window_id"]
    replacement = previous + ":r196-independent-valid-window"
    original["verification_reference"]["window_id"] = replacement
    for name in ("task_reference", "verification_reference", "recovery_reference"):
        original[name]["parents"] = [
            replacement if parent == previous else parent for parent in original[name]["parents"]
        ]
    return changed


def _r196_publication_original(publication, prior):
    publication["payload"]["original_plan_hash"] = _r196_hash(prior)
    publication["payload"]["publication_hash"] = _frozen._r179_publication_hash(publication)


def _r196_request(fixture, category):
    tags = {
        "route_input": "visual.verification.route-input.local.v1",
        "supervision_definition": "visual.supervision.definition.local.v1",
        "supervision_transition": "visual.supervision.transition.local.v1",
    }
    raw = copy.deepcopy(fixture["cases"][tags[category]])
    body = raw["payload"]
    prior = _r196_local_original(fixture["legacy"]["data"]["original"], raw["original_time"])
    body["original"] = prior
    publication = _frozen._r179_publication(
        body["publication"], raw["original_time"], fixture["current"]
    )
    _r196_publication_original(publication, prior)
    body["publication"] = publication
    return raw


def _r196_commit(previous, request, changed):
    changed["payload"]["revision"] = previous["payload"]["revision"] + 1
    event = _frozen._r179_history_event(previous, request, changed)
    changed["payload"]["history"] = copy.deepcopy(previous["payload"]["history"]) + [event]
    changed["decision"] = copy.deepcopy(event["decision"])
    changed["transaction"] = copy.deepcopy(event["transaction"])
    return changed


def _r196_promotion(fixture, local, evidence):
    initial, reserved, captured = _frozen._r179_completed(fixture)
    for label, record in (("initial", initial), ("capture reserved", reserved),
                          ("capture completed", captured)):
        _r196_decode(record, evidence, label)
    reserve = _frozen._r179_history_request(
        fixture, captured, "bootstrap", "RESERVE_PLAN", "r196-reserve-plan"
    )
    claim = _r196_hash([reserve["payload"]["bootstrap_id"],
                         _frozen._r179_state_hash(captured), "RESERVE_PLAN"])
    planning = copy.deepcopy(captured)
    planning["payload"]["pending"] = {"claim_id": claim, "effect": "PLAN"}
    planning = _r196_commit(captured, reserve, planning)
    _r196_decode(planning, evidence, "plan reserved")
    complete = _frozen._r179_history_request(
        fixture, planning, "bootstrap", "COMPLETE_PLAN", "r196-complete-plan"
    )
    complete["payload"]["claim_id"] = claim
    draft = _r196_plain(fixture["legacy"]["sources"]["visual.bootstrap.record.v1"].to_payload())["draft"]
    complete["payload"]["draft"] = draft
    planned = copy.deepcopy(planning)
    planned["payload"].update(draft=draft, planning_source_usable=True,
                               proposal_hash=_r196_hash(draft["parsed_json"]), pending=None)
    planned = _r196_commit(planning, complete, planned)
    _r196_decode(planned, evidence, "plan completed")
    prior_legacy = fixture["legacy"]["promoted_original"]
    legacy_raw = _r196_plain(prior_legacy.to_payload())
    assert _r196_hash(legacy_raw) == prior_legacy.digest()
    prior = _r196_local_original(prior_legacy, planned["original_time"]) if local else legacy_raw
    if local:
        _r196_decode(prior, evidence, "independent complete local original")
    else:
        from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import original_from_payload

        restored = original_from_payload(copy.deepcopy(prior))
        assert restored.to_payload() == legacy_raw
        assert restored.digest() == prior_legacy.digest()
    promotion = copy.deepcopy(fixture["cases"]["visual.bootstrap.promotion.local.v1"])
    promotion["payload"].update(original=prior, expected_record_hash=_frozen._r179_state_hash(planned),
                                 event_key="r196-promote-original")
    _r196_decode(promotion, evidence, "promotion request standalone")
    final = copy.deepcopy(planned)
    final["payload"].update(terminal_reason="original_adopted", adopted_original_hash=_r196_hash(prior))
    final = _r196_commit(planned, promotion, final)
    assert final["payload"]["state"] == planned["payload"]["state"]
    assert len(final["payload"]["history"]) == 5
    return planned, promotion, final


def _r196_pool_task(raw, task):
    changed = copy.deepcopy(raw)
    if changed["schema_version"] == "recovery.verification-budget.local.v1":
        body = changed["payload"]
        body["task_id"] = task
        body["content_hash"] = _r196_hash({
            "schema_version": changed["schema_version"], "task_id": task,
            "state": body["state"], "revision": body["revision"],
        })
    else:
        changed["task_id"] = task
        changed["content_hash"] = _r196_hash({k: v for k, v in changed.items() if k != "content_hash"})
    return changed


def _r196_pool_decode(raw, evidence, label):
    if raw["schema_version"] == "recovery.verification-budget.local.v1":
        return _r196_decode(raw, evidence, label)
    from cloud_edge_robot_arm.edge.recovery.lifecycle import VerificationBudgetRecord

    record = VerificationBudgetRecord.from_payload(copy.deepcopy(raw))
    assert _r196_plain(record.to_payload()) == raw
    evidence["decoder_calls"].append({"label": label, "raw_sha256": _r196_hash(raw),
                                     "entry": "VerificationBudgetRecord.from_payload", "returned": True})
    return record


def _r196_route(fixture, pools):
    route = copy.deepcopy(fixture["route"])
    assert route["payload"]["produced_publication"] is not None
    if pools == "legacy":
        source = fixture["cases"]["visual.verification.route.local.v1"]["payload"]
        for name in ("before_verification_budget", "after_verification_budget"):
            route["payload"][name] = copy.deepcopy(source[name])
    return route


def _r196_foreign_publication(raw, task):
    changed = copy.deepcopy(raw)
    body = changed["payload"]
    body["identity"]["task_id"] = task
    body["checkpoint"]["task_id"] = task
    body["checkpoint"]["checkpoint_hash"] = ""
    body["checkpoint"]["checkpoint_hash"] = _r196_hash(body["checkpoint"])
    body["verification_budget"] = _r196_pool_task(body["verification_budget"], task)
    retry = body["retry_budget"]
    (retry["payload"] if retry.get("schema_version") == "recovery.retry-budget.local.v1" else retry)["task_id"] = task
    body["publication_hash"] = _frozen._r179_publication_hash(changed)
    return changed


@pytest.mark.parametrize("source", ["local", "legacy"])
def test_r196_full_promotion_history(monkeypatch, tmp_path, request, source):
    with _r196_case(request, tmp_path, "full-promotion:" + source) as evidence:
        fixture = _frozen._r179_fixture(monkeypatch)
        planned, promotion, final = _r196_promotion(fixture, source == "local", evidence)
        evidence.update(baseline_payload=planned, changed_payload=final,
                        mutation="append complete typed PROMOTE to four accepted capture/plan phases")
        restored = _r196_decode(final, evidence, "complete promotion replay")
        assert restored.to_payload()["payload"]["terminal_reason"] == "original_adopted"
        assert final["payload"]["adopted_original_hash"] == _r196_hash(promotion["payload"]["original"])
        assert final["payload"]["state"] == planned["payload"]["state"]


@pytest.mark.parametrize("edge", ["route_input", "supervision_definition", "supervision_transition"])
def test_r196_semantic_original_join_rejects(monkeypatch, tmp_path, request, edge):
    with _r196_case(request, tmp_path, "semantic-original:" + edge) as evidence:
        fixture = _frozen._r179_fixture(monkeypatch)
        baseline = _r196_request(fixture, edge)
        _r196_decode(baseline, evidence, "complete baseline")
        changed = copy.deepcopy(baseline)
        prior = _r196_alternate_original(changed["payload"]["original"])
        _r196_decode(prior, evidence, "independent alternate original")
        changed["payload"]["original"] = prior
        _r196_publication_original(changed["payload"]["publication"], prior)
        _r196_decode(changed["payload"]["publication"], evidence, "coherent dependent publication")
        assert prior["original_time"] != changed["original_time"]
        evidence.update(baseline_payload=baseline, changed_payload=changed,
                        mutation="only embedded original verification window identity plus dependent publication hashes")
        with pytest.raises(ValueError, match="original|reference|binding|time"):
            _r196_decode(changed, evidence, "semantic parent-child original join")


@pytest.mark.parametrize("target", ["local_pair", "legacy_pair", "produced_publication"])
def test_r196_route_task_join_rejects(monkeypatch, tmp_path, request, target):
    with _r196_case(request, tmp_path, "route-task:" + target) as evidence:
        fixture = _frozen._r179_fixture(monkeypatch)
        baseline = _r196_route(fixture, "legacy" if target == "legacy_pair" else "local")
        _r196_decode(baseline, evidence, "complete route baseline")
        changed = copy.deepcopy(baseline)
        task = changed["payload"]["input"]["payload"]["original"]["identity"]["task_id"] + ":foreign-r196"
        if target == "produced_publication":
            publication = _r196_foreign_publication(changed["payload"]["produced_publication"], task)
            _r196_decode(publication, evidence, "independent coherent foreign publication")
            changed["payload"]["produced_publication"] = publication
            changed["payload"]["produced_publication_hash"] = publication["payload"]["publication_hash"]
        else:
            for name in ("before_verification_budget", "after_verification_budget"):
                pool = _r196_pool_task(changed["payload"][name], task)
                _r196_pool_decode(pool, evidence, "independent foreign " + name)
                changed["payload"][name] = pool
        evidence.update(baseline_payload=baseline, changed_payload=changed,
                        mutation="foreign task in " + target + "; independent children and hashes remain coherent")
        with pytest.raises(ValueError, match="task|original|publication|binding"):
            _r196_decode(changed, evidence, "route actual task join")


@pytest.mark.parametrize("pools", ["local", "legacy"])
def test_r196_route_task_join_positive(monkeypatch, tmp_path, request, pools):
    with _r196_case(request, tmp_path, "route-positive:" + pools) as evidence:
        fixture = _frozen._r179_fixture(monkeypatch)
        route = _r196_route(fixture, pools)
        for name in ("before_verification_budget", "after_verification_budget"):
            _r196_pool_decode(route["payload"][name], evidence, name)
        _r196_decode(route["payload"]["produced_publication"], evidence, "produced publication")
        evidence.update(baseline_payload=route, changed_payload=route, mutation="none")
        _r196_decode(route, evidence, "complete agreeing-task route")


@pytest.mark.parametrize("target", ["compiler_policy", "original_time"])
def test_r196_promotion_source_rejects(monkeypatch, tmp_path, request, target):
    with _r196_case(request, tmp_path, "promotion-source:" + target) as evidence:
        fixture = _frozen._r179_fixture(monkeypatch)
        planned, promotion, baseline = _r196_promotion(fixture, True, evidence)
        _r196_decode(baseline, evidence, "complete successful local promotion baseline")
        changed_request = copy.deepcopy(promotion)
        prior = changed_request["payload"]["original"]
        if target == "original_time":
            prior = _r196_alternate_original(prior)
        else:
            first = next(iter(prior["payload"]["requirements"].values()))
            first["allowed_error_m"] = first["allowed_error_m"] + 0.001
        _r196_decode(prior, evidence, "independent mutated complete original")
        changed_request["payload"]["original"] = prior
        changed = copy.deepcopy(planned)
        changed["payload"].update(terminal_reason="original_adopted", adopted_original_hash=_r196_hash(prior))
        changed = _r196_commit(planned, changed_request, changed)
        evidence.update(baseline_payload=baseline, changed_payload=changed,
                        mutation="only original " + target + " and dependent original/adoption/history hashes")
        with pytest.raises(ValueError, match="original|reference|binding|requirements|policy|source"):
            _r196_decode(changed, evidence, "full promotion rejects inconsistent source")
