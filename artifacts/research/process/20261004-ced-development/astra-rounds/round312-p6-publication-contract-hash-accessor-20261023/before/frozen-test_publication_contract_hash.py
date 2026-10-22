"""R312 readonly publication accessor, using pinned historical decoded fixtures."""

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

from cloud_edge_robot_arm.repositories.event_autonomy.visual_owner import VisualOwnerPublicationRecord

FIXTURES = (
    ("legacy", "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round166-p6-t1-legacy-supervision-claim-timing-20261013/implementation/legacy_control/legacy-goldens.json", 121893, "10452e376a00b1672d540fc1332c6beeeaa42b6cff44f03f425531e26a5d0c38", "276340b03fd03d67a15486d42bfb09cb9c9e0af3a8213cb2f22a4b87dbd2da6f", "visual.owner.publication.v1"),
    ("local", "/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/green63/cases/963cee1eb28f6de9d5f48dbcd1a54e8d49653d2177aea6b17dd2389e5d846f45.json", 300455, "8aa726ed5d96470291eab3c431e11e9b9f3b770aa54139e6a0851ac9e304e041", "26dcccdf8c7aa136ba3e2c89bead8cf2b2ccf6022221daef4841a7f2cd572d78", "visual.owner.publication.local.v1"),
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _registry_summary(registries):
    return [{"name": name, "count": len(values),
             "identities": sorted((id(key), id(value)) for key, value in values.items())}
            for name, values in registries]


def _budgets_and_time(payload):
    body = payload["payload"] if payload["schema_version"].endswith(".local.v1") else payload
    return {"verification_budget": body["verification_budget"], "retry_budget": body["retry_budget"],
            "original_time": payload.get("original_time"),
            "effective_deadline_at": body.get("effective_deadline_at"),
            "published_at": body.get("published_at")}


def test_publication_contract_hash_readonly(tmp_path):
    from cloud_edge_robot_arm.simulation_runtime import operational_lease as lease
    from cloud_edge_robot_arm.vision import operational_windows as windows

    registries = [
        ("windows._OWNERS", windows._OWNERS), ("windows._PENDING", windows._PENDING),
        ("windows._HANDOFFS", windows._HANDOFFS), ("windows._SCOPES", windows._SCOPES),
        ("windows._TRANSITIONS", windows._TRANSITIONS), ("lease._SESSIONS", lease._SESSIONS),
        ("lease._VIEWS", lease._VIEWS), ("lease._PROPOSALS", lease._PROPOSALS),
        ("lease._ACKS", lease._ACKS),
    ]
    registry_before = [dict(values) for _, values in registries]
    packet = {"round": "R312", "cases": [], "missing_accessors": [],
              "registry_before": _registry_summary(registries),
              "live_authority_created": False}
    try:
        for variant, filename, size, file_sha, leaf_sha, schema in FIXTURES:
            case = {"variant": variant, "source": {"path": filename, "bytes": size, "sha256": file_sha},
                    "selection": ('document["visual.owner.publication.v1"] decoded JSON'
                                  if variant == "legacy" else
                                  'document["baseline_payload"]["payload"]["publication"]'),
                    "payload_canonical_sha256": leaf_sha, "schema": schema, "checks": {}}
            packet["cases"].append(case)
            obj = None
            try:
                path = Path(filename)
                raw = path.read_bytes()
                assert len(raw) == size and hashlib.sha256(raw).hexdigest() == file_sha
                document = json.loads(raw)
                seed = (json.loads(document["visual.owner.publication.v1"]) if variant == "legacy"
                        else document["baseline_payload"]["payload"]["publication"])
                assert seed["schema_version"] == schema and _hash(seed) == leaf_sha
                obj = VisualOwnerPublicationRecord.from_payload(seed)
                before = obj.to_payload()
                before_bytes = _canonical(before)
                digest = obj.digest()
                budget_time = _budgets_and_time(before)
                case.update(type=type(obj).__name__, before_payload=before, before_digest=digest,
                            before_budget_time=budget_time, before_budget_time_sha256=_hash(budget_time))
                assert before_bytes == _canonical(seed)
                roundtrip = VisualOwnerPublicationRecord.from_payload(before)
                assert _canonical(roundtrip.to_payload()) == before_bytes and roundtrip.digest() == digest
                case["checks"]["valid_real_codec_and_roundtrip"] = True
                body = before if variant == "legacy" else before["payload"]
                expected = body["contract_hash"]
                missing = False
                try:
                    actual = obj.contract_hash
                except AttributeError as error:
                    missing = True
                    case["accessor_error"] = {"type": type(error).__name__, "message": str(error)}
                    packet["missing_accessors"].append(variant)
                else:
                    case["accessor_value"] = actual
                    assert type(actual) is str and actual == expected
                    assert all(obj.contract_hash == expected for _ in range(3))
                    assert roundtrip.contract_hash == expected
                    assert obj.detached().contract_hash == expected
                    case["checks"]["exact_repeat_detached_value"] = True

                exported = obj.to_payload()
                exported_body = exported if variant == "legacy" else exported["payload"]
                exported_body["contract_hash"] = "0" * 64
                assert _canonical(obj.to_payload()) == before_bytes and obj.digest() == digest
                if not missing:
                    assert obj.contract_hash == expected
                case["checks"]["exported_copy_isolated"] = True
                with pytest.raises((AttributeError, TypeError)):
                    obj.contract_hash = "0" * 64
                case["checks"]["assignment_rejected"] = True
                for mutation in ("missing_field", "non_SHA"):
                    invalid = copy.deepcopy(seed)
                    invalid_body = invalid if variant == "legacy" else invalid["payload"]
                    if mutation == "missing_field":
                        del invalid_body["contract_hash"]
                    else:
                        invalid_body["contract_hash"] = "not-a-sha256"
                    with pytest.raises(ValueError):
                        VisualOwnerPublicationRecord.from_payload(invalid)
                case["checks"]["unchanged_decoder_rejects_invalid_fields"] = True
                assert _canonical(obj.to_payload()) == before_bytes and obj.digest() == digest
                assert _canonical(_budgets_and_time(obj.to_payload())) == _canonical(budget_time)
                assert [dict(values) for _, values in registries] == registry_before
                assert path.read_bytes() == raw
                case["checks"]["payload_digest_budget_time_fixture_registries_unchanged"] = True
            except BaseException as error:
                case["unexpected_exception"] = {"type": type(error).__name__, "message": str(error)}
                raise
            finally:
                if obj is not None:
                    case["after_payload"] = obj.to_payload()
                    case["after_digest"] = obj.digest()
                    case["after_budget_time_sha256"] = _hash(_budgets_and_time(obj.to_payload()))
                case["registries_unchanged"] = [dict(values) for _, values in registries] == registry_before
        assert [dict(values) for _, values in registries] == registry_before
        assert packet["missing_accessors"] == [], "missing contract_hash accessors"
    finally:
        error_type, error, _ = sys.exc_info()
        packet["test_exit_exception"] = None if error_type is None else {
            "type": error_type.__name__, "message": str(error)}
        packet["registry_after"] = _registry_summary(registries)
        packet["registries_unchanged"] = [dict(values) for _, values in registries] == registry_before
        with (tmp_path / "accessor-cases.json").open("x", encoding="utf-8") as stream:
            json.dump(packet, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write(chr(10))
