"""SOFTWARE_ONLY original signed wire/causal controls; no external clock or authority."""

import base64
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from importlib import import_module, util
from pathlib import Path

import pytest


def clock_api():
    name = "cloud_edge_robot_arm.research.native_clock_source_v2"
    assert util.find_spec(name) is not None, "new original signed-clock reader is missing"
    return import_module(name)


def pairs():
    api = clock_api()
    return (
        api.ClockTupleV2("SOFTWARE_ONLY-clock-1", 1, 100, datetime(2026, 10, 5, tzinfo=UTC), 110),
        api.ClockTupleV2("SOFTWARE_ONLY-clock-1", 2, 120, datetime(2026, 10, 5, tzinfo=UTC), 130),
    )


def test_clock_tuple_is_detached_strict_and_roundtrips_original_values():
    api = clock_api()
    original = pairs()[0]
    payload = original.to_payload()
    rebuilt = api.ClockTupleV2.from_payload(payload)
    payload["sequence"] = 9
    assert rebuilt == original and rebuilt.to_payload()["sequence"] == 1
    assert (
        rebuilt.digest() == hashlib.sha256(api.canonical_bytes(original.to_payload())).hexdigest()
    )
    with pytest.raises(ValueError):
        api.ClockTupleV2.from_payload({**original.to_payload(), "native": True})


@pytest.mark.parametrize(
    "field,value",
    [
        ("sequence", True),
        ("mono_before_ns", None),
        ("mono_after_ns", 99),
        ("utc_at", "2026-10-05T00:00:00"),
        ("clock_domain_id", ""),
    ],
)
def test_bad_clock_originals_do_not_coerce(field, value):
    api = clock_api()
    with pytest.raises((ValueError, TypeError)):
        api.ClockTupleV2.from_payload({**pairs()[0].to_payload(), field: value})


def test_slab_commitment_binds_order_complete_pair_content_and_acquisition_bytes():
    api = clock_api()
    source = pairs()
    digest = api.slab_commitment(source, acquisition_sha256="a" * 64)
    assert digest != api.slab_commitment(source[::-1], acquisition_sha256="a" * 64)
    assert digest != api.slab_commitment(source, acquisition_sha256="b" * 64)
    assert digest != api.slab_commitment(source[:1], acquisition_sha256="a" * 64)
    with pytest.raises(ValueError):
        api.slab_commitment(source, acquisition_sha256="caller-finite-bound")


def wire_fixture():
    clock_api()
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads(
        (root / "tools/research/native-clock-v2/testdata/software-only-exchange.json").read_text()
    )
    assert fixture["scope"] == "SOFTWARE_ONLY"
    metadata = json.loads(
        (
            root / "artifacts/research/process/20261004-ced-development/"
            "t7b-native-calibration-source/reset-utc-v2-design/fix-round-1/go/build-metadata.json"
        ).read_text()
    )
    verifier = clock_api().GoWireVerifierV2(
        root / metadata["binary_path"],
        binary_sha256=metadata["binary_sha256"],
        source_root=root,
        source_hashes=metadata["source_hashes"],
    )
    return fixture, verifier


def test_actual_official_go_packet_replay_is_software_signature_only():
    api = clock_api()
    fixture, verifier = wire_fixture()
    result = verifier.verify(
        fixture["request_b64"], fixture["response_b64"], fixture["public_key_b64"]
    )
    assert result.protocol == api.DRAFT08
    assert result.midpoint_unix_s == fixture["expected"]["midpoint_unix_s"]
    assert result.radius_s == fixture["expected"]["radius_s"]
    assert result.native_authority == result.utc_calibration == "UNAVAILABLE"


@pytest.mark.parametrize("change", ["request", "response", "key"])
def test_signed_original_packet_tampering_rejects(change):
    fixture, verifier = wire_fixture()
    fields = {k: fixture[k] for k in ("request_b64", "response_b64", "public_key_b64")}
    key = {"request": "request_b64", "response": "response_b64", "key": "public_key_b64"}[change]
    raw = bytearray(base64.b64decode(fields[key]))
    index = raw.index(clock_api()._request_nonce(bytes(raw))) if change == "request" else -1
    raw[index] ^= 1
    fields[key] = base64.b64encode(raw).decode()
    with pytest.raises(ValueError):
        verifier.verify(**fields)


