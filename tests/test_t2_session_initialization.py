"""R319 one genuine CPU poll, separating constructor observation from cleanup."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import threading

from tests import test_operational_runtime_closure as fixture


def _pin(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def test_real_session_constructor_completion(monkeypatch, tmp_path, request):
    from cloud_edge_robot_arm.simulation_runtime import operational_lease as lease

    root = Path(__file__).resolve().parents[1]
    original_constructor = lease.OperationalLeaseSession.__init__
    original_profile = sys.getprofile()
    original_thread_profile = threading.getprofile()
    packet = {"round": "R319", "mode": "GENUINE_EXISTING_CPU_SOFTWARE_POLL",
              "native_or_physical_claim": False, "polls_requested": 1,
              "sources": [_pin(root / name) for name in (
                  "tests/test_operational_runtime_closure.py", "tests/test_t2_session_initialization.py",
                  "src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py",
                  "src/cloud_edge_robot_arm/simulation_runtime/worker.py")],
              "checks": {}, "callback_observations": [], "final_resource_evidence": None}
    attempt = None
    actual_sessions = []
    try:
        with fixture._b_t2_attempt(request) as attempt:
            fixture._b_t2_api()
            attempt["entered_behavior"] = True

            def observe_constructed(runtime, session, worker, repo, job, events, reads, observed):
                # Read only the existing actual objects/observer records. No adopt,
                # planning, writes, fault injection, decoder or extra poll.
                assert type(session) is lease.OperationalLeaseSession
                assert worker._operational_lease_session is session and session.worker is worker
                registered, record = observed.objects[id(session)]
                assert registered is session and record["kind"] == "lease_session"
                assert record["worker_resource_id"] == id(worker)
                assert id(session) in observed.objects[id(worker)][1]["session_resource_ids"]
                assert session._closed is False and session._broker.is_alive()
                assert hasattr(session, "_sealed") is False
                current = lease.OperationalLeaseSession.__init__
                cells = dict(zip(current.__code__.co_freevars, current.__closure__ or ()))
                delegate = cells.get("original")
                observation = {"session_resource_id": id(session), "worker_resource_id": id(worker),
                    "actual_session_class": type(session).__module__ + "." + type(session).__qualname__,
                    "actual_has_sealed": hasattr(session, "_sealed"), "closed_during_callback": session._closed,
                    "broker_ident": session._broker.ident, "broker_alive_during_callback": session._broker.is_alive(),
                    "constructor_is_original_during_callback": current is original_constructor,
                    "constructor_delegate_is_original": delegate is not None and delegate.cell_contents is original_constructor,
                    "observer_record_during_callback": copy.deepcopy(record)}
                packet["callback_observations"].append(observation)
                actual_sessions.append(session)
                return {"session_resource_id": id(session), "worker_resource_id": id(worker)}

            with fixture._b_t2_observe(monkeypatch, attempt) as observed:
                outcome = fixture._b_t2_exercise(monkeypatch, tmp_path / "memory-session-init", "memory",
                                                observed, observe_constructed)
            # The original poll and all observer cleanup finish before the RED.
            assert len(actual_sessions) == len(packet["callback_observations"]) == 1
            sessions = [row for row in attempt["resources"] if row["kind"] == "lease_session"]
            assert len(sessions) == 1 and sessions[0]["resource_id"] == outcome["session_resource_id"]
            record = sessions[0]
            calls = attempt["worker_lifecycles"]
            assert len(calls) == 1 and calls[0]["attempted"] is True and calls[0]["entered"] is True
            assert calls[0]["returned_normally"] is True and calls[0]["return_value"] is True
            assert calls[0]["exception"] is None and calls[0]["end_sequence"] is not None
            assert calls[0]["worker_resource_id"] == record["worker_resource_id"]
            resources = attempt["resources"]
            assert 0 < len(resources) <= 1000
            assert len({row["resource_id"] for row in resources}) == len(resources)
            assert sum(row["kind"] == "worker" for row in resources) <= 2
            assert sum(row["kind"] == "broker_thread" for row in resources) == 1
            assert sum(row["kind"] == "heartbeat_thread" for row in resources) == 1
            assert all(row["cleanup_observed"] is True for row in resources)
            assert attempt["cleanup_errors"] == []
            assert attempt["observations"]["observers_restored"] is True
            assert attempt["observations"]["method_restoration"] is True
            assert lease.OperationalLeaseSession.__init__ is original_constructor
            assert sys.getprofile() is original_profile and threading.getprofile() is original_thread_profile
            session = actual_sessions[0]
            assert session._closed is True and not session._broker.is_alive()
            assert session._heartbeat_thread is not None and not session._heartbeat_thread.is_alive()
            packet["checks"]["one_actual_normal_poll_all_resource_cleanup_hooks_restored"] = True
            packet["session_record_after_cleanup"] = copy.deepcopy(record)
            packet["after_cleanup_session"] = {"closed": session._closed,
                "broker_alive": session._broker.is_alive(), "heartbeat_alive": session._heartbeat_thread.is_alive(),
                "actual_has_sealed": hasattr(session, "_sealed")}
            # Sole authorized old-observer RED after successful real poll/cleanup.
            assert record["initialized"] is True, "healthy real session constructor misclassified as uninitialized"
            assert record["initialization_error"] is None
            assert record.get("constructor_outcome") == "RETURNED"
            assert packet["callback_observations"][0]["constructor_delegate_is_original"] is True
            assert packet["callback_observations"][0]["observer_record_during_callback"]["initialized"] is True
            assert packet["callback_observations"][0]["observer_record_during_callback"].get("constructor_outcome") == "RETURNED"
            packet["checks"]["genuine_normal_constructor_outcome_without_sealed_or_synthetic_error"] = True
    finally:
        error_type, error, _ = sys.exc_info()
        packet["test_exit_exception"] = None if error_type is None else {"type": error_type.__name__, "message": str(error)}
        packet["final_resource_evidence"] = None if attempt is None else copy.deepcopy(attempt)
        packet["constructor_restored"] = lease.OperationalLeaseSession.__init__ is original_constructor
        packet["hooks_restored"] = sys.getprofile() is original_profile and threading.getprofile() is original_thread_profile
        raw = (json.dumps(packet, ensure_ascii=False, allow_nan=False, indent=2) + chr(10)).encode()
        assert len(raw) <= 4 * 1024 * 1024, "finite session initialization case cap"
        with (tmp_path / "session-init-case.json").open("xb") as stream:
            stream.write(raw)
