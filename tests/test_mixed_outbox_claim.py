"""R317/R318 mixed outbox compatibility; descriptive rows create no authority."""
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time

import pytest

from cloud_edge_robot_arm.contracts.models import MessageStatus, PendingMessage
from cloud_edge_robot_arm.repositories.event_autonomy.memory import InMemoryEventAutonomyRepository
from cloud_edge_robot_arm.repositories.event_autonomy.sqlite import SQLiteEventAutonomyRepository

SCOPE_ERROR = "operational task mutation requires the registered private publication scope"
ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")


def _pin(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_mixed_local_legacy_claim(tmp_path, backend):
    from cloud_edge_robot_arm.simulation_runtime import operational_lease as lease
    from cloud_edge_robot_arm.vision import operational_windows as windows

    registries = [(name, getattr(module, name)) for module, names in (
        (windows, ("_OWNERS", "_PENDING", "_HANDOFFS", "_SCOPES", "_TRANSITIONS")),
        (lease, ("_SESSIONS", "_VIEWS", "_PROPOSALS", "_ACKS"))) for name in names]
    registry_before = [dict(value) for _, value in registries]
    packet = {"round": "R317", "lock_clarification": "R318", "backend": backend,
              "fixture_kind": "descriptive persisted storage only, no private capability",
              "sources": [_pin(ROOT / "src/cloud_edge_robot_arm/repositories/event_autonomy" / name)
                          for name in ("protocol.py", "memory.py", "sqlite.py")],
              "inputs": [_pin(ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds" / name / "plan.json")
                         for name in ("round317-p6-mixed-outbox-candidate-claim-20261023",
                                      "round318-p6-memory-original-lock-clarification-20261023")],
              "test_source": _pin(Path(__file__)),
              "checks": {}, "operations": [], "fixture_preparations": [],
              "waited_binding": {"phases": []}, "cleanup_errors": [],
              "resources": {"repository_attempted": False, "repository_constructed": False,
                  "repository_closed": False, "sqlite_connections_attempted": 0,
                  "sqlite_connections_opened": 0, "sqlite_connections_closed": 0,
                  "sqlite_connections_peak": 0,
                  "claimant_threads_attempted": 0, "claimant_threads_started": 0,
                  "claimant_threads_joined": 0}, "live_authority_created": False}
    repo = holder = claimant = original_lock = original_connection = None
    holder_lock_held = False
    proceed = threading.Event()
    resources = packet["resources"]

    def message(key, *, task=None, backoff=0, status=MessageStatus.PENDING):
        return PendingMessage(message_id=key, task_id=task or ("legacy-" + key),
            idempotency_key=key, message_type="R317_DESCRIPTION", payload={"label": key},
            backoff_base_ms=backoff, max_retries=5, status=status)

    def snapshot_unlocked(connection=None):
        if backend == "memory":
            local_rows = [{"category": category, "record_key": key, "value_json": raw,
                           "value_utf8_hex": raw.encode().hex()}
                          for (category, key), raw in sorted(repo._local_tasks.items())]
            receipt_rows = [{"operation_id": key, "raw_json": raw, "raw_utf8_hex": raw.encode().hex()}
                            for key, raw in sorted(repo._local_publications.items())]
            legacy = {key: {"payload_json": value.model_dump_json(),
                           "payload_hash": repo._outbox_hashes[key]}
                      for key, value in repo._outbox.items()}
        else:
            conn = connection if connection is not None else repo._conn
            local_rows = [dict(row) for row in conn.execute(
                "SELECT category,record_key,task_id,value_json FROM visual_local_tasks_v1 ORDER BY category,record_key")]
            for row in local_rows:
                row["value_utf8_hex"] = row["value_json"].encode().hex()
            receipt_rows = [dict(row) for row in conn.execute(
                "SELECT * FROM visual_local_publications_v1 ORDER BY operation_id")]
            for row in receipt_rows:
                row["payload_utf8_hex"] = row["payload_json"].encode().hex()
            legacy = {row["message_id"]: dict(row) for row in conn.execute("SELECT * FROM event_outbox ORDER BY id")}
        return {"local_tasks": local_rows, "publication_receipts": receipt_rows, "legacy": legacy}

    def snapshot():
        with (repo._lock if backend == "memory" else repo._write_lock):
            return snapshot_unlocked()

    def same_local(before, after):
        assert before["local_tasks"] == after["local_tasks"]
        assert before["publication_receipts"] == after["publication_receipts"]

    def invoke(label, operation):
        before = snapshot()
        row = {"label": label, "before": before}
        packet["operations"].append(row)
        result = None
        error = None
        try:
            result = operation()
        except ValueError as actual:
            error = actual
            row["exception"] = {"type": type(actual).__name__, "message": str(actual)}
        row["after"] = snapshot()
        same_local(before, row["after"])
        row["returned"] = result.model_dump(mode="json") if isinstance(result, PendingMessage) else result
        return result, error, row

    def refused(label, operation):
        result, error, row = invoke(label, operation)
        assert result is None and type(error) is ValueError and str(error) == SCOPE_ERROR
        assert row["before"] == row["after"]
        return row

    def claimed(label, expected, *, primary=False):
        result, error, row = invoke(label, repo.claim_outbox_message)
        if error is not None:
            assert type(error) is ValueError and str(error) == SCOPE_ERROR
        # Only this first valid mixed delivery assertion is an expected RED.
        if primary:
            assert error is None and result is not None, "mixed legacy candidate must be delivered"
        else:
            assert error is None and result is not None
        assert result.message_id == expected.message_id and result.task_id == expected.task_id
        assert result.status is MessageStatus.SENDING
        old = row["before"]["legacy"]
        new = row["after"]["legacy"]
        assert set(old) == set(new)
        assert {key: value for key, value in old.items() if key != expected.message_id} == {
            key: value for key, value in new.items() if key != expected.message_id}
        stored = PendingMessage.model_validate_json(new[expected.message_id]["payload_json"])
        assert stored == result
        return result

    def binding_unlocked(task, connection=None):
        raw = json.dumps({"task_id": task, "fixture": "descriptive binding, no live authority"}, indent=2)
        if backend == "memory":
            repo._local_tasks[("binding", task)] = raw
        else:
            conn = connection if connection is not None else repo._conn
            conn.execute("INSERT INTO visual_local_tasks_v1(category,record_key,task_id,value_json) VALUES('binding',?,?,?)",
                         (task, task, raw))

    def prepare_local(status):
        with (repo._lock if backend == "memory" else repo._write_lock):
            before = snapshot_unlocked()
            local_message = message("local-message", task="local-task", status=status)
            raw = local_message.model_dump_json(indent=2)
            assert PendingMessage.model_validate_json(raw) == local_message
            receipt = {"operation_id": "fixture-local-publication", "operation_sha256": "1" * 64,
                "job_id": "fixture-job", "attempt": 1, "lease_id": "fixture-lease", "epoch": "fixture-epoch",
                "generation": 1, "row_revision": 1, "phase": "COMPLETE", "event_record_hash": "2" * 64,
                "event_receipt_hash": "3" * 64, "job_receipt_hash": "4" * 64,
                "payload_json": json.dumps({"descriptive_fixture": True, "task_id": "local-task"}, indent=2)}
            if backend == "memory":
                if ("binding", "local-task") not in repo._local_tasks:
                    binding_unlocked("local-task")
                repo._local_tasks[("outbox", "local-message")] = raw
                repo._local_publications[receipt["operation_id"]] = json.dumps(receipt, indent=2)
            else:
                with repo._conn:
                    repo._conn.execute("BEGIN IMMEDIATE")
                    if repo._conn.execute("SELECT 1 FROM visual_local_tasks_v1 WHERE category='binding' AND record_key='local-task'").fetchone() is None:
                        binding_unlocked("local-task")
                    repo._conn.execute("INSERT INTO visual_local_tasks_v1 VALUES('outbox',?,?,?) ON CONFLICT(category,record_key) DO UPDATE SET value_json=excluded.value_json",
                                       ("local-message", "local-task", raw))
                    columns = tuple(receipt)
                    repo._conn.execute("INSERT OR REPLACE INTO visual_local_publications_v1(" + ",".join(columns) + ") VALUES(" + ",".join("?" for _ in columns) + ")", tuple(receipt.values()))
            after = snapshot_unlocked()
        packet["fixture_preparations"].append({"local_status": status.value, "before": before, "after": after,
                                             "valid_local_message_json": raw, "no_live_authority": True})

    try:
        resources["repository_attempted"] = True
        if backend == "sqlite":
            resources["sqlite_connections_attempted"] += 1
            repo = SQLiteEventAutonomyRepository(tmp_path / "events.db")
            resources["sqlite_connections_opened"] += 1
            resources["sqlite_connections_peak"] = 1
        else:
            repo = InMemoryEventAutonomyRepository()
        resources["repository_constructed"] = True
        value, error, _ = invoke("pure_empty", repo.claim_outbox_message)
        assert value is None and error is None
        baseline = message("pure-legacy")
        assert repo.enqueue_outbox(baseline) == baseline
        claimed("pure_legacy_claim", baseline)
        value, error, _ = invoke("pure_no_double_claim", repo.claim_outbox_message)
        assert value is None and error is None
        assert repo.mark_outbox_sent(baseline.message_id) is True
        packet["checks"]["pure_legacy_baseline"] = True

        prepare_local(MessageStatus.PENDING)
        refused("local_only", repo.claim_outbox_message)
        packet["checks"]["local_only_scope_refusal"] = True
        mixed = message("mixed-pending")
        assert repo.enqueue_outbox(mixed) == mixed
        claimed("mixed_pending", mixed, primary=True)
        refused("mixed_no_double_claim", repo.claim_outbox_message)
        assert repo.mark_outbox_sent(mixed.message_id) is True
        for status in (MessageStatus.SENDING, MessageStatus.SENT):
            prepare_local(status)
            mixed = message("mixed-" + status.value.lower())
            assert repo.enqueue_outbox(mixed) == mixed
            claimed("mixed_local_history_" + status.value, mixed)
            refused("retained_local_no_candidate_" + status.value, repo.claim_outbox_message)
            assert repo.mark_outbox_sent(mixed.message_id) is True
        packet["checks"]["mixed_all_local_statuses_no_double_claim"] = True

        future = message("retry-future-first", backoff=86400000)
        assert repo.enqueue_outbox(future) == future
        claimed("future_first_claim", future)
        _, error, failed = invoke("public_future_failure", lambda: repo.mark_outbox_failed(future.message_id, "planned retry"))
        assert error is None and failed["returned"] is True
        future_stored = PendingMessage.model_validate_json(failed["after"]["legacy"][future.message_id]["payload_json"])
        assert future_stored.status is MessageStatus.RETRY_WAIT and future_stored.retry_count == 1
        assert future_stored.next_retry_at > datetime.now(UTC)
        due = message("retry-due-second", backoff=0)
        assert repo.enqueue_outbox(due) == due
        claimed("future_skipped_pending_second", due)
        _, error, due_failed = invoke("public_due_failure", lambda: repo.mark_outbox_failed(due.message_id, "immediate retry"))
        assert error is None and due_failed["returned"] is True
        due_stored = PendingMessage.model_validate_json(due_failed["after"]["legacy"][due.message_id]["payload_json"])
        assert due_stored.status is MessageStatus.RETRY_WAIT and due_stored.retry_count == 1
        claimed("due_retry_selected_after_future_row", due)
        refused("future_only_not_eligible", repo.claim_outbox_message)
        assert repo.mark_outbox_sent(due.message_id) is True
        refused("local_key_mark_sent", lambda: repo.mark_outbox_sent("local-message"))
        refused("local_key_mark_failed", lambda: repo.mark_outbox_failed("local-message", "not authorized"))
        packet["checks"]["retry_backoff_due_order_and_local_mark_refusal"] = True

        candidate = message("waited-candidate", task="newly-bound-task")
        assert repo.enqueue_outbox(candidate) == candidate
        attempted, acquired, done = threading.Event(), threading.Event(), threading.Event()
        wait = packet["waited_binding"]

        def phase(name):
            wait["phases"].append({"name": name, "monotonic_ns": time.monotonic_ns(), "thread_ident": threading.get_ident()})

        class ObservedLock:
            def __enter__(self):
                if threading.current_thread() is claimant:
                    phase("actual_lock_attempt")
                    attempted.set()
                original_lock.acquire()
                return self

            def __exit__(self, *exception):
                original_lock.release()

        class ObservedConnection:
            def __getattr__(self, name):
                return getattr(original_connection, name)

            def __enter__(self):
                original_connection.__enter__()
                return self

            def __exit__(self, *exception):
                return original_connection.__exit__(*exception)

            def execute(self, sql, *arguments):
                observe = threading.current_thread() is claimant and sql.strip().upper() == "BEGIN IMMEDIATE"
                if observe:
                    phase("actual_BEGIN_attempt")
                    attempted.set()
                cursor = original_connection.execute(sql, *arguments)
                if observe:
                    phase("actual_BEGIN_acquired")
                    acquired.set()
                    if not proceed.wait(5):
                        raise AssertionError("bounded claimant observation release absent")
                return cursor

        def claim_waiting():
            try:
                phase("claimant_enter")
                result = repo.claim_outbox_message()
                wait["returned"] = None if result is None else result.model_dump(mode="json")
            except BaseException as error:
                wait["exception"] = {"type": type(error).__name__, "message": str(error)}
            finally:
                phase("claimant_completed")
                done.set()

        if backend == "memory":
            original_lock = repo._lock
            wait.update(actual_lock_type=type(original_lock).__module__ + "." + type(original_lock).__name__,
                        actual_lock_identity=id(original_lock), replacement_lock_constructed=False)
            original_lock.acquire()
            holder_lock_held = True
            phase("holder_actual_lock_acquired")
            wait["pre_binding_snapshot"] = snapshot_unlocked()
            repo._lock = ObservedLock()
        else:
            resources["sqlite_connections_attempted"] += 1
            holder = sqlite3.connect(str(repo.path), check_same_thread=False)
            holder.row_factory = sqlite3.Row
            resources["sqlite_connections_opened"] += 1
            resources["sqlite_connections_peak"] = resources["sqlite_connections_opened"] - resources["sqlite_connections_closed"]
            holder.execute("BEGIN IMMEDIATE")
            phase("holder_actual_BEGIN_acquired")
            wait["pre_binding_snapshot"] = snapshot_unlocked(holder)
            original_connection = repo._conn
            repo._conn = ObservedConnection()
        resources["claimant_threads_attempted"] += 1
        claimant = threading.Thread(target=claim_waiting, name="r317-one-claimant", daemon=True)
        claimant.start()
        resources["claimant_threads_started"] += 1
        assert attempted.wait(5), "claimant must reach actual primitive"
        assert not done.wait(0.05), "claimant must genuinely wait while holder owns primitive"
        phase("claimant_observed_blocked")
        binding_unlocked(candidate.task_id, holder)
        wait["holder_post_binding_snapshot"] = snapshot_unlocked(holder)
        assert wait["pre_binding_snapshot"]["legacy"] == wait["holder_post_binding_snapshot"]["legacy"]
        assert len(wait["holder_post_binding_snapshot"]["local_tasks"]) == len(wait["pre_binding_snapshot"]["local_tasks"]) + 1
        if backend == "memory":
            wait["claimant_before"] = wait["holder_post_binding_snapshot"]
            original_lock.release()
            holder_lock_held = False
            phase("holder_actual_lock_released")
        else:
            holder.commit()
            phase("holder_actual_COMMIT_completed")
            assert acquired.wait(5), "real claimant BEGIN must return after holder commit"
            wait["claimant_before"] = snapshot_unlocked(holder)
            assert wait["claimant_before"] == wait["holder_post_binding_snapshot"]
            proceed.set()
            phase("observation_gate_released")
        assert done.wait(5)
        claimant.join(5)
        assert not claimant.is_alive()
        resources["claimant_threads_joined"] += 1
        wait["claimant_after"] = snapshot()
        assert wait.get("exception") == {"type": "ValueError", "message": SCOPE_ERROR}
        assert "returned" not in wait
        assert wait["claimant_before"] == wait["claimant_after"]
        packet["checks"]["waited_current_binding_rechecked_without_claimant_mutation"] = True
        assert [dict(value) for _, value in registries] == registry_before
    finally:
        error_type, error, _ = sys.exc_info()
        packet["test_exit_exception"] = None if error_type is None else {"type": error_type.__name__, "message": str(error)}
        proceed.set()
        if holder_lock_held:
            original_lock.release()
            holder_lock_held = False
        if holder is not None:
            try:
                holder.rollback()
                holder.close()
                resources["sqlite_connections_closed"] += 1
            except BaseException as cleanup_error:
                packet["cleanup_errors"].append({"stage": "holder_close", "type": type(cleanup_error).__name__, "message": str(cleanup_error)})
        if claimant is not None and claimant.ident is not None:
            claimant.join(5)
            packet["claimant_still_alive"] = claimant.is_alive()
            if not claimant.is_alive():
                resources["claimant_threads_joined"] = 1
            else:
                packet["cleanup_errors"].append({"stage": "claimant_join", "type": "StillAlive"})
        if repo is not None and not packet.get("claimant_still_alive", False):
            if original_lock is not None:
                repo._lock = original_lock
            if original_connection is not None:
                repo._conn = original_connection
            try:
                packet["final_before_close"] = snapshot()
                repo.close()
                resources["repository_closed"] = True
                if backend == "sqlite":
                    resources["sqlite_connections_closed"] += 1
            except BaseException as cleanup_error:
                packet["cleanup_errors"].append({"stage": "repository_close", "type": type(cleanup_error).__name__, "message": str(cleanup_error)})
        packet["registries_unchanged"] = [dict(value) for _, value in registries] == registry_before
        packet["registry_counts"] = [{"name": name, "count": len(value)} for name, value in registries]
        packet["resource_completion"] = resources["repository_closed"] and not packet["cleanup_errors"] and (
            resources["claimant_threads_started"] == resources["claimant_threads_joined"]) and (
            resources["sqlite_connections_opened"] == resources["sqlite_connections_closed"])
        raw = (json.dumps(packet, ensure_ascii=False, allow_nan=False, indent=2) + chr(10)).encode()
        assert len(raw) <= 4 * 1024 * 1024, "finite R317 case cap"
        with (tmp_path / "mixed-outbox-case.json").open("xb") as stream:
            stream.write(raw)
        assert packet["resource_completion"] and packet["registries_unchanged"], "actual resources/registries not restored"