def test_binary_and_upstream_source_drift_cannot_reuse_public_hash_claim(tmp_path):
    api = clock_api()
    fixture, verifier = wire_fixture()
    altered = tmp_path / "wire"
    altered.write_bytes(verifier.binary.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        api.GoWireVerifierV2(
            altered,
            binary_sha256=verifier.binary_sha256,
            source_root=verifier.source_root,
            source_hashes=verifier.source_hashes,
        )
    sources = dict(verifier.source_hashes)
    sources[next(iter(sources))] = "0" * 64
    with pytest.raises(ValueError):
        api.GoWireVerifierV2(
            verifier.binary,
            binary_sha256=verifier.binary_sha256,
            source_root=verifier.source_root,
            source_hashes=sources,
        )
    assert fixture["scope"] == "SOFTWARE_ONLY"


def test_exchange_schema_rejects_null_brackets_and_foreign_flags():
    api = clock_api()
    payload = {
        "clock_domain_id": "clock-1",
        "exchange_id": "A",
        "request_b64": "",
        "response_b64": "",
        "public_key_b64": base64.b64encode(bytes(32)).decode(),
        "commitment_b64": base64.b64encode(bytes(32)).decode(),
        "previous_reply_b64": "",
        "source_blind_b64": base64.b64encode(bytes(32)).decode(),
        "effective_blind_b64": base64.b64encode(bytes(32)).decode(),
        "send_before_ns": 1,
        "send_after_ns": 2,
        "receive_before_ns": 3,
        "receive_after_ns": 4,
        "verified_before_ns": 5,
        "verified_after_ns": 6,
    }
    with pytest.raises(ValueError, match="original integer"):
        api.ClockExchangeOriginalV2.from_payload({**payload, "verified_after_ns": None})
    with pytest.raises(ValueError):
        api.ClockExchangeOriginalV2.from_payload({**payload, "VALID": True})


def test_causal_replay_binds_real_software_signed_a_b_and_every_original_pair():
    api = clock_api()
    fixture, verifier = wire_fixture()
    originals = fixture["causal_exchanges"]
    before = api.ClockExchangeOriginalV2.from_payload(originals["A"])
    after = api.ClockExchangeOriginalV2.from_payload(originals["B"])
    result = api.verify_causal_slab(pairs(), before, after, verifier, acquisition_sha256="a" * 64)
    assert not result.reasons and len(result.conditional_pair_utc_intervals) == 2
    assert result.native_authority == result.utc_calibration == "UNAVAILABLE"
    expected = fixture["causal_expected_utc_ns"]
    assert all((lo, hi) == tuple(expected) for _, lo, hi in result.conditional_pair_utc_intervals)
    variants = [
        (pairs()[:1], before, after, "a" * 64),
        (pairs()[::-1], before, after, "a" * 64),
        (pairs(), replace(before, verified_after_ns=101), after, "a" * 64),
        (pairs(), before, replace(after, send_before_ns=129, send_after_ns=129), "a" * 64),
        (pairs(), before, replace(after, clock_domain_id="foreign"), "a" * 64),
        (pairs(), before, after, "b" * 64),
    ]
    for sample, first, last, digest in variants:
        diagnosis = api.verify_causal_slab(sample, first, last, verifier, acquisition_sha256=digest)
        assert diagnosis.reasons and not diagnosis.conditional_pair_utc_intervals
        assert diagnosis.native_authority == "UNAVAILABLE"


def test_causal_boundary_detaches_caller_list_and_public_exchange_objects(monkeypatch):
    api = clock_api()
    fixture, verifier = wire_fixture()
    before = api.ClockExchangeOriginalV2.from_payload(fixture["causal_exchanges"]["A"])
    after = api.ClockExchangeOriginalV2.from_payload(fixture["causal_exchanges"]["B"])
    original_pairs = list(pairs())
    verify = verifier.verify

    def mutate_then_verify(*args):
        original_pairs.clear()
        object.__setattr__(after, "clock_domain_id", "caller-drift-during-replay")
        return verify(*args)

    monkeypatch.setattr(verifier, "verify", mutate_then_verify)
    result = api.verify_causal_slab(
        original_pairs,
        before,
        after,
        verifier,
        acquisition_sha256="a" * 64,
    )
    assert not result.reasons and len(result.conditional_pair_utc_intervals) == 2
    assert result.native_authority == "UNAVAILABLE"


def test_duplicate_pair_missing_a_chain_and_replayed_b_stay_unavailable():
    api = clock_api()
    fixture, verifier = wire_fixture()
    before = api.ClockExchangeOriginalV2.from_payload(fixture["causal_exchanges"]["A"])
    after = api.ClockExchangeOriginalV2.from_payload(fixture["causal_exchanges"]["B"])
    for sample, first, last in (
        ((*pairs(), pairs()[0]), before, after),
        (pairs(), before, replace(after, previous_reply_b64="")),
        (pairs(), before, replace(after, response_b64=before.response_b64)),
        (pairs(), replace(before, clock_domain_id="restarted-domain"), after),
        (pairs(), before, replace(after, effective_blind_b64=base64.b64encode(bytes(32)).decode())),
    ):
        result = api.verify_causal_slab(sample, first, last, verifier, acquisition_sha256="a" * 64)
        assert result.reasons and not result.conditional_pair_utc_intervals


def test_offline_verifier_timeout_and_binary_change_leave_no_conditional_result(monkeypatch):
    api = clock_api()
    fixture, verifier = wire_fixture()
    before = api.ClockExchangeOriginalV2.from_payload(fixture["causal_exchanges"]["A"])
    after = api.ClockExchangeOriginalV2.from_payload(fixture["causal_exchanges"]["B"])

    def timeout(*_args, **_kwargs):
        raise api.subprocess.TimeoutExpired("SOFTWARE_ONLY-verifier", 10)

    monkeypatch.setattr(api.subprocess, "run", timeout)
    result = api.verify_causal_slab(pairs(), before, after, verifier, acquisition_sha256="a" * 64)
    assert result.reasons and not result.conditional_pair_utc_intervals
    assert result.native_authority == result.utc_calibration == "UNAVAILABLE"


def test_verifier_rechecks_binary_after_construction_and_detaches_source_hash_alias(tmp_path):
    api = clock_api()
    fixture, verifier = wire_fixture()
    binary = tmp_path / "wire-copy"
    binary.write_bytes(verifier.binary.read_bytes())
    binary.chmod(verifier.binary.stat().st_mode)
    sources = dict(verifier.source_hashes)
    copied = api.GoWireVerifierV2(
        binary,
        binary_sha256=verifier.binary_sha256,
        source_root=verifier.source_root,
        source_hashes=sources,
    )
    sources.clear()
    assert copied.source_hashes
    diagnosis = copied.verify(
        fixture["request_b64"], fixture["response_b64"], fixture["public_key_b64"]
    )
    assert diagnosis.native_authority == "UNAVAILABLE"
    binary.write_bytes(binary.read_bytes() + b"changed-after-construction")
    with pytest.raises(ValueError, match="binary changed"):
        copied.verify(fixture["request_b64"], fixture["response_b64"], fixture["public_key_b64"])


@pytest.mark.parametrize("drift_pin", ["binary", "source"])
def test_final_b_persistent_pin_drift_after_precheck_rejects_real_signed_replay(
    tmp_path, monkeypatch, drift_pin
):
    api = clock_api()
    fixture, original = wire_fixture()
    binary = tmp_path / "wire-copy"
    binary.write_bytes(original.binary.read_bytes())
    binary.chmod(original.binary.stat().st_mode)
    for name in original.source_hashes:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((original.source_root / name).read_bytes())
    verifier = api.GoWireVerifierV2(
        binary,
        binary_sha256=original.binary_sha256,
        source_root=tmp_path,
        source_hashes=original.source_hashes,
    )
    before = api.ClockExchangeOriginalV2.from_payload(fixture["causal_exchanges"]["A"])
    after = api.ClockExchangeOriginalV2.from_payload(fixture["causal_exchanges"]["B"])
    positive = api.verify_causal_slab(pairs(), before, after, verifier, acquisition_sha256="a" * 64)
    assert not positive.reasons and len(positive.conditional_pair_utc_intervals) == 2
    changed_path = (
        binary if drift_pin == "binary" else tmp_path / "tools/research/native-clock-v2/main.go"
    )
    previous_hash = hashlib.sha256(changed_path.read_bytes()).hexdigest()
    real_run = api.subprocess.run
    actual_completions = []

    def append_before_real_final_b(*args, **kwargs):
        if len(actual_completions) == 1:
            with changed_path.open("ab") as handle:
                handle.write(b"SOFTWARE_ONLY appended drift between pin check and final B exec")
        completed = real_run(*args, **kwargs)
        actual_completions.append(completed)
        return completed

    monkeypatch.setattr(api.subprocess, "run", append_before_real_final_b)
    result = api.verify_causal_slab(pairs(), before, after, verifier, acquisition_sha256="a" * 64)
    assert len(actual_completions) == 2
    assert all(completed.returncode == 0 for completed in actual_completions)
    assert all(
        json.loads(completed.stdout)["protocol"] == "draft-ietf-ntp-roughtime-08"
        for completed in actual_completions
    )
    assert hashlib.sha256(changed_path.read_bytes()).hexdigest() != previous_hash
    print(
        json.dumps(
            {
                "scope": "SOFTWARE_ONLY",
                "drift_pin": drift_pin,
                "actual_subprocess_calls": len(actual_completions),
                "before_sha256": previous_hash,
                "after_sha256": hashlib.sha256(changed_path.read_bytes()).hexdigest(),
                "intervals": len(result.conditional_pair_utc_intervals),
                "reasons": result.reasons,
                "subprocess_outputs_fabricated": False,
            },
            sort_keys=True,
        )
    )
    assert result.reasons and not result.conditional_pair_utc_intervals
    assert result.native_authority == result.utc_calibration == "UNAVAILABLE"
