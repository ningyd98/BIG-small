"""R331 finite resource evidence; selected R319 stdlib functions only."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time
import xml.etree.ElementTree as ET
ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
MODULE_PIN = {"path": str(ROOT / "tests/test_operational_time_v1.py"), "bytes": 24211, "sha256": "ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f"}
CASE_NAMES = {"startup-grounding.json", "utc-provenance.json", "terminal-confirmation.json", "public-confirmed-control.json"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin_identity(record):
    require(type(record) is dict, "pin object required")
    result = {name: record[name] for name in ("path", "bytes", "sha256")}
    require(type(result["path"]) is str and Path(result["path"]).is_absolute(),
            "absolute pin path required")
    require(type(result["bytes"]) is int and result["bytes"] >= 0, "integer bytes required")
    require(type(result["sha256"]) is str and len(result["sha256"]) == 64
            and all(c in "0123456789abcdef" for c in result["sha256"]), "SHA256 required")
    return result


def bytes_pin(path, raw):
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def stable_bytes(path):
    path = Path(path)
    first = path.lstat()
    require(stat.S_ISREG(first.st_mode), "regular nofollow file required: " + str(path))
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(descriptor)
        coordinates = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size,
                                  s.st_mtime_ns, s.st_ctime_ns)
        require(coordinates(first) == coordinates(opened), "file changed before read")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read()
        require(coordinates(opened) == coordinates(os.fstat(descriptor))
                == coordinates(path.lstat()) and len(raw) == opened.st_size,
                "file changed during read: " + str(path))
        return raw
    finally:
        os.close(descriptor)


def checked(record):
    item = pin_identity(record)
    raw = stable_bytes(item["path"])
    require(bytes_pin(item["path"], raw) == item, "pin changed: " + item["path"])
    return raw


def decode_json(raw):
    value = json.loads(raw.decode("utf-8"))
    require(type(value) is dict, "JSON object required")
    return value


def read_json(path):
    return decode_json(stable_bytes(path))


def _t2_pin(path: Path) -> dict:
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest()}


def _t2_cleanup(process: subprocess.Popen) -> dict:
    """One owned process group, one 15-second total termination/reap deadline."""
    deadline = time.monotonic() + 15
    errors = []

    def remaining() -> float:
        return max(0.0, deadline - time.monotonic())

    def group_alive():
        try:
            os.killpg(process.pid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError as error:
            errors.append({"stage": "observe group", "type": type(error).__name__,
                           "message": str(error)})
            return None

    if group_alive() is True:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError as error:
            errors.append({"stage": "TERM", "type": type(error).__name__, "message": str(error)})
        try:
            process.wait(timeout=min(5.0, remaining()))
        except subprocess.TimeoutExpired:
            pass
        if group_alive() is True:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError as error:
                errors.append({"stage": "KILL", "type": type(error).__name__, "message": str(error)})
    try:
        process.wait(timeout=remaining())
    except subprocess.TimeoutExpired as error:
        errors.append({"stage": "reap", "type": type(error).__name__, "message": str(error)})
    alive = group_alive()
    while alive is True and remaining() > 0:
        time.sleep(min(0.02, remaining()))
        alive = group_alive()
    return {"leader_reaped": process.returncode is not None, "group_remaining": alive,
            "cleanup_errors": errors, "cleanup_seconds_bound": 15}


def diagnostic_resources(directory: Path, command_id: str, argv: list[str], process_pid: int | None) -> dict:
    from collections import Counter

    expected = [arg for arg in argv if "::" in arg]
    records, errors, nodes = [], [], Counter()
    counts = Counter()
    scenario_caps = {
        "test_memory_sqlite_publication_wait_requires_current_d": 2,
        "test_dual_database_order_and_partial_commit": 6,
        "test_original_budget_debit_not_refilled_by_retry": 2,
        "test_b_local_writer_requires_private_scope": 2,
        "test_real_session_constructor_completion": 1,
        "test_private_startup_to_transaction_grounding": 2,
        "test_local_new_schema_ignores_utc_jump_but_external_does_not": 3,
        "test_b_terminal_publication_confirmation_fault": 1,
        "test_b_public_confirmed_publication_control": 1,
    }
    peak_active_polls = 0
    paths = sorted(directory.iterdir()) if directory.is_dir() else []
    if len(paths) > 10000:
        raise ValueError("T2 resource directory exceeds finite evidence cap")
    for path in paths:
        record = {"path": str(path), "pin": None, "data": None, "error": None}
        try:
            if path.is_symlink() or not path.is_file() or path.suffix != ".json":
                raise ValueError("exact regular T2 resource JSON required")
            record["pin"] = _t2_pin(path)
            value = read_json(path)
            record["data"] = value
            if value["schema_version"] != "bigsmall.r158-t2-resource.v1":
                raise ValueError("exact T2 resource sidecar schema required")
            if value["command_id"] != command_id or value["nodeid"] not in expected:
                raise ValueError("T2 sidecar command/node provenance differs")
            if value["pid"] != process_pid or process_pid is None:
                raise ValueError("T2 sidecar actual child PID differs")
            nodes[value["nodeid"]] += 1
            if value["entered_contract_guard"] is not True:
                raise ValueError("T2 attempt must record the contract guard")
            resources = value["resources"]
            if type(resources) is not list or type(value["allocation_attempts"]) is not int:
                raise ValueError("actual resource allocation denominator required")
            if value["allocation_attempts"] != len(resources):
                raise ValueError("resource attempts do not match actual object records")
            if value["cleanup_errors"]:
                raise ValueError("actual T2 resource cleanup errors retained")
            by_id = {}
            for resource in resources:
                key = resource["resource_id"]
                if type(key) is not int or key <= 0 or key in by_id:
                    raise ValueError("unique actual resource identities required")
                if resource["pid"] != process_pid:
                    raise ValueError("resource child identity differs")
                by_id[key] = resource
            lifecycles = value["worker_lifecycles"]
            if type(lifecycles) is not list:
                raise ValueError("actual worker lifecycle records required")
            poll_ids, linked, intervals = set(), Counter(), []
            observed_sequences, previous_start = set(), 0
            for ordinal, call in enumerate(lifecycles, 1):
                poll_id = call["poll_id"]
                if type(poll_id) is not int or poll_id != ordinal or poll_id in poll_ids:
                    raise ValueError("unique monotonic poll IDs required")
                poll_ids.add(poll_id)
                worker = by_id[call["worker_resource_id"]]
                if worker["kind"] != "worker" or poll_id not in worker["poll_ids"]:
                    raise ValueError("poll must resolve to the same actual worker")
                linked[worker["resource_id"]] += 1
                if call["attempted"] is not True:
                    raise ValueError("actual poll attempt required")
                if type(call["entered"]) is not bool or type(call["returned_normally"]) is not bool:
                    raise ValueError("strict poll entry/return observations required")
                start, end = call["start_sequence"], call["end_sequence"]
                if type(start) is not int or type(end) is not int or not 0 < start < end:
                    raise ValueError("finished poll attempt sequence required")
                if start <= previous_start or start in observed_sequences or end in observed_sequences:
                    raise ValueError("unique ordered observation sequences required")
                previous_start = start
                observed_sequences.update((start, end))
                counts["attempted_poll_lifecycles"] += 1
                if call["entered"]:
                    entry = call["entry_sequence"]
                    if type(entry) is not int or not start < entry < end:
                        raise ValueError("actual poll entry must precede its finish")
                    if entry in observed_sequences:
                        raise ValueError("poll entry sequence duplicated")
                    observed_sequences.add(entry)
                    if (type(call["thread_id"]) is not int
                            or type(call["native_thread_id"]) is not int):
                        raise ValueError("actual poll thread coordinates required")
                    counts["entered_poll_lifecycles"] += 1
                    intervals.extend(((entry, 1), (end, -1)))
                elif (call["entry_sequence"] is not None or call["thread_id"] is not None
                      or call["native_thread_id"] is not None):
                    raise ValueError("unentered poll cannot invent entry/thread observations")
                if call["returned_normally"]:
                    if (not call["entered"] or type(call["return_value"]) is not bool
                            or call["exception"] is not None):
                        raise ValueError("normal poll return must preserve actual bool and entry")
                    counts["normally_returned_poll_lifecycles"] += 1
                elif (call["return_value"] is not None or type(call["exception"]) is not dict
                      or set(call["exception"]) != {"type", "message"}
                      or any(type(item) is not str for item in call["exception"].values())):
                    raise ValueError("failed poll must preserve its actual exception")
            family = value["nodeid"].split("::")[-1].split("[")[0]
            if family not in scenario_caps or len(lifecycles) > scenario_caps[family]:
                raise ValueError("actual scenario poll lifecycle cap exceeded")
            active, local_peak = 0, 0
            for _, delta in sorted(intervals):
                active += delta
                if active < 0:
                    raise ValueError("poll interval ordering differs")
                local_peak = max(local_peak, active)
            if active != 0 or local_peak > 2:
                raise ValueError("actual concurrent poll cap exceeded or unfinished")
            peak_active_polls = max(peak_active_polls, local_peak)
            counts["allocation_attempts"] += len(resources)
            for resource in resources:
                if resource["initialization_attempted"] is not True:
                    raise ValueError("resource attempt missing")
                if type(resource["initialized"]) is not bool:
                    raise ValueError("actual resource initialization observation required")
                counts["initialized"] += int(resource["initialized"])
                counts["kind:" + resource["kind"]] += 1
                if resource["cleanup_observed"] is not True:
                    raise ValueError("resource cleanup unavailable or failed")
                if resource["kind"] == "worker":
                    counts["constructed_worker_attempts"] += 1
                    counts["initialized_workers"] += int(resource["initialized"])
                    ids = resource["poll_ids"]
                    actual_ids = [call["poll_id"] for call in lifecycles
                                  if call["worker_resource_id"] == resource["resource_id"]]
                    if (type(ids) is not list or any(type(item) is not int for item in ids)
                            or ids != actual_ids or len(ids) != linked[resource["resource_id"]]):
                        raise ValueError("worker poll associations differ")
                    if resource["final_active_job_id"] != "":
                        raise ValueError("actual worker idle state must be empty string")
                    if (type(resource["session_observed"]) is not bool
                            or type(resource["heartbeat_observed"]) is not bool):
                        raise ValueError("worker runtime allocation observation missing")
                    for key, kind, peak_key in (
                        ("broker_resource_ids", "broker_thread", "broker_peak_alive"),
                        ("heartbeat_resource_ids", "heartbeat_thread", "heartbeat_peak_alive"),
                    ):
                        thread_ids = resource[key]
                        if (type(thread_ids) is not list or len(set(thread_ids)) != len(thread_ids)
                                or type(resource[peak_key]) is not int
                                or not 0 <= resource[peak_key] <= 1):
                            raise ValueError("worker thread identity/concurrency observation differs")
                        for thread_id in thread_ids:
                            thread = by_id[thread_id]
                            if (thread["kind"] != kind
                                    or thread["worker_resource_id"] != resource["resource_id"]
                                    or thread["cleanup_observed"] is not True
                                    or thread["alive_after_join"] is not False
                                    or type(thread["thread_ident"]) is not int
                                    or type(thread["native_thread_id"]) is not int
                                    or thread["session_resource_id"] not in resource["session_resource_ids"]):
                                raise ValueError("actual worker thread link or termination differs")
                    sessions = resource["session_resource_ids"]
                    if type(sessions) is not list or len(set(sessions)) != len(sessions):
                        raise ValueError("actual session identities required")
                    for session_id in sessions:
                        session = by_id[session_id]
                        if (session["kind"] != "lease_session"
                                or session["worker_resource_id"] != resource["resource_id"]
                                or session["cleanup_observed"] is not True
                                or session["broker_alive"] is not False):
                            raise ValueError("worker session ownership/release differs")
                    if (resource["session_observed"] != bool(sessions)
                            or resource["heartbeat_observed"] != bool(resource["heartbeat_resource_ids"])):
                        raise ValueError("runtime presence and actual resource links differ")
                    if not ids:
                        if (resource["cleanup_basis"] != "never_polled_no_owned_runtime"
                                or resource["initial_active_job_id"] != ""
                                or resource["session_observed"] is not False
                                or resource["heartbeat_observed"] is not False
                                or sessions or resource["broker_resource_ids"]
                                or resource["heartbeat_resource_ids"] or resource["close_attempts"]):
                            raise ValueError("unpolled worker cannot invent runtime execution/close")
                        counts["never_polled_workers"] += 1
                    elif resource["cleanup_basis"] != "poll_finished_runtime_released":
                        raise ValueError("polled worker must preserve actual runtime cleanup basis")
                elif resource["kind"] in {"broker_thread", "heartbeat_thread"}:
                    owner = by_id[resource["worker_resource_id"]]
                    key = ("broker_resource_ids" if resource["kind"] == "broker_thread"
                           else "heartbeat_resource_ids")
                    if owner["kind"] != "worker" or resource["resource_id"] not in owner[key]:
                        raise ValueError("thread cannot omit its real owning worker")
                counts["cleanup_observed"] += 1
            if value["observations"]["observers_restored"] is not True:
                raise ValueError("T2 observer restoration not observed")
        except (OSError, ValueError, TypeError, KeyError) as error:
            record["error"] = {"type": type(error).__name__, "message": str(error)}
            errors.append({"path": str(path), **record["error"]})
        records.append(record)
    mapping_match = nodes == Counter(expected)
    missing_nodes = [node for node in expected if nodes[node] == 0]
    if any(node not in expected or count != 1 for node, count in nodes.items()):
        errors.append({"stage": "helper map", "type": "WrongOrDuplicateNode",
                       "message": "actual sidecar must belong uniquely to selected diagnostic node"})
    if counts["attempted_poll_lifecycles"] > 15 or counts["attempted_poll_lifecycles"] > 64:
        errors.append({"stage": "cap", "type": "WorkerLifecycleCap",
                       "message": "T2 attempted poll15/parent64 cap exceeded"})
    valid = not errors
    return {"schema_version": "bigsmall.r268.resource-observations.v1",
            "command_id": command_id, "actual_node_attempts": len(records),
            "actual_node_counts": dict(nodes), "records": records,
            "complete_sidecar_set": mapping_match, "unavailable_nodes": missing_nodes,
            "whole_run_allocation_denominator": (counts["allocation_attempts"] if mapping_match else None),
            "counts": dict(counts), "all_records_valid": valid, "validation_errors": errors,
            "peak_active_polls_per_node": peak_active_polls,
            "interpretation": "Diagnostic only. Missing sidecars leave whole-run resources unknown; "
                              "ordinary assertion failure is not an observer failure.",
            "unobserved": {"OS_handles": None, "external_models": None, "GPU_native": None,
                           "network_calls": None}}


def _t2_index(root: Path) -> list[dict]:
    import stat

    items = []
    try:
        initial = root.lstat()
    except FileNotFoundError:
        return items
    if stat.S_ISLNK(initial.st_mode):
        return [{"path": str(root), "mode": initial.st_mode, "bytes": initial.st_size,
                 "inode": initial.st_ino, "symlink": True,
                 "link_target": os.readlink(root)}]
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda value: value.name):
                path = Path(entry.path)
                info = entry.stat(follow_symlinks=False)
                value = {"path": str(path), "mode": info.st_mode, "bytes": info.st_size,
                         "inode": info.st_ino, "symlink": stat.S_ISLNK(info.st_mode)}
                if value["symlink"]:
                    value["link_target"] = os.readlink(path)
                elif stat.S_ISDIR(info.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(info.st_mode):
                    value["sha256"] = sha(path)
                items.append(value)
                if len(items) > 10000:
                    raise ValueError("T2 finite file index cap exceeded")
    return items


def strict_index(root):
    rows = _t2_index(root)
    require(root.is_dir() and not root.is_symlink(), "persistent basetemp must remain a real directory")
    by_path = {row["path"]: row for row in rows}
    require(len(by_path) == len(rows), "duplicate persistent index path")
    for row in rows:
        path = Path(row["path"])
        info = path.lstat()
        require(info.st_mode == row["mode"] and info.st_size == row["bytes"]
                and info.st_ino == row["inode"], "persistent index lstat changed")
        if stat.S_ISREG(info.st_mode):
            raw = stable_bytes(path)
            require(not row["symlink"] and bytes_pin(path, raw) == {
                "path": row["path"], "bytes": row["bytes"], "sha256": row["sha256"]},
                    "regular-file own SHA differs")
        elif stat.S_ISDIR(info.st_mode):
            require(not row["symlink"] and "sha256" not in row, "directory is not a file pin")
        elif stat.S_ISLNK(info.st_mode):
            target_text = os.readlink(path)
            require(row["symlink"] and row["link_target"] == target_text and "sha256" not in row,
                    "symlink must retain its own link text only")
            target = Path(os.path.abspath(os.path.join(str(path.parent), target_text)))
            require(target.is_relative_to(root) and str(target) in by_path
                    and not by_path[str(target)]["symlink"], "symlink target escapes, missing or chains")
        else:
            raise ValueError("unexpected special persistent file")
    return rows


def prerequisite(path, contract, pid):
    record = read_json(path)
    valid = (
        record["schema_version"] == "bigsmall.r235.startup-prerequisite.v1"
        and record["pid"] == pid and record["accepted_prerequisite"] is True
        and record["exception"] is None and record["expected_pin"] == contract["module"]
        and record["actual_file_pin"] == contract["module"]
        and record["same_sys_modules_object_after"] is True
        and record["pre_import_hooks_empty"] is True
        and record["profile_trace_before_after_equal"] is True
        and record["profile_trace_before"] == [None] * 4
        and record["profile_trace_after"] == [None] * 4
        and record["pre_observer_resource_measurement"] is None
        and (not record["already_loaded_before"] or record["same_previously_loaded_object"] is True)
        and type(record["elapsed_ns"]) is int and record["elapsed_ns"] >= 0)
    return {"pin": _t2_pin(path), "data": record, "accepted": valid}


def junit_observation(path, nodes):
    if not path.exists():
        return {"pin": None, "available": False, "reason": "No JUnit file actually produced",
                "tests": None, "failures": None, "errors": None, "skips": None}
    raw = stable_bytes(path)
    tree = ET.fromstring(raw)
    rows = []
    for element in tree.iter("testcase"):
        rows.append({"nodeid": element.attrib["classname"].replace(".", "/") + ".py::" + element.attrib["name"],
                     "attributes": dict(element.attrib),
                     "outcomes": [{"tag": v.tag, "attributes": dict(v.attrib), "text": v.text}
                                  for v in element if v.tag in {"failure", "error", "skipped"}]})
    require([row["nodeid"] for row in rows] == nodes, "JUnit selected-node identity differs")
    return {"pin": bytes_pin(path, raw), "available": True, "records": rows, "tests": len(rows),
            "failures": sum(any(v["tag"] == "failure" for v in r["outcomes"]) for r in rows),
            "errors": sum(any(v["tag"] == "error" for v in r["outcomes"]) for r in rows),
            "skips": sum(any(v["tag"] == "skipped" for v in r["outcomes"]) for r in rows)}


def completion_marker_fact(container):
    if type(container) is not dict:
        return {"present": None, "type": None, "value": None,
                "interpretation": "container unavailable or malformed"}
    if "assertions_completed" not in container:
        return {"present": False, "type": None, "value": None,
                "interpretation": "unobserved at this location"}
    value = container["assertions_completed"]
    return {"present": True, "type": type(value).__name__, "value": value,
            "interpretation": "observed at this location"}


def behavior_resources_complete(summary, *, facts):
    facts.update({"eligible": False, "reason": None, "records": []})
    if type(summary) is not dict or type(summary.get("records")) is not list:
        facts["reason"] = "resource summary or records unavailable/malformed"
        return False
    eligible = bool(summary["records"] and summary.get("all_records_valid") is True
                    and summary.get("complete_sidecar_set") is True)
    for ordinal, row in enumerate(summary["records"]):
        data = row.get("data") if type(row) is dict else None
        observations = data.get("observations") if type(data) is dict else None
        top = completion_marker_fact(data)
        nested = completion_marker_fact(observations)
        valid = bool(type(data) is dict and type(observations) is dict
                     and data.get("entered_behavior") is True
                     and nested["present"] is True and nested["type"] == "bool"
                     and nested["value"] is True)
        reason = None
        if type(data) is not dict:
            reason = "data unavailable/malformed"
        elif type(observations) is not dict:
            reason = "observations unavailable/malformed"
        elif nested["present"] is not True:
            reason = "nested completion marker absent"
        elif nested["type"] != "bool":
            reason = "nested completion marker has non-bool type"
        elif nested["value"] is not True:
            reason = "nested completion marker observed false"
        elif data.get("entered_behavior") is not True:
            reason = "entered_behavior is not true"
        facts["records"].append({
            "ordinal": ordinal, "data_type": type(data).__name__,
            "observations_present": type(data) is dict and "observations" in data,
            "observations_type": type(observations).__name__,
            "top_level": top, "nested": nested, "eligible": valid, "reason": reason})
        eligible = eligible and valid
    facts["eligible"] = bool(eligible)
    facts["reason"] = None if eligible else "resource prerequisites or nested completion not satisfied"
    return facts["eligible"]

