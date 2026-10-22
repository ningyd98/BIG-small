"""R307 finite observation of original lease-session events; no authority."""
from pathlib import Path
import hashlib
import json
import math
import os
import sys
import threading

import pytest

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round307-p6-t2-detached-publication-phase-expectation-20261022"
LEASE = str(ROOT / "src/cloud_edge_robot_arm/simulation_runtime/operational_lease.py")
TEST = ROOT / "tests/test_operational_runtime_closure.py"
LEASE_SHA = "f71d9bcb9c38a7c93e989f7649360b4a0624b4cc2d869bc389b9c9f6b8a76580"
TEST_SHA = "0b86d44080c9c07f927f8e7421f1d61d7a8ed723efa9fdd0b88127c8cfae6fe4"
PLAN_SHA = "5b93a067f41b198d0732ad54a21954f77d9122655fb7956e90cdc1ca188d2488"
NODE = "tests/test_operational_runtime_closure.py::test_dual_database_order_and_partial_commit"
KEY = "dual_behavior"
TARGETS = {
    ("__init__", 417): ("OperationalLeaseSession.__init__", {"call", "line455", "return"}),
    ("invalidate", 640): ("OperationalLeaseSession.invalidate", {"call"}),
    ("_check_ingress", 468): ("OperationalLeaseSession._check_ingress", {"line471", "exception"}),
    ("_close_worker_lease_session", 982): ("_close_worker_lease_session", {"call", "line987", "return"}),
}
BOUNDS = {"sessions_max": 6, "events_per_session_max": 64, "stack_frames_max": 12,
          "primitive_string_utf8_max": 1024, "exception_chain_max": 4,
          "total_persisted_utf8_bytes_max": 524288, "files_max": 2}
_STATE = None


