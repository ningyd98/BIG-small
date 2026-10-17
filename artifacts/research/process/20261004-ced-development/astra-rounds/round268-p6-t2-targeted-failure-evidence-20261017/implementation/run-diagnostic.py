"""R268: two separate, once-only evidence captures; never GREEN/RED authority."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUNDS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
D = ROUNDS / "round268-p6-t2-targeted-failure-evidence-20261017"
PARENT = ROUNDS / "round258-p6-t2-parent-green7-continuation-20261017"
PLAN_SHA = "ea92b785c2058e7f373ef444dc22655a043b9235f963e80098b4c015b4448c52"
OBS_SHA = "b9bf488904254377daf32daa0ddaca61aafc5f24194c10605a1983e42a00c03e"
CASE_NAMES = {"after-both-lock-denial.json", "true-commit-loss.json",
              "restart-no-authority.json", "same-owner-exact-history.json",
              "one-CAS-no-refund.json", "complete-writer-inventory.json"}
MODULE_PIN = {"path": str(ROOT / "tests/test_operational_time_v1.py"), "bytes": 24211,
              "sha256": "ff226e9a616462c67d74d29931f8f9a7d21548f4f13f93ced64901b263229c0f"}


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


def identity_key(record):
    item = pin_identity(record)
    return item["path"], item["bytes"], item["sha256"]


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


def sha(path):
    return hashlib.sha256(stable_bytes(path)).hexdigest()


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


def write_bytes(path, raw, mode=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        require(handle.write(raw) == len(raw), "partial evidence write")
        handle.flush()
        os.fsync(handle.fileno())
    if mode is not None:
        os.chmod(path, stat.S_IMODE(mode))
    require(stable_bytes(path) == raw, "exclusive evidence readback differs")
    return bytes_pin(path, raw)


def write_json(path, value):
    return write_bytes(path, (json.dumps(value, ensure_ascii=False,
                                        allow_nan=False, indent=2) + "\n").encode("utf-8"))


def absence(path):
    path = Path(path)
    require(not path.exists() and not path.is_symlink(), "required absence changed: " + str(path))
    return {"path": str(path), "exists": False, "is_symlink": False,
            "bytes": None, "sha256": None, "hash_match": None}


def pointer(value, path):
    require(type(path) is str and path.startswith("/") and len(path) < 512,
            "finite explicit pointer required")
    parts = path.split("/")[1:]
    require(len(parts) <= 16, "pointer depth exceeds bound")
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if type(value) is dict:
            require(part in value, "explicit pointer key absent")
            value = value[part]
        else:
            require(type(value) is list and part.isdecimal(), "list pointer required")
            index = int(part)
            require(index < len(value), "pointer index outside list")
            value = value[index]
    return value


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
    if counts["attempted_poll_lifecycles"] > 18 or counts["attempted_poll_lifecycles"] > 64:
        errors.append({"stage": "cap", "type": "WorkerLifecycleCap",
                       "message": "T2 attempted poll18/parent64 cap exceeded"})
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




def author_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()


def cas_author(path, expected_raw, value, mode, progress):
    require(stable_bytes(path) == expected_raw
            and stat.S_IMODE(path.lstat().st_mode) == mode,
            "author immediate full-bytes/mode CAS failed")
    raw = author_bytes(value)
    temporary = path.with_name(path.name + ".r258-next")
    write_bytes(temporary, raw, mode)
    require(stat.S_IMODE(temporary.lstat().st_mode) == mode,
            "replacement must retain original author mode")
    require(stable_bytes(path) == expected_raw
            and stat.S_IMODE(path.lstat().st_mode) == mode,
            "author changed before atomic replacement")
    progress["replace_attempted"] = True
    os.replace(temporary, path)
    progress["replaced"] = True
    require(stable_bytes(path) == raw and stat.S_IMODE(path.lstat().st_mode) == mode,
            "author exact mutation/mode readback differs")
    progress["readback_verified"] = True
    return raw


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


def retained_new_databases(index, evidence):
    records = []
    for row in index:
        path = Path(row["path"])
        if not stat.S_ISREG(row["mode"]) or path.suffix not in {".db", ".sqlite", ".sqlite3"}:
            continue
        raw = stable_bytes(path)
        require(bytes_pin(path, raw) == pin_identity(row), "new regular DB index changed")
        archive = write_bytes(evidence / "retained-databases" / (str(len(records)) + path.suffix), raw)
        sides = []
        for suffix in ("-wal", "-shm", "-journal"):
            side = Path(str(path) + suffix)
            if side.exists() or side.is_symlink():
                side_raw = stable_bytes(side)
                side_pin = bytes_pin(side, side_raw)
                side_archive = write_bytes(evidence / "retained-databases" / (
                    str(len(records)) + path.suffix + suffix), side_raw)
                sides.append({"path": str(side), "exists": True, "is_symlink": False,
                              "pin": side_pin, "archive": side_archive})
            else:
                sides.append({"path": str(side), "exists": False, "is_symlink": False, "pin": None})
        records.append({"pin": bytes_pin(path, raw), "archive": archive, "sidecars": sides,
                        "provenance": "This genuine new R268 diagnostic run only; old bytes not recovered"})
    return records


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


def bytes_record(row):
    raw = base64.b64decode(row["base64"], validate=True)
    require(checked(row["archive"]) == raw
            and bytes_pin(row["original"]["path"], raw) == pin_identity(row["original"]),
            "full physical/base64 generation differs")
    return raw


def authority(context):
    obs, source_gate = context["observation"], context["source_gate"]
    context_rows = context["context_manifest"]["changes"]
    require(type(context_rows) is list and len(context_rows) == 2, "two exact context generations required")
    mapped, context_after = {}, []
    expected_context = {context["plan"]["history_and_context"]["state_path"],
                        context["plan"]["history_and_context"]["phase_path"]}
    for row in context_rows:
        raw = bytes_record(row["before"])
        original = pin_identity(row["before"]["original"])
        require(original["path"] in expected_context and row["after"]["path"] == original["path"],
                "only exact STATE/PHASE generation mapping allowed")
        require(original["path"] not in mapped, "duplicate context path")
        mapped[original["path"]] = (original, raw)
        checked(row["after"])
        require(Path(row["after"]["path"]).lstat().st_mode == row["mode"], "context mode differs")
        context_after.append(pin_identity(row["after"]))
    require(set(mapped) == expected_context, "complete context mapping required")
    records = []
    require(type(obs["inputs"]) is list and len(obs["inputs"]) == 45, "exact45 observed inputs required")
    for ordinal, row in enumerate(obs["inputs"]):
        item = pin_identity(row)
        if item["path"] in mapped:
            original, raw = mapped[item["path"]]
            require(item == original and bytes_pin(item["path"], raw) == item,
                    "old context identity lacks exact before bytes")
            resolution = "EXACT_AUTHORIZED_CONTEXT_BEFORE"
        else:
            checked(item)
            resolution = "CURRENT_EXACT_IDENTITY"
        records.append({"ordinal": ordinal, "pin": item, "resolution": resolution})
    for row in source_gate["fixed_inputs"]:
        checked(row)
    for row in context["stable_controls"]:
        checked(row)
    old_result_pin = next(row for row in obs["inputs"]
                          if row["path"] == str(PARENT / "implementation/green/result.json"))
    old_result = decode_json(checked(old_result_pin))
    source_index = decode_json(checked(old_result["source_before"]))
    require(len(source_index["sources"]) == 27 and len(source_index["protected"]) == 211,
            "accepted current27/protected211 authority required")
    source_records = []
    for row in source_index["sources"]:
        raw = checked(row)
        require(checked(row["physical"]) == base64.b64decode(row["base64"], validate=True) == raw
                and Path(row["path"]).lstat().st_mode == row["mode"],
                "current source/full physical/base64/mode differs")
        source_records.append({**pin_identity(row), "mode": row["mode"], "physical": row["physical"]})
    for row in source_index["protected"]:
        checked(row)
    parent_plan_pin = next(row for row in obs["inputs"] if row["path"] == str(PARENT / "plan.json"))
    parent_plan = decode_json(checked(parent_plan_pin))
    old = decode_json(checked(parent_plan["inputs"]["complete_manifest"]))
    require(len(old["missing_registry35"]) == 35 and len(old["old_absent_sidecars90"]) == 90,
            "exact old35/90 history sets required")
    for row in old["missing_registry35"]:
        require(row["disposition"] == "HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245"
                and row["current_bytes"] is None and row["current_sha256"] is None
                and row["hash_match"] is None, "old missing identity/null disposition differs")
        absence(row["original"]["path"])
    for row in old["old_absent_sidecars90"]:
        require(row["exists"] is False and row["is_symlink"] is False, "old sidecar declaration differs")
        absence(row["path"])
    groups = old["retained_workspace_databases"]
    require(type(groups) is dict and set(groups) == {"R242_R248", "R251"}, "two old DB groups required")
    for name, count in (("R242_R248", 12), ("R251", 18)):
        require(type(groups[name]) is list and len(groups[name]) == count, "old DB group count differs")
        for row in groups[name]:
            checked(row["pin"])
            require(len(row["sidecars"]) == 3, "three exact old DB sidecar states required")
            for side in row["sidecars"]:
                require(side["exists"] is False and side["is_symlink"] is False
                        and side["pin"] is None, "old DB sidecar must remain absent")
                absence(side["path"])
    new_old_dbs = old_result["new_retained_databases"]
    require(type(new_old_dbs) is list and len(new_old_dbs) == 10, "ten retained R258 DB pairs required")
    present, absent_count = 0, 0
    for row in new_old_dbs:
        require(checked(row["pin"]) == checked(row["archive"]), "R258 DB original/archive bytes differ")
        require(len(row["sidecars"]) == 3, "three retained R258 sidecars required")
        for side in row["sidecars"]:
            if side["exists"]:
                require(side["is_symlink"] is False
                        and checked(side["pin"]) == checked(side["archive"]),
                        "present R258 sidecar pair differs")
                present += 1
            else:
                require(side["is_symlink"] is False and side["pin"] is None, "absent R258 sidecar differs")
                absence(side["path"])
                absent_count += 1
    require((present, absent_count) == (2, 28), "R258 present/absent sidecar counts differ")
    settlement_pin = next(row for row in obs["inputs"]
                          if row["path"] == str(PARENT / "root-parent-green7-failure-settlement.json"))
    settlement = decode_json(checked(settlement_pin))
    root_old = settlement["root_before"]
    bytes_record(root_old)
    root_checks = [row for row in obs["checks"] if row["kind"] == "exact_historical_root_generation"]
    require(len(root_checks) == 1
            and pin_identity(root_old["original"]) == pin_identity(root_checks[0]["expected_original"])
            and pin_identity(root_old["archive"]) == pin_identity(root_checks[0]["archive"]),
            "R266 exact historical ROOT generation differs")
    for role_path in (str(ROUNDS / "round158-p6-stage-b-local-temporal-publication-20261013"
                          / "root-command-ledger.json"),
                      str(ROUNDS / "round158-p6-stage-b-local-temporal-publication-20261013"
                          / "command-ledger.json")):
        record = next(row for row in obs["inputs"] if row["path"] == role_path)
        entry = decode_json(checked(record))["commands"]["t2_green"]
        require(entry["used"] == 1 and entry["remaining"] == 0 and entry["state"].startswith("SPENT"),
                "old original GREEN7 must remain spent")
    for row in context["sources"].values():
        checked(row)
    return {"input_records": records, "fixed_inputs": source_gate["fixed_inputs"],
            "context_after": context_after, "sources": source_records,
            "protected": source_index["protected"], "source_authority": old_result["source_before"],
            "accepted_history_generations": source_index["resolved_generations"],
            "history_reaudited_as_current": False, "missing_registry35": old["missing_registry35"],
            "old_absent_sidecars90": old["old_absent_sidecars90"],
            "old_retained_groups": groups, "R258_retained_DB_pairs": new_old_dbs,
            "old_ROOT_generation": root_old}


def preconditions():
    require(len(sys.argv) == 2, "one R268 diagnostic key required")
    name = sys.argv[1]
    require(name in {"wait_memory_failure", "dual_progress"} and Path.cwd() == ROOT
            and Path(sys.executable).absolute() == ROOT / ".venv/bin/python",
            "exact R268 command/interpreter/cwd required")
    plan_raw, obs_raw = stable_bytes(D / "plan.json"), stable_bytes(D / "input-observation.json")
    require(hashlib.sha256(plan_raw).hexdigest() == PLAN_SHA
            and hashlib.sha256(obs_raw).hexdigest() == OBS_SHA, "frozen R268 authority changed")
    plan, observation = decode_json(plan_raw), decode_json(obs_raw)
    command = plan["commands"][name]
    require(command["limits"]["child_wall_seconds"] == 600
            and command["limits"]["cleanup_total_seconds"] == 15
            and command["limits"]["raw_stream_threshold_bytes_each"] == 33554432
            and command["node_count"] == 1, "frozen diagnostic bounds differ")
    require([a for a in command["child_argv"] if "::" in a] == [command["node"]]
            and command["child_env"]["BIGSMALL_R158_COMMAND"] == "t2_green"
            and command["child_env"]["BIGSMALL_R268_COMMAND"] == name,
            "one exact diagnostic node/fixture sink required")
    source_path, script_path = D / "source-gate.json", D / "script-gate.json"
    source_gate, script_gate = read_json(source_path), read_json(script_path)
    require(source_gate["round"] == script_gate["round"] == "R268"
            and source_gate["status"] == "VERIFIED_SOURCE_ONLY"
            and script_gate["status"] == "VERIFIED_BY_ROOT", "ROOT source/runtime gates required")
    require(pin_identity(source_gate["plan"]) == bytes_pin(D / "plan.json", plan_raw)
            and pin_identity(source_gate["observation"]) == bytes_pin(D / "input-observation.json", obs_raw)
            and pin_identity(script_gate["plan"]) == pin_identity(source_gate["plan"])
            and pin_identity(script_gate["source_gate"]) == _t2_pin(source_path),
            "source/script plan binding differs")
    sources = source_gate["sources"]
    require(set(sources) == {"plugin", "runner"} and script_gate["sources"] == sources
            and pin_identity(sources["runner"]) == _t2_pin(Path(__file__)),
            "exact two reviewed R268 sources required")
    require(script_gate["commands"] == plan["commands"]
            and script_gate["role_files"] == plan["runner_contract"]["role_files"],
            "ROOT exact command/role interface differs")
    for row in (source_gate["input_check"], source_gate["native"], source_gate["interface"]):
        checked(row)
    context_manifest = decode_json(checked(source_gate["context_manifest"]))
    require(context_manifest["round"] == "R268"
            and context_manifest["status"] == "FACTUAL_CONTEXT_UPDATED"
            and context_manifest["T2_complete"] is False, "ROOT exact context manifest required")
    require(type(source_gate["fixed_inputs"]) is list, "finite fixed_inputs required")
    reservation_dir = D / "root-reservations"
    require(script_gate["reservation_directory"] == str(reservation_dir), "exact ROOT reservation path required")
    reservation_path = reservation_dir / (name + ".json")
    reservation = read_json(reservation_path)
    require(reservation["round"] == "R268" and reservation["command_id"] == name
            and type(reservation["reservation_id"]) is str and reservation["reservation_id"]
            and reservation["command"] == command and reservation["sources"] == sources
            and pin_identity(reservation["plan"]) == pin_identity(source_gate["plan"])
            and pin_identity(reservation["source_gate"]) == _t2_pin(source_path)
            and pin_identity(reservation["script_gate"]) == _t2_pin(script_path)
            and pin_identity(reservation["context_manifest"]) == pin_identity(source_gate["context_manifest"]),
            "exact ROOT per-command reservation required")
    roles = plan["runner_contract"]["role_files"]
    require(set(roles) == {"ROOT", "AUTHOR"} and len(reservation["role_before"]) == 2,
            "two new R268 roles required")
    full_before = {row["original"]["path"]: bytes_record(row) for row in reservation["role_before"]}
    require(set(full_before) == set(roles.values()), "two exact role-before paths required")
    root_before, author_before = (decode_json(full_before[roles[k]]) for k in ("ROOT", "AUTHOR"))
    for role, value in (("ROOT", root_before), ("AUTHOR", author_before)):
        require(value["round"] == "R268" and value["role"] == role
                and pin_identity(value["plan"]) == pin_identity(source_gate["plan"])
                and set(value["commands"]) == set(plan["commands"]), "exact new role identity required")
        entry = value["commands"][name]
        require(entry["authorized"] == 1 and entry["used"] == 0 and entry["remaining"] == 1
                and entry["state"] == "HELD_PENDING_ROOT_SOURCE_INPUT_ARGV_GATE"
                and entry["command"] == command, "selected new allowance not held")
    continuation = {"reservation_id": reservation["reservation_id"], "plan": reservation["plan"],
                    "source_gate": reservation["source_gate"], "script_gate": reservation["script_gate"],
                    "sources": sources, "command": command}
    root_expected = copy.deepcopy(root_before)
    root_entry = root_expected["commands"][name]
    root_entry.update(state="RESERVED_BY_ROOT", used=1, remaining=0,
                      reservation_id=reservation["reservation_id"])
    root_entry.setdefault("continuation", {})["R268"] = continuation
    require(reservation["root_role_after"]["path"] == roles["ROOT"]
            and decode_json(checked(reservation["root_role_after"])) == root_expected,
            "ROOT selected-key transition differs")
    author_raw = checked(reservation["author_role_before"])
    require(reservation["author_role_before"]["path"] == roles["AUTHOR"]
            and author_raw == full_before[roles["AUTHOR"]], "author exact current before differs")
    stable_controls = [_t2_pin(source_path), _t2_pin(script_path), _t2_pin(reservation_path),
                       reservation["root_role_after"], source_gate["context_manifest"]]
    context = {"plan": plan, "observation": observation, "command": command, "name": name,
               "source_gate": source_gate, "sources": sources, "reservation": reservation,
               "context_manifest": context_manifest, "stable_controls": stable_controls,
               "author_before": author_before, "author_raw": author_raw,
               "author_path": Path(roles["AUTHOR"]), "continuation": continuation}
    context["before_check"] = authority(context)
    directory = Path(command["outputs"]["directory"])
    require(directory == D / "implementation" / name, "exact new diagnostic output directory required")
    absence(directory)
    return context


def save_before(context):
    output = Path(context["command"]["outputs"]["directory"])
    output.mkdir(exist_ok=False)
    (output / "resources").mkdir(exist_ok=False)
    Path(context["command"]["outputs"]["passive"]).mkdir(exist_ok=False)
    sources = []
    for row in context["before_check"]["sources"]:
        raw = checked(row)
        archive = write_bytes(output / "before/sources" / Path(row["path"]).relative_to(ROOT),
                              raw, row["mode"])
        sources.append({**row, "physical": archive, "base64": base64.b64encode(raw).decode("ascii")})
    controls = []
    for ordinal, row in enumerate(context["stable_controls"] + [
            bytes_pin(context["author_path"], context["author_raw"])]):
        raw = checked(row)
        archive = write_bytes(output / "before/controls" / (str(ordinal) + ".bin"), raw)
        controls.append({"original": row, "archive": archive, "base64": base64.b64encode(raw).decode("ascii")})
    return write_json(Path(context["command"]["outputs"]["before"]), {
        "round": "R268", "command_id": context["name"], "sources": sources,
        "new_sources": context["sources"], "control_before": controls,
        "authority_before": context["before_check"], "runtime_scope": "diagnostic only"})


def junit_observation(path, node):
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
    require([row["nodeid"] for row in rows] == [node], "JUnit selected-node identity differs")
    return {"pin": bytes_pin(path, raw), "available": True, "records": rows, "tests": len(rows),
            "failures": sum(any(v["tag"] == "failure" for v in r["outcomes"]) for r in rows),
            "errors": sum(any(v["tag"] == "error" for v in r["outcomes"]) for r in rows),
            "skips": sum(any(v["tag"] == "skipped" for v in r["outcomes"]) for r in rows)}


def case_observations(summary, index, pid, node, root):
    sidecars = summary["records"] if summary is not None else []
    files = []
    for row in index or []:
        path = Path(row["path"])
        if not stat.S_ISREG(row["mode"]) or path.name not in CASE_NAMES:
            continue
        raw = stable_bytes(path)
        require(bytes_pin(path, raw) == pin_identity(row), "diagnostic scenario own pin changed")
        witnesses = []
        for sidecar in sidecars:
            data = sidecar["data"]
            if type(data) is not dict:
                continue
            require(data["pid"] == pid and data["nodeid"] == node, "actual sidecar identity differs")
            for resource in data.get("resources", []):
                if (resource.get("kind") == "sqlite_connection" and resource.get("initialized") is True
                        and resource.get("path") == str(path.parent / "events.db")
                        and resource.get("pid") == pid):
                    witnesses.append({"nodeid": data["nodeid"], "pid": data["pid"],
                                      "sidecar_pin": sidecar["pin"], "resource": resource})
        files.append({"pin": bytes_pin(path, raw), "base64": base64.b64encode(raw).decode("ascii"),
                      "relative_path": str(path.relative_to(root)), "witnesses": witnesses,
                      "actual_owner": ({"nodeid": node, "pid": pid} if witnesses else None),
                      "unavailable_reason": None if witnesses else "No completed matching actual sidecar witness"})
    return {"round": "R268", "expected_node": node, "actual_sidecars": sidecars, "scenario_files": files,
            "whole_run_resource_completeness": None if summary is None else summary["complete_sidecar_set"],
            "interpretation": "Partial timeout files are actual bytes; no missing owner or resource record is invented."}


def passive_observations(directory, pid, name, node, timed_out):
    rows, summary, errors = [], None, []
    paths = sorted(directory.iterdir())
    require(len(paths) <= 25, "plugin file count exceeds24 events+1summary")
    total = 0
    for path in paths:
        raw = stable_bytes(path)
        total += len(raw)
        require(total <= 262144, "plugin total byte bound exceeded")
        data = decode_json(raw)
        require(data["round"] == "R268" and data["pid"] == pid and data["command_id"] == name,
                "plugin actual child/command identity differs")
        if data.get("nodeid") is not None:
            require(data["nodeid"] == node, "plugin actual node differs")
        if data["kind"] == "summary":
            require(summary is None, "duplicate plugin final summary")
            summary = data
        rows.append({"pin": bytes_pin(path, raw), "data": data})
        errors.extend(data.get("observer_errors", []))
    configured = any(row["data"]["kind"] == "configure" for row in rows)
    require(configured, "actual plugin configure evidence missing")
    if summary is None and not timed_out:
        errors.append({"type": "MissingNormalSummary", "message": "No observed normal plugin finish"})
    if summary is not None:
        require(summary["hooks_equal"] is True, "plugin observed changed profile/trace identities")
    return {"records": rows, "summary": summary, "total_utf8_bytes": total,
            "observer_errors": errors, "normal_finish_observed": summary is not None,
            "post_unwind_values_are_non_atomic": True, "legal_RED": False, "GREEN": False}


def main():
    context = preconditions()
    name, command, reservation = context["name"], context["command"], context["reservation"]
    paths = {key: Path(value) for key, value in command["outputs"].items()}
    require(sys.argv == command["runner_argv"][1:], "exact runner argv required")
    basetemps = [a.split("=", 1)[1] for a in command["child_argv"] if a.startswith("--basetemp=")]
    require(basetemps == [str(paths["directory"] / "persistent-basetemp")],
            "one exact new persistent basetemp required")
    temp = Path(basetemps[0])
    before_pin = save_before(context)
    author = copy.deepcopy(context["author_before"])
    entry = author["commands"][name]
    entry.update(state="RESERVED", used=1, remaining=0, reservation_id=reservation["reservation_id"])
    entry.setdefault("continuation", {})["R268"] = context["continuation"]
    reserved_raw = author_bytes(author)
    spent = copy.deepcopy(author)
    spent["commands"][name].update(state="SPENT", result_path=str(paths["result"]))
    spent_raw = author_bytes(spent)
    mode = stat.S_IMODE(context["author_path"].lstat().st_mode)
    progress = {"replace_attempted": False, "replaced": False, "readback_verified": False}
    spent_progress = {"replace_attempted": False, "replaced": False, "readback_verified": False}
    process, previous_term, handler_installed = None, signal.getsignal(signal.SIGTERM), False
    started, captured = time.monotonic(), {}
    outcome = {
        "round": "R268", "command_id": name, "budget_identity": command["budget_identity"],
        "reservation_id": reservation["reservation_id"], "attempt": 1, "retry": 0,
        "started": False, "pid": None, "child_exit": None, "wrapper_exit": 2,
        "timed_out": False, "interrupted": False, "output_limited": False,
        "raw_stream_threshold_bytes_each": 33554432, "raw_size_observations": [],
        "errors": [], "cleanup": None, "JUnit": None, "resources": None, "cases": None,
        "passive": None, "index": None, "before": before_pin, "after": None,
        "prerequisite": None, "new_retained_databases": None,
        "diagnostic_complete": False, "evidence_may_be_partial": True,
        "legal_RED": False, "GREEN": False, "T2_complete": False,
        "author_reserved": None, "author_spent": None, "author_generation_observations": [],
        "reservation_progress": progress, "spent_progress": spent_progress,
        "known_author_generations": {
            "mode": mode,
            "before": {"pin": bytes_pin(context["author_path"], context["author_raw"]),
                       "base64": base64.b64encode(context["author_raw"]).decode("ascii")},
            "reserved": {"pin": bytes_pin(context["author_path"], reserved_raw),
                         "base64": base64.b64encode(reserved_raw).decode("ascii")},
            "spent": {"pin": bytes_pin(context["author_path"], spent_raw),
                      "base64": base64.b64encode(spent_raw).decode("ascii")}},
        "unobserved": {"OS_handles": None, "external_models": None, "GPU_native": None,
                       "network_calls": None, "terminated_node_whole_resource_denominator": None}}

    def capture_error(stage, error):
        outcome["errors"].append({"stage": stage, "type": type(error).__name__,
                                   "message": str(error), "traceback": traceback.format_exc()})

    def capture(stage, action):
        try:
            return action()
        except BaseException as error:
            capture_error(stage, error)
            return None

    def generation(stage):
        raw = stable_bytes(context["author_path"])
        actual_mode = stat.S_IMODE(context["author_path"].lstat().st_mode)
        label = "UNKNOWN"
        if actual_mode == mode:
            if raw == context["author_raw"]:
                label = "BEFORE"
            elif raw == reserved_raw:
                label = "RESERVED"
            elif raw == spent_raw:
                label = "SPENT"
        outcome["author_generation_observations"].append({
            "stage": stage, "state": label, "mode": actual_mode,
            "pin": bytes_pin(context["author_path"], raw),
            "base64": base64.b64encode(raw).decode("ascii")})
        return label

    def on_term(signum, frame):
        outcome["interrupted"] = True
        raise InterruptedError("outer TERM: same owned-group cleanup, no rerun")

    try:
        signal.signal(signal.SIGTERM, on_term)
        handler_installed = True
        cas_author(context["author_path"], context["author_raw"], author, mode, progress)
        outcome["author_reserved"] = bytes_pin(context["author_path"], reserved_raw)
        write_bytes(paths["directory"] / "before/author-reserved.json", reserved_raw, mode)
        invocation = {
            "round": "R268", "command_id": name, "budget_identity": command["budget_identity"],
            "reservation_id": reservation["reservation_id"], "command": command,
            "argv": command["child_argv"], "cwd": command["cwd"],
            "actual_environment": command["child_env"], "shell": False, "start_new_session": True,
            "stdin": "DEVNULL", "timeout_seconds": 600, "cleanup_total_seconds": 15,
            "TERM_grace_seconds": 5, "faulthandler_one_shot_seconds": 540,
            "stream_monitor_interval_max_seconds": 0.1, "raw_stream_threshold_bytes_each": 33554432,
            "exact_tool_arguments": reservation["exact_tool_arguments"],
            "source_gate": reservation["source_gate"], "script_gate": reservation["script_gate"],
            "sources": context["sources"], "source_before": before_pin,
            "role_before": reservation["role_before"],
            "author_reserved": outcome["author_reserved"], "author_mode": mode,
            "context_manifest": reservation["context_manifest"],
            "independent_tool_stdout": None, "independent_tool_stderr": None,
            "old_R158_budget_mutated": False}
        write_json(paths["invocation"], invocation)
        with paths["stdout"].open("xb") as stdout, paths["stderr"].open("xb") as stderr:
            before_spawn = time.monotonic()
            process = subprocess.Popen(command["child_argv"], cwd=command["cwd"],
                                       env=command["child_env"], stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, shell=False, start_new_session=True)
            outcome.update(started=True, pid=process.pid, monotonic_before_spawn=before_spawn,
                           monotonic_after_spawn=time.monotonic())
            # A conservative deadline starts before Popen, never later than actual spawn.
            deadline = before_spawn + 600
            while process.poll() is None:
                sizes = {"stdout": os.fstat(stdout.fileno()).st_size,
                         "stderr": os.fstat(stderr.fileno()).st_size}
                if any(value > 33554432 for value in sizes.values()):
                    outcome["output_limited"] = True
                    outcome["raw_size_observations"].append({
                        "monotonic": time.monotonic(), "observed_bytes": sizes,
                        "observed_overshoot_bytes": {k: max(0, v - 33554432) for k, v in sizes.items()}})
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    outcome["timed_out"] = True
                    break
                try:
                    process.wait(timeout=min(0.1, remaining))
                except subprocess.TimeoutExpired:
                    pass
    except BaseException as error:
        capture_error("reserved diagnostic lifecycle", error)
    finally:
        if handler_installed:
            capture("protect bounded cleanup", lambda: signal.signal(signal.SIGTERM, signal.SIG_IGN))
        try:
            if process is not None:
                outcome["cleanup"] = capture("owned process group", lambda: _t2_cleanup(process))
                outcome["child_exit"] = process.returncode
            outcome["JUnit"] = capture("actual optional JUnit", lambda: junit_observation(
                paths["JUnit"], command["node"]))
            prerequisite_path = Path(command["child_env"]["BIGSMALL_R235_PREREQUISITE_RECORD"])
            outcome["prerequisite"] = capture("actual R235 prerequisite", lambda: prerequisite(
                prerequisite_path, {"module": MODULE_PIN}, outcome["pid"]))
            captured["resources"] = capture("actual frozen sidecars", lambda: diagnostic_resources(
                paths["directory"] / "resources", "t2_green", command["child_argv"], outcome["pid"]))
            if captured["resources"] is not None:
                outcome["resources"] = capture("resource summary persistence", lambda: write_json(
                    paths["resources"], captured["resources"]))
            captured["passive"] = capture("bounded passive evidence", lambda: passive_observations(
                paths["passive"], outcome["pid"], name, command["node"], outcome["timed_out"]))
            outcome["passive"] = captured["passive"]
            index = capture("new persistent nofollow index", lambda: strict_index(temp))
            if index is not None:
                outcome["new_retained_databases"] = capture("new raw DB/sidecar retention",
                    lambda: retained_new_databases(index, paths["directory"]))
                outcome["index"] = capture("new persistent index persistence", lambda: write_json(
                    paths["index"], {"round": "R268", "command_id": name, "root": str(temp),
                                     "records": index, "new_retained_databases": outcome["new_retained_databases"],
                                     "SQL_executed": False, "old_missing_recovered": False}))
            outcome["cases"] = capture("available actual cases persistence", lambda: write_json(
                paths["cases"], case_observations(captured["resources"], index, outcome["pid"],
                                                 command["node"], temp)))
            after = capture("strict fixed source/history/old DB postconditions", lambda: authority(context))
            if after is not None:
                capture("authority before/after equality", lambda: require(
                    after == context["before_check"], "fixed authority observation changed"))
                outcome["after"] = capture("source-after persistence", lambda: write_json(paths["after"], after))
            for stream in ("stdout", "stderr"):
                outcome.setdefault("streams", {})[stream] = capture("raw " + stream, lambda stream=stream:
                    _t2_pin(paths[stream]))
            if outcome.get("streams", {}).get("stderr") is not None:
                def markers():
                    raw_stderr = stable_bytes(paths["stderr"])
                    return {"timeout_text_marker": b"Timeout (" in raw_stderr,
                            "thread_text_marker": b"Thread 0x" in raw_stderr,
                            "interpretation": "Raw textual markers only, not proof of deadlock/CPU/time origin"}
                outcome["faulthandler_raw_markers"] = capture("raw native stack markers", markers)
            for stream, row in outcome.get("streams", {}).items():
                if row is not None and row["bytes"] > 33554432:
                    outcome["output_limited"] = True
                    outcome["raw_size_observations"].append({
                        "stage": "after_cleanup", "stream": stream, "observed_bytes": row["bytes"],
                        "observed_overshoot_bytes": row["bytes"] - 33554432})
            outcome["file_index"] = capture("evidence nofollow index", lambda: _t2_index(paths["directory"]))
        finally:
            try:
                label = capture("observe reserved generation", lambda: generation("before-spend"))
                if label == "RESERVED":
                    outcome["author_reserved"] = bytes_pin(context["author_path"], reserved_raw)
                    capture("optional before-spend archive", lambda: write_bytes(
                        paths["directory"] / "before/author-before-spend.json", reserved_raw, mode))
                    capture("selected-key SPENT CAS", lambda: cas_author(
                        context["author_path"], reserved_raw, spent, mode, spent_progress))
                    label = capture("observe spent generation", lambda: generation("after-spend"))
                if label == "SPENT":
                    outcome["author_spent"] = bytes_pin(context["author_path"], spent_raw)
                    capture("optional spent archive", lambda: write_bytes(
                        paths["directory"] / "author-spent.json", spent_raw, mode))
                elif label == "BEFORE" and not progress["replaced"]:
                    outcome["author_consumption"] = "NOT_CONSUMED_NO_RETRY"
                else:
                    outcome["errors"].append({"stage": "author generation", "type": "UnresolvedGeneration",
                                              "message": "ROOT reconciliation required; no refund/retry/overwrite"})
            except BaseException as error:
                capture_error("independent author finalization", error)
            finally:
                if handler_installed:
                    capture("restore TERM handler", lambda: signal.signal(signal.SIGTERM, previous_term))
                cleanup = outcome["cleanup"]
                resource = captured.get("resources") or {}
                passive = captured.get("passive") or {}
                junit = outcome["JUnit"] or {}
                outcome["diagnostic_complete"] = bool(
                    outcome["started"] and not outcome["errors"] and not outcome["interrupted"]
                    and not outcome["output_limited"] and outcome["author_spent"] is not None
                    and cleanup is not None and cleanup["leader_reaped"]
                    and cleanup["group_remaining"] is False and not cleanup["cleanup_errors"]
                    and (outcome["timed_out"] or outcome["child_exit"] in {0, 1})
                    and resource.get("all_records_valid") is True
                    and not passive.get("observer_errors") and passive.get("records")
                    and (outcome["timed_out"] or junit.get("available") is True)
                    and (outcome["prerequisite"] or {}).get("accepted") is True
                    and outcome["before"] is not None and outcome["after"] is not None
                    and outcome["index"] is not None and outcome["cases"] is not None
                    and outcome["streams"]["stdout"] is not None and outcome["streams"]["stderr"] is not None)
                outcome["evidence_may_be_partial"] = bool(
                    outcome["timed_out"] or not resource.get("complete_sidecar_set")
                    or not passive.get("normal_finish_observed"))
                outcome["wrapper_exit"] = 0 if outcome["diagnostic_complete"] else 2
                outcome["elapsed_seconds"] = time.monotonic() - started
                outcome["classification"] = (
                    "DIAGNOSTIC_FACTS_ONLY_REQUIRES_ROOT_INTEGRITY_REVIEW"
                    if outcome["diagnostic_complete"] else "EVIDENCE_OR_INFRASTRUCTURE_FAILURE_STOP_NEXT_ASTRA")
                result_pin = capture("best-available result persistence", lambda: write_json(paths["result"], outcome))
                if result_pin is None:
                    outcome["wrapper_exit"] = 2
                display = {"round": "R268", "command_id": name, "child_exit": outcome["child_exit"],
                           "wrapper_exit": outcome["wrapper_exit"], "timed_out": outcome["timed_out"],
                           "output_limited": outcome["output_limited"],
                           "diagnostic_complete": outcome["diagnostic_complete"] if result_pin else False,
                           "result": result_pin, "legal_RED": False, "GREEN": False}
                rendered = json.dumps(display, ensure_ascii=False)
                require(len((rendered + "\n").encode()) <= 6000, "bounded diagnostic console exceeded")
                print(rendered)
    return outcome["wrapper_exit"]


if __name__ == "__main__":
    raise SystemExit(main())
