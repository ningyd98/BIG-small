"""Software fixtures for original usage metadata, never invoiced money."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cloud_edge_robot_arm.research.provider_usage import (
    ProviderUsageAuditor,
    ProviderUsageRegistration,
)
from cloud_edge_robot_arm.vision.role_models import RoleProviderSnapshot

MODEL = "qwen3.8-max-0902"
SOURCE_NAMES = (
    "src/cloud_edge_robot_arm/research/provider_usage.py",
    "src/cloud_edge_robot_arm/research/cost_ledger.py",
    "src/cloud_edge_robot_arm/research/resource_plan.py",
)


@pytest.mark.parametrize("object_type", [None, "error", "response", "chat.completion.chunk"])
def test_only_supported_synchronous_chat_response_is_observed(tmp_path, object_type):
    response = {
        "id": "opaque",
        "model": MODEL,
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    if object_type is not None:
        response["object"] = object_type
    result = read(fixture(tmp_path, response=response)[0])
    assert result.status == "UNKNOWN" and result.attempts[0].input_tokens is None
    assert result.original_attempts == result.sent_attempts == 1
    assert result.monetary_cost is None


def test_typed_chat_error_envelope_is_still_unsupported(tmp_path):
    response = {
        "object": "chat.completion",
        "error": {"code": "software-fixture-error"},
        "id": "opaque",
        "model": MODEL,
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }
    result = read(fixture(tmp_path, response=response, status="ERROR")[0])
    assert result.status == "UNKNOWN" and result.original_attempts == 1


@pytest.mark.parametrize("empty", [False, True])
def test_zero_provider_usage_keeps_all_attempts_unknown(tmp_path, empty):
    registration, evidence = fixture(tmp_path, status="ERROR")
    ledger = json.loads((evidence / "ledger.json").read_text())
    if empty:
        ledger = []
    else:
        ledger[0].update(sent_at=None, serialized_sent_bytes=0, serialized_received_bytes=0)
    (evidence / "ledger.json").write_text(json.dumps(ledger))
    (evidence / "wire.json").write_text("[]")
    result = read(rebound(registration, evidence))
    assert result.status == "UNKNOWN"
    assert result.original_attempts == (0 if empty else 1) and result.sent_attempts == 0
    assert len(result.attempts) == (0 if empty else 1)
    assert result.monetary_cost is None


@pytest.mark.parametrize("side", ["input", "output"])
def test_disjoint_modality_subtotals_cannot_exceed_parent(tmp_path, side):
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    if side == "input":
        usage["prompt_tokens_details"] = {"text_tokens": 70, "image_tokens": 70}
    else:
        usage["completion_tokens_details"] = {"text_tokens": 40, "audio_tokens": 40}
    response = {"object": "chat.completion", "id": "opaque", "model": MODEL, "usage": usage}
    result = read(fixture(tmp_path, response=response)[0])
    assert result.status == "UNKNOWN" and result.attempts[0].input_tokens is None


def fixture(tmp_path: Path, *, response=None, status="SUCCESS"):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    sources = tmp_path / "sources"
    source_hashes = {}
    for name in SOURCE_NAMES:
        path = sources / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(Path(name).read_bytes())
        source_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    role = RoleProviderSnapshot(
        "CLOUD",
        "software-fixture",
        "REMOTE_SERVICE",
        MODEL,
        MODEL,
        None,
        None,
        "1" * 64,
        source_hashes,
    )
    request = json.dumps({"model": MODEL, "messages": []}).encode()
    payload = (
        response
        if response is not None
        else {
            "object": "chat.completion",
            "id": "chatcmpl-provider-7",
            "model": MODEL,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "prompt_tokens_details": {"cached_tokens": 20},
                "completion_tokens_details": {"reasoning_tokens": 30},
            },
        }
    )
    raw_response = json.dumps(payload).encode()
    (evidence / "request.json").write_bytes(request)
    (evidence / "response.json").write_bytes(raw_response)
    timestamp = datetime(2026, 10, 4, tzinfo=UTC).isoformat()
    ledger = [
        {
            "request_id": "local-attempt-1",
            "sent_at": timestamp,
            "finished_at": timestamp,
            "is_cloud_model": True,
            "model_role": "PLANNER",
            "deployment": "CLOUD",
            "provider_location": "REMOTE_SERVICE",
            "provider_version": role.digest(),
            "status": status,
            "serialized_sent_bytes": len(request),
            "serialized_received_bytes": len(raw_response),
            "monetary_cost": 900.0,
        }
    ]
    wire = [
        {
            "request_id": "local-attempt-1",
            "request_path": "request.json",
            "response_path": "response.json",
            "response_present": True,
            "request_sha256": hashlib.sha256(request).hexdigest(),
            "response_sha256": hashlib.sha256(raw_response).hexdigest(),
        }
    ]
    (evidence / "ledger.json").write_text(json.dumps(ledger))
    (evidence / "wire.json").write_text(json.dumps(wire))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence.iterdir()}
    registration = ProviderUsageRegistration(
        evidence,
        "ledger.json",
        "wire.json",
        role,
        hashes,
        sources,
        source_hashes,
    )
    return registration, evidence


def read(registration):
    return ProviderUsageAuditor({"registered": registration}).audit("registered")


def test_reports_original_ids_and_usage_without_billing_authority(tmp_path):
    result = read(fixture(tmp_path)[0])
    assert result.status == "OBSERVED"
    row = result.attempts[0]
    assert row.local_attempt_id == "local-attempt-1"
    assert row.provider_response_id == "chatcmpl-provider-7"
    assert row.provider_request_id is None
    assert (row.input_tokens, row.output_tokens, row.total_tokens) == (100, 50, 150)
    assert (row.cached_input_tokens, row.reasoning_output_tokens) == (20, 30)
    assert result.monetary_cost is None and result.billing_status == "UNAVAILABLE"
    assert result.original_attempts == result.sent_attempts == 1


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
        {"prompt_tokens": 1.5, "completion_tokens": 1, "total_tokens": 2.5},
        {"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 0},
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 99},
    ],
)
def test_missing_or_invalid_usage_is_unknown_not_zero(tmp_path, usage):
    result = read(
        fixture(
            tmp_path,
            response={"object": "chat.completion", "id": "opaque", "model": MODEL, "usage": usage},
        )[0]
    )
    assert result.status == "UNKNOWN" and result.attempts[0].input_tokens is None
    assert result.monetary_cost is None and result.original_attempts == 1


@pytest.mark.parametrize("details", [{"cached_tokens": 101}, {"cached_tokens": True}])
def test_cache_subsets_cannot_exceed_or_corrupt_input_total(tmp_path, details):
    response = {
        "object": "chat.completion",
        "id": "opaque",
        "model": MODEL,
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "prompt_tokens_details": details,
        },
    }
    assert read(fixture(tmp_path, response=response)[0]).status == "UNKNOWN"


def test_failed_attempt_kept_with_original_usage(tmp_path):
    result = read(fixture(tmp_path, status="ERROR")[0])
    assert result.status == "OBSERVED" and result.attempts[0].status == "ERROR"
    assert result.original_attempts == 1 and result.monetary_cost is None


def test_provider_model_drift_rejects_original_response(tmp_path):
    result = read(
        fixture(
            tmp_path,
            response={
                "id": "opaque",
                "model": "other-model",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )[0]
    )
    assert result.status == "INVALID"


def test_source_drift_and_added_original_file_reject(tmp_path):
    registration, evidence = fixture(tmp_path)
    (evidence / "omitted-failure.json").write_text("{}")
    assert read(registration).status == "INVALID"
    (evidence / "omitted-failure.json").unlink()
    (registration.source_root / SOURCE_NAMES[0]).write_text("# changed source\n")
    assert read(registration).status == "INVALID"


def test_symlinked_original_rejects_without_following(tmp_path):
    registration, evidence = fixture(tmp_path)
    data = (evidence / "request.json").read_bytes()
    target = tmp_path / "outside.json"
    target.write_bytes(data)
    (evidence / "request.json").unlink()
    (evidence / "request.json").symlink_to(target)
    assert read(registration).status == "INVALID"


def test_unregistered_id_cannot_supply_an_arbitrary_root(tmp_path):
    registration, _ = fixture(tmp_path)
    assert (
        ProviderUsageAuditor({"registered": registration}).audit("../../evidence").status
        == "UNKNOWN"
    )


def test_registration_and_results_detach_aliases(tmp_path):
    registration, _ = fixture(tmp_path)
    hashes = dict(registration.original_hashes)
    isolated = replace(registration, original_hashes=hashes)
    hashes.clear()
    result = read(isolated)
    assert result.status == "OBSERVED"
    with pytest.raises(TypeError):
        result.raw_file_hashes["fake"] = "0" * 64
    with pytest.raises(FrozenInstanceError):
        result.monetary_cost = 0


def test_constructor_cannot_inject_a_paid_amount(tmp_path):
    result = read(fixture(tmp_path)[0])
    with pytest.raises(ValueError):
        replace(result, monetary_cost=0)


def rebound(registration, evidence):
    """Explicit software owner fixture re-registers original bytes, never actual authority."""
    return replace(
        registration,
        original_hashes={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence.iterdir()
        },
    )


def test_original_empty_error_response_is_unknown_with_full_attempt(tmp_path):
    registration, evidence = fixture(tmp_path, status="ERROR")
    (evidence / "response.json").write_bytes(b"")
    rows = json.loads((evidence / "ledger.json").read_text())
    rows[0]["serialized_received_bytes"] = 0
    wire = json.loads((evidence / "wire.json").read_text())
    wire[0]["response_sha256"] = hashlib.sha256(b"").hexdigest()
    (evidence / "ledger.json").write_text(json.dumps(rows))
    (evidence / "wire.json").write_text(json.dumps(wire))
    result = read(rebound(registration, evidence))
    assert result.status == "UNKNOWN" and result.original_attempts == 1
    assert result.attempts[0].total_tokens is None and result.monetary_cost is None


def test_absent_timeout_response_stays_distinct_from_empty_payload(tmp_path):
    registration, evidence = fixture(tmp_path, status="TIMEOUT")
    rows = json.loads((evidence / "ledger.json").read_text())
    rows[0]["serialized_received_bytes"] = 0
    wire = json.loads((evidence / "wire.json").read_text())
    wire[0].update(response_path=None, response_present=False, response_sha256=None)
    (evidence / "response.json").unlink()
    (evidence / "ledger.json").write_text(json.dumps(rows))
    (evidence / "wire.json").write_text(json.dumps(wire))
    result = read(rebound(registration, evidence))
    assert result.status == "UNKNOWN" and result.sent_attempts == 1
    assert result.attempts[0].status == "TIMEOUT" and result.monetary_cost is None


def test_rehashed_ledger_cannot_replace_registered_provider(tmp_path):
    registration, evidence = fixture(tmp_path)
    rows = json.loads((evidence / "ledger.json").read_text())
    rows[0]["provider_version"] = "other-provider"
    (evidence / "ledger.json").write_text(json.dumps(rows))
    assert read(rebound(registration, evidence)).status == "INVALID"


def test_streaming_chunk_is_not_a_complete_supported_response(tmp_path):
    registration, evidence = fixture(tmp_path)
    request = {"model": MODEL, "messages": [], "stream": True}
    raw = json.dumps(request).encode()
    (evidence / "request.json").write_bytes(raw)
    rows = json.loads((evidence / "ledger.json").read_text())
    rows[0]["serialized_sent_bytes"] = len(raw)
    wire = json.loads((evidence / "wire.json").read_text())
    wire[0]["request_sha256"] = hashlib.sha256(raw).hexdigest()
    (evidence / "ledger.json").write_text(json.dumps(rows))
    (evidence / "wire.json").write_text(json.dumps(wire))
    assert read(rebound(registration, evidence)).status == "UNKNOWN"


def test_reasoning_is_not_added_again_and_cannot_exceed_text_subset(tmp_path):
    response = {
        "object": "chat.completion",
        "id": "opaque",
        "model": MODEL,
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "completion_tokens_details": {"text_tokens": 20, "reasoning_tokens": 30},
        },
    }
    assert read(fixture(tmp_path, response=response)[0]).status == "UNKNOWN"


def test_changed_files_during_metadata_read_reject(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.research import provider_usage

    registration, evidence = fixture(tmp_path)
    original = provider_usage._read_request_costs

    def change(*args, **kwargs):
        value = original(*args, **kwargs)
        (evidence / "unreported.json").write_text("{}")
        return value

    monkeypatch.setattr(provider_usage, "_read_request_costs", change)
    assert read(registration).status == "INVALID"
