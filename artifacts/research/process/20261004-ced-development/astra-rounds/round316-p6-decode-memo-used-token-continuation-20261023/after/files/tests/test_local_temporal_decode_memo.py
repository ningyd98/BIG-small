"""R315 scoped decode reuse with real frozen histories and delegating validators."""
from collections import Counter
import contextvars
import copy
import hashlib
import json
from pathlib import Path
import sys

import pytest

from cloud_edge_robot_arm.vision import local_temporal as local

SEED = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014/implementation/green63/cases/6d92899340e539991792be9037c073ce65513cc029918750cae4831bd0ef02f4.json")
SEED_SHA = "20cbbe651d46f5c62428130db2523a413fcccede2f8851a0e6db2fb56126fb79"
LEAF_SHA = "3e64056f99c608399c22c6f6a36df402c8c777397d0268e476fb8df3f12b14c6"
OUTER = {"schema_version", "payload", "original_time", "decision", "transaction", "diagnostics"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def frozen_projection(value):
    # Independent copy of the frozen R179 projection recipe; no decoder/helper call.
    if isinstance(value, list):
        return [frozen_projection(item) for item in value]
    if isinstance(value, dict):
        if set(value) == OUTER and value["schema_version"].endswith(".local.v1"):
            return {"schema_version": value["schema_version"],
                    "payload": frozen_projection(value["payload"]),
                    "original_time": copy.deepcopy(value["original_time"])}
        return {name: frozen_projection(item) for name, item in value.items()}
    return value


def test_scoped_decode_memo_contract(tmp_path, monkeypatch):
    from cloud_edge_robot_arm.simulation_runtime import operational_lease as lease
    from cloud_edge_robot_arm.vision import operational_windows as windows

    registries = [(name, getattr(module, name)) for module, names in (
        (windows, ("_OWNERS", "_PENDING", "_HANDOFFS", "_SCOPES", "_TRANSITIONS")),
        (lease, ("_SESSIONS", "_VIEWS", "_PROPOSALS", "_ACKS"))) for name in names]
    before_registries = [dict(value) for _, value in registries]
    source = Path(local.__file__)
    source_bytes = source.read_bytes()
    packet = {"round": "R315", "seed": {"path": str(SEED), "bytes": 524867, "sha256": SEED_SHA},
              "source": {"path": str(source), "bytes": len(source_bytes),
                         "sha256": hashlib.sha256(source_bytes).hexdigest()},
              "selection": "changed_payload", "checks": {}, "exceptions": [], "live_authority_created": False}
    stack = contextvars.ContextVar("r315_test_decode_stack", default=())
    attempts, successes = Counter(), Counter()
    roots = {}
    phase = ["primary"]
    next_root = [0]
    action, acting = [None], [False]
    real_from_payload = local.LocalEnvelope.from_payload.__func__
    real_semantic = local._semantic

    def tracked_decode(cls, payload):
        parents = stack.get()
        if parents:
            root_id = parents[0][0]
        else:
            next_root[0] += 1
            root_id = next_root[0]
            roots[root_id] = phase[0]
        # Same strict-copy/canonical recipe as the actual decoder key, no trusted path.
        key = (root_id, cls, canonical(local._object(payload, local.OUTER_FIELDS)))
        token = stack.set(parents + (key,))
        try:
            return real_from_payload(cls, payload)
        finally:
            stack.reset(token)

    def delegating_semantic(*args, **kwargs):
        key = stack.get()[-1]
        attempts[key] += 1
        result = real_semantic(*args, **kwargs)
        successes[key] += 1
        if len(stack.get()) == 1 and action[0] is not None and not acting[0]:
            acting[0] = True
            try:
                action[0]()
            finally:
                acting[0] = False
        return result

    monkeypatch.setattr(local.LocalEnvelope, "from_payload", classmethod(tracked_decode))
    monkeypatch.setattr(local, "_semantic", delegating_semantic)

    def run(label, payload, cls=local.LocalEnvelope):
        previous = phase[0]
        phase[0] = label
        try:
            value = cls.from_payload(payload)
            return value, next_root[0]
        finally:
            phase[0] = previous

    def rejected(label, payload):
        try:
            local.LocalEnvelope.from_payload(payload)
        except ValueError as error:
            packet["exceptions"].append({"label": label, "type": type(error).__name__, "message": str(error)})
        else:
            pytest.fail("invalid complete envelope accepted: " + label)

    try:
        seed_bytes = SEED.read_bytes()
        assert len(seed_bytes) == 524867 and hashlib.sha256(seed_bytes).hexdigest() == SEED_SHA
        document = json.loads(seed_bytes)
        assert document["category"] == "full-promotion:local" and document["test_exit_exception"] is None
        seed = document["changed_payload"]
        assert digest(seed) == LEAF_SHA == document["changed_payload_sha256"]
        expected = canonical(seed)
        decoded, primary = run("primary", seed)
        assert canonical(decoded.to_payload()) == expected and decoded.digest() == LEAF_SHA
        packet.update(output_payload=decoded.to_payload(), output_digest=decoded.digest(),
                      frozen_projection_sha256=digest(frozen_projection(seed)))
        packet["checks"]["real_full_promotion_decoded_exactly"] = True
        primary_counts = {key: count for key, count in successes.items() if key[0] == primary}
        duplicate = [count for count in primary_counts.values() if count > 1]
        packet["primary_duplicate_success_counts"] = duplicate
        # Sole approved RED on original code: valid inputs were decoded successfully.
        assert not duplicate, "identical scoped envelopes repeated successful semantic validation"

        assert len(primary_counts) <= 128 and sum(2 * len(key[2].encode()) for key in primary_counts) <= 8 * 1024 * 1024
        assert local._DECODE_MEMO_ENTRY_CAP == 128 and local._DECODE_MEMO_BYTE_CAP == 8 * 1024 * 1024
        assert local._DECODE_MEMO.get() is None
        assert local.semantic_projection(seed) == frozen_projection(seed)
        assert canonical(decoded.local_time.to_payload()) == canonical(seed["original_time"])
        assert canonical(decoded.decision.to_payload()) == canonical(seed["decision"])
        assert canonical(decoded.transaction.to_payload()) == canonical(seed["transaction"])
        assert canonical(decoded.semantic["state"]) == canonical(seed["payload"]["state"])
        exported = decoded.to_payload()
        exported["payload"]["state"]["remaining_reobservations"] = -1
        assert canonical(decoded.to_payload()) == expected and decoded.digest() == LEAF_SHA
        roundtrip, _ = run("roundtrip", decoded.to_payload())
        assert roundtrip is not decoded and canonical(roundtrip.to_payload()) == expected
        packet["checks"]["canonical_digest_projection_budget_time_evidence_copy_isolation"] = True

        small = copy.deepcopy(seed["payload"]["history"][0]["request"])
        variant = copy.deepcopy(small)
        variant["diagnostics"]["monotonic"] = 1.0
        different = copy.deepcopy(variant)
        different["diagnostics"]["monotonic"] = 2.0

        class First(local.LocalEnvelope):
            pass

        class Second(local.LocalEnvelope):
            pass

        invalids = {}
        for label in ("nested_decision", "nested_transaction", "original_reference", "diagnostic_shape", "exhausted_budget"):
            bad = copy.deepcopy(seed)
            history = bad["payload"]["history"]
            if label == "nested_decision":
                history[0]["decision"]["operation_id"] += "-corrupt"
            elif label == "nested_transaction":
                history[0]["transaction"]["operation_id"] += "-corrupt"
            elif label == "original_reference":
                history[0]["request"]["original_time"]["task_reference"]["deadline_ns"] += 1
            elif label == "diagnostic_shape":
                history[0]["request"]["diagnostics"]["monotonic"] = {}
            else:
                bad["payload"]["state"]["remaining_reobservations"] = 0
                bad["payload"]["state"]["exhausted_reason"] = "MAX_REOBSERVATIONS"
            invalids[label] = bad

        def same_scope_checks():
            assert local._DECODE_MEMO.get() is not None
            root_id = stack.get()[0][0]
            first = First.from_payload(variant)
            again = First.from_payload(variant)
            second = Second.from_payload(variant)
            second_again = Second.from_payload(variant)
            assert type(first) is type(again) is First and type(second) is type(second_again) is Second
            assert len({id(first), id(again), id(second), id(second_again)}) == 4
            for cls in (First, Second):
                assert successes[(root_id, cls, canonical(variant))] == 1
            changed = first.to_payload()
            changed["diagnostics"]["monotonic"] = 99
            assert first.to_payload() == again.to_payload() == variant
            before = local.LocalEnvelope.from_payload(variant)
            after = local.LocalEnvelope.from_payload(different)
            assert before.to_payload() == variant and after.to_payload() == different
            assert before.digest() != after.digest() and frozen_projection(variant) == frozen_projection(different)
            assert successes[(root_id, local.LocalEnvelope, canonical(variant))] == 1
            assert successes[(root_id, local.LocalEnvelope, canonical(different))] == 1
            mutable = copy.deepcopy(variant)
            local.LocalEnvelope.from_payload(mutable)
            mutable["decision"] = {"cannot": "install authority"}
            rejected("valid_then_mutated_same_object", mutable)
            for label, bad in invalids.items():
                rejected(label, bad)
                rejected(label + "_again", bad)
                assert attempts[(root_id, local.LocalEnvelope, canonical(bad))] == 2
                assert successes[(root_id, local.LocalEnvelope, canonical(bad))] == 0
            for ordinal in range(2):
                context = contextvars.Context()
                assert context.run(local._DECODE_MEMO.get) is None
                obj, separate = context.run(run, "isolated_context_" + str(ordinal), variant)
                assert obj.to_payload() == variant and context.run(local._DECODE_MEMO.get) is None
                assert successes[(separate, local.LocalEnvelope, canonical(variant))] == 1
            packet["checks"]["fresh_hits_class_full_content_keys_mutation_rejection_context_isolation"] = True

        action[0] = same_scope_checks
        run("same_scope", seed)
        action[0] = None
        assert local._DECODE_MEMO.get() is None
        for ordinal in range(2):
            _, separate = run("independent_top_" + str(ordinal), variant)
            assert successes[(separate, local.LocalEnvelope, canonical(variant))] == 1
            assert local._DECODE_MEMO.get() is None

        class Abort(BaseException):
            pass

        def abort_after_success():
            local.LocalEnvelope.from_payload(variant)
            raise Abort("R315 forced BaseException after a successful nested decode")

        action[0] = abort_after_success
        with pytest.raises(Abort) as caught:
            run("exception_scope", small)
        packet["exceptions"].append({"label": "BaseException_scope", "type": type(caught.value).__name__, "message": str(caught.value)})
        action[0] = None
        assert local._DECODE_MEMO.get() is None
        rejected("top_level_exception", invalids["exhausted_budget"])
        assert local._DECODE_MEMO.get() is None
        value, separate = run("after_exception", variant)
        assert value.to_payload() == variant and successes[(separate, local.LocalEnvelope, canonical(variant))] == 1
        packet["checks"]["top_calls_and_success_BaseException_failure_cleanup"] = True

        copied_cases = []
        packet["copied_context_after_parent_cases"] = copied_cases
        for exceptional_parent in (False, True):
            captured = {}

            def retain_active_context():
                parent_value = local.LocalEnvelope.from_payload(variant)
                parent_memo = local._DECODE_MEMO.get()
                assert parent_memo is not None
                context = contextvars.copy_context()
                # Only the test spy stack is reset; the real copied memo stays intact.
                context.run(stack.set, ())
                assert context.run(local._DECODE_MEMO.get) is parent_memo
                captured.update(context=context, parent_memo=parent_memo, parent_value=parent_value)
                if exceptional_parent:
                    raise Abort("R316 copied-context parent BaseException")

            action[0] = retain_active_context
            if exceptional_parent:
                with pytest.raises(Abort) as copied_abort:
                    run("copied_parent_exception", small)
                packet["exceptions"].append({"label": "copied_parent_exception",
                    "type": type(copied_abort.value).__name__, "message": str(copied_abort.value)})
            else:
                run("copied_parent_success", small)
            action[0] = None
            assert local._DECODE_MEMO.get() is None
            context = captured["context"]
            assert context.run(local._DECODE_MEMO.get) is captured["parent_memo"]
            child_memos = []

            def observe_fresh_child_scope():
                child_memo = local._DECODE_MEMO.get()
                assert child_memo is not None and child_memo is not captured["parent_memo"]
                child_memos.append(child_memo)

            action[0] = observe_fresh_child_scope
            child, child_root = context.run(run, "copied_child_" + str(exceptional_parent), variant)
            action[0] = None
            assert len(child_memos) == 1
            assert child is not captured["parent_value"]
            assert canonical(child.to_payload()) == canonical(variant)
            assert child.digest() == captured["parent_value"].digest() == digest(variant)
            assert successes[(child_root, local.LocalEnvelope, canonical(variant))] == 1
            assert context.run(local._DECODE_MEMO.get) is None and local._DECODE_MEMO.get() is None
            copied_cases.append({"exceptional_parent": exceptional_parent,
                "stale_parent_memo_was_preserved": True, "fresh_child_memo": True,
                "successful_revalidations": successes[(child_root, local.LocalEnvelope, canonical(variant))],
                "fresh_instance": True, "exact_canonical_sha256": child.digest(),
                "parent_and_copied_context_cleared": True})
        packet["checks"]["copied_context_after_normal_and_exceptional_parent_cleanup"] = True

        def overflow_checks():
            root_id = stack.get()[0][0]
            a = local.LocalEnvelope.from_payload(variant)
            b = local.LocalEnvelope.from_payload(variant)
            assert a is not b and a.to_payload() == b.to_payload() == variant
            assert successes[(root_id, local.LocalEnvelope, canonical(variant))] == 2
            bad = copy.deepcopy(variant)
            bad["decision"] = {"not": "a decision"}
            rejected("overflow_still_rejects", bad)

        for name, bound in (("_DECODE_MEMO_ENTRY_CAP", 0), ("_DECODE_MEMO_BYTE_CAP", 1)):
            with monkeypatch.context() as limits:
                limits.setattr(local, name, bound)
                action[0] = overflow_checks
                obj, _ = run("overflow_" + name, small)
                action[0] = None
                assert obj.to_payload() == small and local._DECODE_MEMO.get() is None
        assert local._DECODE_MEMO_ENTRY_CAP == 128 and local._DECODE_MEMO_BYTE_CAP == 8 * 1024 * 1024
        assert SEED.read_bytes() == seed_bytes and source.read_bytes() == source_bytes
        assert [dict(value) for _, value in registries] == before_registries
        packet["checks"]["entry_and_byte_overflow_validate_normally_and_originals_unchanged"] = True
    finally:
        exception_type, exception, _ = sys.exc_info()
        packet["test_exit_exception"] = None if exception_type is None else {
            "type": exception_type.__name__, "message": str(exception)}
        packet["validation_counters"] = [
            {"root_id": root_id, "phase": roots[root_id], "class": cls.__module__ + "." + cls.__qualname__,
             "class_identity": id(cls), "full_canonical_sha256": hashlib.sha256(text.encode()).hexdigest(),
             "full_canonical_bytes": len(text.encode()), "attempts": count,
             "successful": successes[(root_id, cls, text)]}
            for (root_id, cls, text), count in attempts.items()]
        packet["registries_unchanged"] = [dict(value) for _, value in registries] == before_registries
        packet["registry_counts"] = [{"name": name, "count": len(value)} for name, value in registries]
        raw = (json.dumps(packet, ensure_ascii=False, allow_nan=False, indent=2) + chr(10)).encode()
        assert len(raw) <= 4 * 1024 * 1024, "finite micro evidence cap"
        with (tmp_path / "decode-memo-case.json").open("xb") as stream:
            stream.write(raw)