def pin(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def typename(value):
    cls = type(value)
    return {"module": bounded(type.__getattribute__(cls, "__module__")),
            "name": bounded(type.__getattribute__(cls, "__name__"))}


def bounded(value):
    if type(value) is not str:
        return None
    raw = value.encode("utf-8")
    if len(raw) > 1024:
        return {"prefix": raw[:1024].decode("utf-8", errors="ignore"),
                "omitted_utf8_bytes_at_least": len(raw) - 1024}
    return value


def primitive(value, depth=0):
    kind = type(value)
    if value is None or kind is bool:
        return value
    if kind is int:
        return value if value.bit_length() <= 256 else {"unavailable": "integer_bound"}
    if kind is str:
        return bounded(value)
    if kind in (tuple, list) and depth < 2:
        return {"items": [primitive(value[i], depth + 1) for i in range(min(8, len(value)))],
                "omitted": max(0, len(value) - 8)}
    return {"unavailable": "not_allowed_primitive", "type": typename(value)}


def upper_json_bytes(value, depth=0):
    """Compact ensure_ascii=False JSON cost, without serialization in callbacks."""
    if depth > 16:
        raise ValueError("primitive tree exceeds finite depth16")
    kind = type(value)
    if value is None:
        return 4
    if kind is bool:
        return 4 if value else 5
    if kind is int:
        if value.bit_length() > 256:
            raise ValueError("integer exceeds bounded primitive256bits")
        return len(str(value))
    if kind is float:
        if not math.isfinite(value):
            raise ValueError("nonfinite primitive float")
        return 32
    if kind is str:
        size = len(value.encode("utf-8")) + 2
        for char in value:
            number = ord(char)
            if char in ('"', "\\"):
                size += 1
            elif number < 32:
                size += 1 if number in (8, 9, 10, 12, 13) else 5
        return size
    if kind is list:
        return 2 + max(0, len(value) - 1) + sum(upper_json_bytes(x, depth + 1) for x in value)
    if kind is dict:
        if any(type(key) is not str for key in value):
            raise TypeError("primitive JSON keys must be native strings")
        return 2 + max(0, len(value) - 1) + sum(
            upper_json_bytes(key, depth + 1) + 1 + upper_json_bytes(item, depth + 1)
            for key, item in dict.items(value))
    raise TypeError("unsupported compact primitive tree")


def hook_values():
    return (sys.gettrace(), threading.gettrace(), sys.getprofile(), threading.getprofile())


def hook_records(values):
    return [None if value is None else {"id": id(value), "type": typename(value)} for value in values]


def error_record(stage, error):
    state = _STATE
    if state is None:
        return
    state["incomplete"] = True
    if len(state["observer_errors"]) < 8:
        state["observer_errors"].append({"stage": stage, "type": typename(error)})
    else:
        state["omitted_observer_errors"] += 1


def drop(reason):
    _STATE["incomplete"] = True
    _STATE["dropped_events"] += 1
    counts = _STATE["drops_by_reason"]
    counts[reason] = counts.get(reason, 0) + 1


def target(frame):
    code = frame.f_code
    spec = TARGETS.get((code.co_name, code.co_firstlineno))
    if (spec is None or code.co_filename != LEASE or code.co_qualname != spec[0]
            or frame.f_globals.get("__name__") !=
            "cloud_edge_robot_arm.simulation_runtime.operational_lease"):
        return None
    cls = frame.f_globals.get("OperationalLeaseSession")
    value = frame.f_locals.get("session" if code.co_name == "_close_worker_lease_session" else "self")
    if type(cls) is not type or type(value) is not cls:
        return None
    return spec, value


def dictionary(value):
    try:
        result = object.__getattribute__(value, "__dict__")
    except AttributeError:
        return None
    return result if type(result) is dict else None


def session_snapshot(frame, session):
    values = dictionary(session)
    if values is None:
        return {"session_id": id(session), "unavailable": "exact_session_dict_unavailable"}
    snapshot = {"session_id": id(session), "post_event_non_atomic": True}
    for key in ("epoch", "job_id", "lease_id", "worker_id", "cleanup_reason"):
        value = dict.get(values, key)
        snapshot[key] = bounded(value) if type(value) is str else None
    for key in ("_closed", "join_failed"):
        value = dict.get(values, key)
        snapshot[key] = value if type(value) is bool else None
    for key in ("main_thread", "main_native_thread"):
        value = dict.get(values, key)
        snapshot[key] = value if type(value) is int else None
    for key in ("worker", "repository"):
        value = dict.get(values, key)
        if key == "worker" and value is None and frame.f_code.co_name == "__init__":
            value = frame.f_locals.get("worker")
        snapshot["worker_object_id" if key == "worker" else "repository_id"] = id(value) if value is not None else None
    for key in ("_unusable", "_stop", "_ready"):
        value = dict.get(values, key)
        detail = dictionary(value) if type(value) is threading.Event else None
        flag = dict.get(detail, "_flag") if detail is not None else None
        snapshot[key] = {"event_id": id(value) if type(value) is threading.Event else None,
                         "flag": flag if type(flag) is bool else None,
                         "unavailable": None if type(flag) is bool else "exact_Event_bool_unavailable"}
    epoch = dict.get(values, "epoch")
    registry = frame.f_globals.get("_SESSIONS")
    valid = type(epoch) is str and len(epoch.encode("utf-8")) <= 1024 and type(registry) is dict
    snapshot["registry_id"] = id(registry) if type(registry) is dict else None
    snapshot["registry_maps_epoch_to_session"] = dict.get(registry, epoch) is session if valid else None
    return snapshot


def stack_locations(frame):
    rows, current = [], frame
    try:
        while current is not None and len(rows) < 12:
            code = current.f_code
            rows.append({"filename": bounded(code.co_filename), "name": bounded(code.co_name),
                         "firstlineno": code.co_firstlineno, "current_lineno": current.f_lineno})
            current = current.f_back
        return {"locations": rows, "omitted_more_frames": current is not None}
    finally:
        current = None
        frame = None


def exception_fields(error):
    rows, pending, seen = [], [(error, None, None)], set()
    try:
        while pending and len(rows) < 4:
            value, relation, parent = pending.pop(0)
            if id(value) in seen:
                continue
            seen.add(id(value))
            ordinal = len(rows)
            args = BaseException.__dict__["args"].__get__(value, type(value))
            rows.append({"ordinal": ordinal, "relation": relation, "parent": parent,
                         "type": typename(value), "primitive_args": primitive(args)})
            for name in ("__cause__", "__context__"):
                linked = BaseException.__dict__[name].__get__(value, type(value))
                if linked is not None and id(linked) not in seen:
                    pending.append((linked, name, ordinal))
                linked = None
            value = None
        return {"exceptions": rows, "additional_chain_unavailable": bool(pending)}
    finally:
        pending.clear()
        error = None


def event_flag(value):
    detail = dictionary(value) if type(value) is threading.Event else None
    flag = dict.get(detail, "_flag") if detail is not None else None
    return {"event_id": id(value) if type(value) is threading.Event else None,
            "flag": flag if type(flag) is bool else None,
            "unavailable": None if type(flag) is bool else "exact_Event_bool_unavailable"}


def rpc_timeout_witness(frame, session, ordinal):
    witness = {"selection": "FIRST_OBSERVED_RPC_WAIT_CAP_EXCEEDED_PER_SESSION",
               "event_ordinal": ordinal, "session_id": id(session),
               "non_atomic": True, "caller": None, "request": None,
               "threads": {}, "current_frames_calls": 0, "unavailable": []}
    caller, request, frame_map = frame.f_back, None, None
    try:
        code = caller.f_code if caller is not None else None
        cls = frame.f_globals.get("OperationalLeaseSession")
        original = type.__getattribute__(cls, "__dict__").get("_rpc") if type(cls) is type else None
        valid = (caller is not None and code is not None and code.co_filename == LEASE
                 and code.co_name == "_rpc" and code.co_qualname == "OperationalLeaseSession._rpc"
                 and code.co_firstlineno == 530 and caller.f_globals is frame.f_globals
                 and caller.f_globals.get("__name__") ==
                 "cloud_edge_robot_arm.simulation_runtime.operational_lease"
                 and type(original).__name__ == "function" and original.__code__ is code
                 and caller.f_locals.get("self") is session)
        witness["caller"] = {"exact_original_rpc": bool(valid),
                             "filename": bounded(code.co_filename) if code is not None else None,
                             "firstlineno": code.co_firstlineno if code is not None else None,
                             "lineno": caller.f_lineno if caller is not None else None}
        if valid:
            request = caller.f_locals.get("request")
            request_class = frame.f_globals.get("_Request")
            values = dictionary(request) if type(request_class) is type and type(request) is request_class else None
            if values is None:
                witness["unavailable"].append("exact_original_Request_dictionary_unavailable")
            else:
                error = dict.get(values, "error")
                view, ack = dict.get(values, "view"), dict.get(values, "ack")
                witness["request"] = {
                    "request_id": id(request), "exact_class": True,
                    "kind": bounded(dict.get(values, "kind")), "role": bounded(dict.get(values, "role")),
                    "completed": event_flag(dict.get(values, "completed")),
                    "cancelled": event_flag(dict.get(values, "cancelled")),
                    "error_type": typename(error) if error is not None else None,
                    "view_id": id(view) if view is not None else None,
                    "ack_id": id(ack) if ack is not None else None}
                if type(dict.get(values, "kind")) is not str or type(dict.get(values, "role")) is not str:
                    witness["unavailable"].append("request_kind_or_role_not_native_string")
                for key in ("completed", "cancelled"):
                    if witness["request"][key]["unavailable"] is not None:
                        witness["unavailable"].append("request_" + key + "_flag_unavailable")
                error = view = ack = values = None
        else:
            witness["unavailable"].append("immediate_original_rpc_caller_unavailable")
        values = dictionary(session)
        broker = dict.get(values, "_broker") if values is not None else None
        broker_values = dictionary(broker) if type(broker) is threading.Thread else None
        wanted = {
            "main": (dict.get(values, "main_thread") if values is not None else None,
                     dict.get(values, "main_native_thread") if values is not None else None, None),
            "broker": (dict.get(broker_values, "_ident") if broker_values is not None else None,
                       dict.get(broker_values, "_native_id") if broker_values is not None else None,
                       id(broker) if broker_values is not None else None)}
        frame_map = sys._current_frames()
        witness["current_frames_calls"] = 1
        for label, (ident, native, object_id) in wanted.items():
            selected = dict.get(frame_map, ident) if type(ident) is int else None
            available = type(ident) is int and selected is not None
            witness["threads"][label] = {
                "thread_id": ident if type(ident) is int else None,
                "native_thread_id": native if type(native) is int else None,
                "thread_object_id": object_id, "available": available,
                "stack": stack_locations(selected) if available else None,
                "unavailable": None if available else "exact_selected_live_thread_frame_unavailable"}
            if not available:
                witness["unavailable"].append(label + "_thread_frame_unavailable")
            selected = None
        values = broker = broker_values = None
        return witness
    finally:
        caller = request = frame = None
        if frame_map is not None:
            frame_map.clear()
        frame_map = None


def append_record(row, session_row=None):
    row["ordinal"] = len(_STATE["records"])
    if session_row is not None and session_row["event_count"] >= 64:
        drop("events_per_session64")
        return
    size = upper_json_bytes(row)
    if _STATE["estimated_record_bytes"] + size > 393216:
        drop("reserved_512KiB_budget")
        return
    _STATE["records"].append(row)
    _STATE["record_charges"].append(size)
    _STATE["estimated_record_bytes"] += size
    if session_row is not None:
        session_row["event_count"] += 1
        category = row["category"]
        session_row["first_observed"].setdefault(category, row["ordinal"])
        if category == "invalidate:call":
            session_row.setdefault("first_observed_invalidate", {
                "ordinal": row["ordinal"], "original_reason": row["original_reason"]})


def record_event(frame, event, arg):
    found = target(frame)
    if found is None:
        return
    spec, session = found
    category = "line" + str(frame.f_lineno) if event == "line" else event
    if category not in spec[1]:
        return
    _STATE["attempted_records"] += 1
    sid = id(session)
    sessions = _STATE["sessions"]
    if sid not in sessions:
        if len(sessions) >= 6:
            drop("sessions6")
            return
        sessions[sid] = {"session_id": sid, "event_count": 0, "epoch": None, "first_observed": {}}
    session_row = sessions[sid]
    snapshot = session_snapshot(frame, session)
    epoch = snapshot.get("epoch")
    if type(epoch) is str:
        if session_row["epoch"] is not None and session_row["epoch"] != epoch:
            drop("session_identity_reused")
            return
        session_row["epoch"] = epoch
    tid, native = threading.get_ident(), threading.get_native_id()
    _STATE["observed_threads"].add(tid)
    row = {"category": frame.f_code.co_name + ":" + category, "trace_event": event,
           "trace_lineno": frame.f_lineno, "code_filename": frame.f_code.co_filename,
           "code_name": frame.f_code.co_name, "code_firstlineno": frame.f_code.co_firstlineno,
           "pid": os.getpid(), "thread_id": tid, "native_thread_id": native,
           "snapshot": snapshot, "stack": stack_locations(frame),
           "original_reason": primitive(frame.f_locals.get("reason")),
           "profile_ids_during_event": [None if x is None else id(x)
                                       for x in (sys.getprofile(), threading.getprofile())]}
    if event == "exception":
        row["exception"] = exception_fields(arg[1])
        tb = arg[2]
        row["actual_tb_lineno_at_trace_event"] = tb.tb_lineno if tb is not None else None
        tb = None
    if (row["category"] == "invalidate:call" and row["original_reason"] == "RPC wait cap exceeded"
            and not session_row.get("rpc_timeout_witness_attempted", False)):
        session_row["rpc_timeout_witness_attempted"] = True
        row["rpc_timeout_witness"] = rpc_timeout_witness(frame, session, len(_STATE["records"]))
    append_record(row, session_row)
    session = None
    found = None


def local_trace(frame, event, arg):
    try:
        record_event(frame, event, arg)
    except BaseException as error:
        error_record("target trace callback", error)
    return local_trace


def global_dispatch(frame, event, arg):
    try:
        if event == "call" and target(frame) is not None:
            record_event(frame, event, arg)
            return local_trace
    except BaseException as error:
        error_record("global trace binding", error)
    return None


def live_thread_ids():
    rows = []
    for thread in threading.enumerate():
        values = dictionary(thread)
        ident = dict.get(values, "_ident") if values is not None else None
        rows.append(ident if type(ident) is int else None)
    return rows


def pytest_configure(config):
    global _STATE
    if _STATE is not None:
        raise RuntimeError("R296 observer configured twice")
    command = os.environ["BIGSMALL_R296_COMMAND"]
    directory = Path(os.environ["BIGSMALL_R296_OBSERVATION_DIR"])
    if command != KEY or directory != D / "implementation" / KEY / "passive":
        raise RuntimeError("exact R296 diagnostic identity/sink required")
    if not directory.is_dir() or directory.is_symlink():
        raise RuntimeError("existing exclusive R296 passive directory required")
    if float(config.getini("faulthandler_timeout") or 0.0) != 540:
        raise RuntimeError("native faulthandler540 required")
    sources = {"lease": pin(Path(LEASE)), "test": pin(TEST), "plugin": pin(Path(__file__)),
               "plan": pin(D / "plan.json"), "source_gate": pin(D / "source-gate.json")}
    if (sources["lease"]["sha256"] != LEASE_SHA or sources["test"]["sha256"] != TEST_SHA
            or sources["plan"]["sha256"] != PLAN_SHA):
        raise RuntimeError("frozen R296 source generation differs")
    gate = json.loads((D / "source-gate.json").read_bytes())
    if gate["round"] != "R307" or gate["sources"]["plugin"] != sources["plugin"]:
        raise RuntimeError("ROOT source gate does not bind this complete plugin")
    _STATE = {"directory": directory, "sources": sources, "records": [], "sessions": {},
              "estimated_record_bytes": 0, "record_charges": [], "attempted_records": 0, "dropped_events": 0, "drops_by_reason": {},
              "observer_errors": [], "omitted_observer_errors": 0, "incomplete": False,
              "observed_threads": set(), "call_started": False, "call_finally_observed": False,
              "hooks_before": None, "hooks_after": None, "hooks_equal": None,
              "new_threads_still_live": None, "handles": [], "normal_finish": False}


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_call(item):
    if _STATE is None or item.nodeid != NODE:
        raise RuntimeError("one exact R296 dual call required")
    before = hook_values()
    if before[0] is not None or before[1] is not None:
        error_record("unknown preexisting trace", RuntimeError())
        raise RuntimeError("R296 refuses unknown preexisting trace")
    _STATE["hooks_before"] = hook_records(before)
    _STATE["call_started"] = True
    baseline = set(live_thread_ids())
    installed = False
    try:
        threading.settrace(global_dispatch)
        installed = True
        sys.settrace(global_dispatch)
        yield
    finally:
        observed_hooks = hook_values()
        _STATE["hooks_before_restoration"] = hook_records(observed_hooks)
        if installed and (observed_hooks[0] is not global_dispatch
                          or observed_hooks[1] is not global_dispatch):
            _STATE["incomplete"] = True
        for setter, value, label in ((sys.settrace, before[0], "sys"),
                                     (threading.settrace, before[1], "threading")):
            try:
                setter(value)
            except BaseException as error:
                error_record(label + " trace restoration", error)
        after = hook_values()
        _STATE["hooks_after"] = hook_records(after)
        _STATE["hooks_equal"] = all(a is b for a, b in zip(before, after))
        _STATE["call_finally_observed"] = True
        _STATE["trace_install_attempted"] = installed
        remaining = sorted((_STATE["observed_threads"] - baseline) & set(live_thread_ids()))
        _STATE["new_threads_still_live"] = remaining
        _STATE["per_thread_trace_restoration"] = (
            "ORIGINAL_THREADS_TERMINATED" if not remaining else "UNAVAILABLE_FOR_STILL_LIVE_THREADS")
        if remaining or not _STATE["hooks_equal"]:
            _STATE["incomplete"] = True


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_makereport(item, call):
    if _STATE is None or item.nodeid != NODE or call.excinfo is None:
        return None
    _STATE["attempted_records"] += 1
    try:
        error = call.excinfo.value
        tb = BaseException.__dict__["__traceback__"].__get__(error, type(error))
        rows, examined = [], 0
        try:
            while tb is not None and examined < 64:
                frame = tb.tb_frame
                try:
                    if target(frame) is not None and len(rows) < 12:
                        rows.append({"tb_lineno": tb.tb_lineno, "tb_lasti": tb.tb_lasti,
                                     "post_unwind_frame_lineno": frame.f_lineno,
                                     "code_name": frame.f_code.co_name,
                                     "code_firstlineno": frame.f_code.co_firstlineno,
                                     "code_filename": frame.f_code.co_filename})
                finally:
                    frame = None
                tb = tb.tb_next
                examined += 1
            append_record({"category": "post_unwind_original_exception", "phase": call.when,
                           "exception": exception_fields(error), "actual_target_tracebacks": rows,
                           "more_traceback_unexamined": tb is not None,
                           "post_unwind_non_atomic": True})
        finally:
            tb = None
            error = None
    except BaseException as error:
        error_record("post-unwind original traceback", error)
    return None


def pytest_sessionfinish(session, exitstatus):
    if _STATE is None:
        return
    state = _STATE
    state["normal_finish"] = True
    metadata = {"round": "R307", "command_id": KEY, "nodeid": NODE, "pid": os.getpid(),
                "sources": state["sources"], "bounds": BOUNDS,
                "events_count": len(state["records"]), "dropped_events": state["dropped_events"],
                "first_observed": list(state["sessions"].values()),
                "hooks_before": state["hooks_before"], "hooks_after": state["hooks_after"],
                "hooks_equal": state["hooks_equal"],
                "hooks_before_restoration": state.get("hooks_before_restoration"),
                "observer_errors": state["observer_errors"],
                "omitted_observer_errors": state["omitted_observer_errors"],
                "cap_hit": bool(state["dropped_events"]), "incomplete": state["incomplete"],
                "snapshot_boundary": "Non-atomic target-event fields; no audit of unobserved registry mutations.",
                "legal_RED": False, "GREEN": False}
    events = {**metadata, "schema_version": "bigsmall.r296.session-events.v1",
              "records": state["records"], "drops_by_reason": state["drops_by_reason"]}
    summary = {**metadata, "schema_version": "bigsmall.r296.session-summary.v1",
               "normal_sessionfinish_observed": True,
               "exitstatus": int(exitstatus) if type(exitstatus) is int else None,
               "call_started": state["call_started"],
               "call_finally_observed": state["call_finally_observed"],
               "new_threads_still_live": state["new_threads_still_live"],
               "per_thread_trace_restoration": state.get("per_thread_trace_restoration"),
               "first_cause": "UNKNOWN_REQUIRES_ROOT_EVENT_INTERPRETATION",
               "native_watchdog_identity": None, "native_watchdog_cancellation_observed": None,
               "own_new_Python_threads": 0, "own_new_Events": 0,
               "own_handles": state["handles"], "summary_handle_close_observation": None}
    accounting = {"method": "COMPACT_PRIMITIVE_TREE_UTF8_ESCAPE_BOUND",
                  "record_payload_budget": 393216, "metadata_reserved_bytes": 131072,
                  "attempted_records": state["attempted_records"],
                  "charged_record_bytes": state["estimated_record_bytes"],
                  "record_charges": state["record_charges"], "measured_record_bytes": [],
                  "verified": False, "failure": None}
    events["accounting"] = accounting
    summary["accounting"] = accounting
    try:
        if len(state["record_charges"]) != len(state["records"]):
            raise ValueError("record charge count differs")
        for row, charged in zip(state["records"], state["record_charges"]):
            measured = len(json.dumps(row, ensure_ascii=False, allow_nan=False,
                                      separators=(",", ":")).encode("utf-8"))
            accounting["measured_record_bytes"].append(measured)
            if measured > charged:
                raise ValueError("compact actual record exceeds admitted primitive cost")
        if sum(state["record_charges"]) != state["estimated_record_bytes"] or state["estimated_record_bytes"] > 393216:
            raise ValueError("record admission accounting differs")
        accounting["verified"] = True
        event_raw = (json.dumps(events, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()
        summary_raw = (json.dumps(summary, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()
        if len(event_raw) + len(summary_raw) > 524288:
            raise ValueError("R296 persisted evidence would exceed512KiB; no oversized write")
        with (state["directory"] / "events.json").open("xb") as handle:
            descriptor = handle.fileno()
            if handle.write(event_raw) != len(event_raw):
                raise OSError("partial R296 events write")
        state["handles"].append({"path": str(state["directory"] / "events.json"),
                                 "fd": descriptor, "closed_observed": handle.closed})
        summary["own_handles"] = state["handles"]
        summary_raw = (json.dumps(summary, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()
        if len(event_raw) + len(summary_raw) > 524288:
            raise ValueError("R296 final512KiB bound")
        with (state["directory"] / "summary.json").open("xb") as handle:
            summary["own_handles"] = state["handles"] + [{
                "path": str(state["directory"] / "summary.json"), "fd": handle.fileno(),
                "closed_observed": None,
                "limitation": "Own final close follows this payload; not observable in it."}]
            summary_raw = (json.dumps(summary, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n").encode()
            if len(event_raw) + len(summary_raw) > 524288:
                raise ValueError("R296 handle metadata exceeds512KiB")
            if handle.write(summary_raw) != len(summary_raw):
                raise OSError("partial R296 summary write")
    except BaseException as error:
        error_record("exclusive post-restoration persistence", error)
        accounting["verified"] = False
        accounting["failure"] = {"type": typename(error), "captured_records_not_discarded_in_memory": True}
        failure = {"round": "R307", "command_id": KEY, "nodeid": NODE, "pid": os.getpid(),
                   "schema_version": "bigsmall.r296.session-summary.v1",
                   "incomplete": True, "persistence_failure": True,
                   "captured_event_count": len(state["records"]),
                   "dropped_events": state["dropped_events"], "drops_by_reason": state["drops_by_reason"],
                   "observer_errors": state["observer_errors"],
                   "omitted_observer_errors": state["omitted_observer_errors"],
                   "accounting": accounting, "legal_RED": False, "GREEN": False}
        failure_raw = (json.dumps(failure, ensure_ascii=False, allow_nan=False,
                                  separators=(",", ":")) + "\n").encode("utf-8")
        event_path = state["directory"] / "events.json"
        summary_path = state["directory"] / "summary.json"
        prior_size = event_path.stat().st_size if event_path.exists() else 0
        if not summary_path.exists() and len(failure_raw) + prior_size <= 524288:
            with summary_path.open("xb") as handle:
                if handle.write(failure_raw) != len(failure_raw):
                    raise OSError("partial bounded failure record")
        raise
