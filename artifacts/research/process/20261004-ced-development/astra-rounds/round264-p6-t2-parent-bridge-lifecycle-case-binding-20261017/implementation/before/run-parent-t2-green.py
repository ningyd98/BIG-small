"""R258 green-only bridge: one original R158 t2_green allowance."""
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
D = ROUNDS / "round258-p6-t2-parent-green7-continuation-20261017"
PARENT = ROUNDS / "round158-p6-stage-b-local-temporal-publication-20261013"
PLAN_SHA = "50970ee4e58d28f7732686ff11befd01f1d56a3657a200d97dba9b45ffa764e7"
OBS_SHA = "8213421ccb98f9bdc8370d909cda26a7366cc44c9f4fe12a9d463c5f5e2899d9"
PARENT_PLAN_SHA = "70f51381f8f401c5456304d9eb12f019e7f903a582407ab7819447b8cd1f871b"
COMMAND = "t2_green"
CASE_NAMES = {"after-both-lock-denial.json", "true-commit-loss.json",
              "restart-no-authority.json", "same-owner-exact-history.json",
              "one-CAS-no-refund.json", "complete-writer-inventory.json"}


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


def _t2_resources(directory: Path, command_id: str, argv: list[str], process_pid: int | None) -> dict:
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
            if command_id == "t2_green" and value["entered_behavior"] is not True:
                raise ValueError("T2 GREEN must enter every behavioral body")
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
            if command_id == "t2_green" and value["observations"]["assertions_completed"] is not True:
                raise ValueError("T2 behavioral assertions did not complete")
        except (OSError, ValueError, TypeError, KeyError) as error:
            record["error"] = {"type": type(error).__name__, "message": str(error)}
            errors.append({"path": str(path), **record["error"]})
        records.append(record)
    mapping_match = nodes == Counter(expected)
    if not mapping_match:
        errors.append({"stage": "helper map", "type": "MissingOrDuplicateNode",
                       "message": "exactly one actual attempt sidecar per selected node required"})
    if counts["attempted_poll_lifecycles"] > 18 or counts["attempted_poll_lifecycles"] > 64:
        errors.append({"stage": "cap", "type": "WorkerLifecycleCap",
                       "message": "T2 attempted poll18/parent64 cap exceeded"})
    valid = not errors and mapping_match
    return {"schema_version": "bigsmall.r158-t2-resource-summary.v1",
            "command_id": command_id, "actual_node_attempts": len(records),
            "actual_node_counts": dict(nodes), "records": records,
            "counts": dict(counts), "all_records_valid": valid, "validation_errors": errors,
            "peak_active_polls_per_node": peak_active_polls,
            "interpretation": "Interface RED may reject before allocation; never behavioral proof.",
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




def map_bytes(mappings, original, raw, evidence):
    require(bytes_pin(original["path"], raw) == pin_identity(original),
            "historical bytes do not match exact original")
    item = identity_key(original)
    if item in mappings:
        require(mappings[item]["raw"] == raw, "conflicting same-generation bytes")
    else:
        mappings[item] = {"original": pin_identity(original), "raw": raw, "evidence": evidence}


def resolved(record, mappings):
    item = pin_identity(record)
    if identity_key(item) in mappings:
        raw = mappings[identity_key(item)]["raw"]
        require(bytes_pin(item["path"], raw) == item, "historical mapping changed")
        return raw, "EXACT_PHYSICAL_OR_FULL_BASE64_GENERATION"
    return checked(item), "CURRENT_EXACT_IDENTITY"


def full_before_row(row, mappings):
    require(type(row) is dict and set(row) == {"original", "archive", "base64"},
            "exact full-before record required")
    raw = base64.b64decode(row["base64"], validate=True)
    require(checked(row["archive"]) == raw, "physical/full-base64 before mismatch")
    map_bytes(mappings, row["original"], raw, {"archive": row["archive"]})
    return raw


def verify_preserved_databases(groups):
    require(type(groups) is dict and set(groups) == {"R242_R248", "R251"},
            "two exact retained DB groups required")
    output = {}
    for name, count in (("R242_R248", 12), ("R251", 18)):
        rows = groups[name]
        require(type(rows) is list and len(rows) == count, "retained DB group count differs")
        observed = []
        for ordinal, row in enumerate(rows):
            require(type(row) is dict and set(row) == {"pin", "sidecars", "provenance"}
                    and type(row["provenance"]) is str, "retained DB record shape differs")
            checked(row["pin"])
            require(type(row["sidecars"]) is list and len(row["sidecars"]) == 3,
                    "retained DB sidecars differ")
            for side in row["sidecars"]:
                require(type(side) is dict and set(side) == {"path", "exists", "is_symlink", "pin"}
                        and side["exists"] is False and side["is_symlink"] is False
                        and side["pin"] is None, "exact absent old DB sidecar required")
                absence(side["path"])
            observed.append({"group": name, "ordinal": ordinal, "record": row,
                             "current_pin": pin_identity(row["pin"]), "hash_match": True})
        output[name] = observed
    return output


def verify_authorities(context):
    plan, obs, mappings = context["plan"], context["observation"], context["mappings"]
    records = []
    for origin, rows in (("observation.inputs", obs["inputs"]),
                         ("plan.inputs.fixed_metadata", plan["inputs"]["fixed_metadata"]),
                         ("source_gate.fixed_inputs", context["source_gate"]["fixed_inputs"])):
        require(type(rows) is list, "finite exact input list required")
        for ordinal, row in enumerate(rows):
            item = pin_identity(row)
            if identity_key(item) in context["missing"]:
                mode = "EXACT_REGISTERED_HISTORICAL_UNAVAILABLE"
            else:
                _, mode = resolved(item, mappings)
            records.append({"origin": origin, "ordinal": ordinal, "pin": item, "resolution": mode})
    for row in context["missing"].values():
        original, authority = row["original"], row["authority"]
        raw, _ = resolved(authority["pin"], mappings)
        container = decode_json(raw)
        selector, ordinal = authority["selector"], authority["ordinal"]
        require(type(ordinal) is int and ordinal >= 0, "registered ordinal required")
        if selector == "input_records":
            rows = container["input_records"]
            require(type(rows) is list and ordinal < len(rows), "input_records ordinal differs")
            selected = rows[ordinal]
        elif selector == "new_retained_databases.pin":
            rows = container["new_retained_databases"]
            require(type(rows) is list and ordinal < len(rows)
                    and type(rows[ordinal]) is dict, "new DB ordinal differs")
            selected = rows[ordinal]["pin"]
        else:
            raise ValueError("unapproved missing-authority selector")
        require(pin_identity(selected) == pin_identity(original), "missing authority identity differs")
        require(row["disposition"] == "HISTORICAL_BYTES_CURRENTLY_UNAVAILABLE_R245"
                and row["current_exists"] is False and row["current_is_symlink"] is False
                and row["current_bytes"] is None and row["current_sha256"] is None
                and row["hash_match"] is None, "missing registry disposition differs")
        absence(original["path"])
    require(len(obs["old_absent_sidecars90"]) == 90, "exact90 old sidecars required")
    sidecars = []
    for row in obs["old_absent_sidecars90"]:
        require(row["exists"] is False and row["is_symlink"] is False,
                "old sidecar absence declaration differs")
        sidecars.append(absence(row["path"]))
    sources = []
    require(len(obs["current_sources27"]) == 27 and len(obs["protected211"]) == 211,
            "exact current27/protected211 required")
    for row in obs["current_sources27"]:
        raw = checked(row)
        require(checked(row["physical"]) == raw
                and Path(row["path"]).lstat().st_mode == row["mode"],
                "current source/full physical/mode differ")
        sources.append({"pin": pin_identity(row), "mode": row["mode"], "physical": row["physical"]})
    for row in obs["protected211"]:
        checked(row)
    checked(plan["prerequisite"]["plugin"])
    checked(plan["prerequisite"]["module"])
    checked(context["source_gate"]["runner"])
    for row in context["stable_controls"]:
        checked(row)
    return {"input_records": records, "sources": sources, "protected": obs["protected211"],
            "missing_registry": list(context["missing"].values()), "old_sidecars": sidecars,
            "retained_workspace_databases": verify_preserved_databases(
                obs["retained_workspace_databases"]),
            "history_reaudited_as_current": False,
            "accepted_history_authority": plan["history"]["complete_source_authority"]}


def preconditions():
    require(sys.argv == [str(D / "implementation/run-parent-t2-green.py"), COMMAND],
            "one exact t2_green launcher required")
    require(Path.cwd() == ROOT and Path(sys.executable).absolute() == ROOT / ".venv/bin/python",
            "exact interpreter/cwd required")
    plan_raw = stable_bytes(D / "plan.json")
    obs_raw = stable_bytes(D / "input-observation.json")
    require(hashlib.sha256(plan_raw).hexdigest() == PLAN_SHA
            and hashlib.sha256(obs_raw).hexdigest() == OBS_SHA, "frozen R258 authority changed")
    plan, obs = decode_json(plan_raw), decode_json(obs_raw)
    parent_raw = stable_bytes(PARENT / "plan.json")
    require(hashlib.sha256(parent_raw).hexdigest() == PARENT_PLAN_SHA, "original R158 plan changed")
    original_plan = decode_json(parent_raw)
    require(type(original_plan["commands"]) is dict and len(original_plan["commands"]) == 15,
            "original15 keyed commands required")
    command = plan["command"]
    require(command["command_id"] == COMMAND and command["node_count"] == 7
            and command["original_record"] == original_plan["commands"][COMMAND],
            "original t2_green command differs")
    require(command["child_timeout_seconds"] == 600 and command["cleanup_total_seconds"] == 15
            and command["TERM_grace_within_cleanup_seconds"] == 5,
            "original600+15 timing required")
    require([a for a in command["effective_argv"] if "::" in a] == command["exact_nodes"]
            and len(set(command["exact_nodes"])) == 7, "exact seven child nodes required")
    require(command["launcher_argv"] == [str(ROOT / ".venv/bin/python"),
                                        str(Path(__file__)), COMMAND],
            "exact bridge launcher required")
    source_path, script_path = D / "source-gate.json", D / "script-gate.json"
    source_raw, script_raw = stable_bytes(source_path), stable_bytes(script_path)
    source_gate, script_gate = decode_json(source_raw), decode_json(script_raw)
    require(source_gate["round"] == "R258" and source_gate["status"] == "VERIFIED_SOURCE_ONLY"
            and script_gate["round"] == "R258" and script_gate["status"] == "VERIFIED_BY_ROOT"
            and script_gate["command_id"] == COMMAND, "ROOT source/runtime gate required")
    checked(source_gate["plan"])
    checked(source_gate["observation"])
    checked(source_gate["input_check"])
    checked(source_gate["native"])
    require(pin_identity(source_gate["plan"]) == bytes_pin(D / "plan.json", plan_raw)
            and pin_identity(source_gate["observation"]) == bytes_pin(
                D / "input-observation.json", obs_raw), "source gate authority differs")
    own = bytes_pin(Path(__file__), stable_bytes(Path(__file__)))
    require(pin_identity(source_gate["runner"]) == own
            and pin_identity(script_gate["runner"]) == own
            and pin_identity(script_gate["source_gate"]) == bytes_pin(source_path, source_raw)
            and pin_identity(script_gate["plan"]) == pin_identity(source_gate["plan"])
            and pin_identity(script_gate["observation"]) == pin_identity(source_gate["observation"])
            and script_gate["command"] == command
            and script_gate["original_command"] == command["original_record"],
            "exact ROOT script/runner/command binding required")
    require(type(source_gate["fixed_inputs"]) is list, "ROOT fixed_inputs list required")
    reservation_path = D / "root-parent-green7-reservation.json"
    require(script_gate["root_reservation_path"] == str(reservation_path),
            "exact root reservation path required")
    reservation_raw = stable_bytes(reservation_path)
    reservation = decode_json(reservation_raw)
    require(reservation["round"] == "R258" and reservation["command_id"] == COMMAND
            and type(reservation["reservation_id"]) is str and reservation["reservation_id"]
            and pin_identity(reservation["plan"]) == pin_identity(source_gate["plan"])
            and pin_identity(reservation["runner"]) == own
            and pin_identity(reservation["source_gate"]) == bytes_pin(source_path, source_raw)
            and pin_identity(reservation["script_gate"]) == bytes_pin(script_path, script_raw)
            and reservation["effective_command"] == command
            and reservation["original_command"] == command["original_record"]
            and reservation["exact_tool_arguments"] == command["exact_tool_arguments"],
            "ROOT reservation exact command/gate binding differs")
    mappings = {}
    require(len(obs["existing_exact_maps47"]) == 47
            and len(obs["R251_exact_invocation_generations"]) == 22,
            "finite historical mapping counts differ")
    for row in obs["existing_exact_maps47"]:
        raw = checked(row["archive"])
        map_bytes(mappings, row["original"], raw, {"archive": row["archive"]})
    for row in obs["R251_exact_invocation_generations"]:
        raw = base64.b64decode(pointer(decode_json(checked(row["container"])), row["pointer"]),
                               validate=True)
        map_bytes(mappings, row["original"], raw,
                  {"container": row["container"], "pointer": row["pointer"]})
    require(type(reservation["role_before"]) is list and len(reservation["role_before"]) == 2,
            "two original role full-before records required")
    role_bytes = {}
    for row in reservation["role_before"]:
        raw = full_before_row(row, mappings)
        role_bytes[row["original"]["path"]] = raw
    root_path, author_path = PARENT / "root-command-ledger.json", PARENT / "command-ledger.json"
    require(set(role_bytes) == {str(root_path), str(author_path)}, "exact two parent role paths required")
    require(type(reservation["context_history"]) is list
            and type(reservation["context_before"]) is list
            and len(reservation["context_before"]) == 2, "finite context full-before required")
    context_paths = {pin_identity(v)["path"] for v in obs["mutable_context_timepoint"].values()}
    for row in reservation["context_history"]:
        require(row["original"]["path"] in context_paths, "only STATE/PHASE context histories allowed")
        full_before_row(row, mappings)
    context_current = []
    for row in reservation["context_before"]:
        require(row["original"]["path"] in context_paths, "exact STATE/PHASE context path required")
        raw = full_before_row(row, mappings)
        require(checked(row["original"]) == raw, "current context differs from root before")
        context_current.append(pin_identity(row["original"]))
    require({v["path"] for v in context_current} == context_paths, "two distinct contexts required")
    root_before = decode_json(role_bytes[str(root_path)])
    author_before = decode_json(role_bytes[str(author_path)])
    continuation = {"reservation_id": reservation["reservation_id"], "plan": reservation["plan"],
                    "runner": reservation["runner"], "source_gate": reservation["source_gate"],
                    "script_gate": reservation["script_gate"], "command": command}
    expected_root = copy.deepcopy(root_before)
    root_entry = expected_root["commands"][COMMAND]
    require(root_entry["used"] == 0 and root_entry["remaining"] == 1
            and root_entry["authorized"] == 1
            and root_entry["state"] == "HELD_PENDING_ROOT_GATE", "original ROOT allowance not held")
    require(root_entry["argv"] == command["original_record"]["argv"]
            and root_entry["cwd"] == command["cwd"], "original ROOT entry contract changed")
    root_entry.update(state="RESERVED_BY_ROOT", used=1, remaining=0,
                      reservation_id=reservation["reservation_id"])
    root_entry.setdefault("continuation", {})["R258"] = continuation
    expected_root["active_task"] = "T2"
    root_current_raw = checked(reservation["root_role_after"])
    require(reservation["root_role_after"]["path"] == str(root_path)
            and decode_json(root_current_raw) == expected_root,
            "ROOT exact keyed reservation transition differs")
    author_raw = checked(reservation["author_role_before"])
    require(reservation["author_role_before"]["path"] == str(author_path)
            and author_raw == role_bytes[str(author_path)], "author full before generation changed")
    entry = author_before["commands"][COMMAND]
    require(entry["used"] == 0 and entry["remaining"] == 1 and entry["state"] == "HELD"
            and entry["argv"] == command["original_record"]["argv"]
            and entry["cwd"] == command["cwd"], "original author allowance not held")
    history_contract = plan["history"]["complete_source_authority"]
    history = decode_json(checked(history_contract["source_index"]))
    checked(history_contract["ROOT_settlement"])
    require(len(history["history_observations"]) == 1689
            and len(history["explicit_maps"]) == 47 and len(history["input_records"]) == 48,
            "accepted finite source-history counts differ")
    require(type(obs["missing_registry35"]) is list and len(obs["missing_registry35"]) == 35,
            "exact35 unavailable history records required")
    missing = {identity_key(v["original"]): v for v in obs["missing_registry35"]}
    require(len(missing) == 35, "registered missing identity duplicate")
    require(len(obs["inputs"]) == 388 and len(plan["inputs"]["fixed_metadata"]) == 105,
            "frozen input list counts differ")
    stable_controls = [bytes_pin(source_path, source_raw), bytes_pin(script_path, script_raw),
                       bytes_pin(reservation_path, reservation_raw),
                       reservation["root_role_after"], *context_current,
                       bytes_pin(D / "root-activation.json", stable_bytes(D / "root-activation.json"))]
    context = {"plan": plan, "observation": obs, "command": command,
               "source_gate": source_gate, "script_gate": script_gate,
               "reservation": reservation, "reservation_raw": reservation_raw,
               "mappings": mappings, "missing": missing, "history": history,
               "stable_controls": stable_controls, "author_before": author_before,
               "author_raw": author_raw, "author_path": author_path,
               "continuation": continuation, "own": own}
    context["before_check"] = verify_authorities(context)
    paths = command["output_paths"]
    require(paths["evidence"] == str(D / "implementation/green")
            and paths["basetemp"] == str(D / "implementation/green/persistent-basetemp"),
            "new persistent evidence paths differ")
    evidence = Path(paths["evidence"])
    absence(evidence)
    for name, descriptor in (("outer_stdout", 1), ("outer_stderr", 2)):
        path = Path(paths[name])
        require(path.parent == D / "implementation", "exact outer stream directory required")
        linked, opened = path.lstat(), os.fstat(descriptor)
        require(stat.S_ISREG(linked.st_mode) and stat.S_ISREG(opened.st_mode)
                and (linked.st_dev, linked.st_ino) == (opened.st_dev, opened.st_ino)
                and linked.st_size == opened.st_size == 0,
                "outer stream must be the initially empty exclusive actual fd")
    for ancestor in evidence.parents:
        if ancestor == ROOT:
            break
        require(ancestor.is_dir() and not ancestor.is_symlink(), "unsafe evidence ancestor")
    return context


def save_before(context):
    evidence = Path(context["command"]["output_paths"]["evidence"])
    evidence.mkdir(exist_ok=False)
    (evidence / "resources").mkdir(exist_ok=False)
    rows = []
    for row in context["observation"]["current_sources27"]:
        raw = checked(row)
        relative = Path(row["path"]).relative_to(ROOT)
        archive = write_bytes(evidence / "before/sources" / relative, raw, row["mode"])
        rows.append({**pin_identity(row), "mode": row["mode"], "physical": archive,
                     "base64": base64.b64encode(raw).decode("ascii")})
    generations = []
    for ordinal, value in enumerate(context["mappings"].values()):
        archive = write_bytes(evidence / "before/history" / (str(ordinal) + ".bin"), value["raw"])
        generations.append({"original": value["original"], "archive": archive,
                            "base64": base64.b64encode(value["raw"]).decode("ascii"),
                            "source": value["evidence"]})
    controls = []
    for ordinal, item in enumerate(context["stable_controls"] + [
            bytes_pin(context["author_path"], context["author_raw"])]):
        raw = checked(item)
        archive = write_bytes(evidence / "before/controls" / (str(ordinal) + ".bin"), raw)
        controls.append({"original": item, "archive": archive,
                         "base64": base64.b64encode(raw).decode("ascii")})
    value = {"round": "R258", "command_id": COMMAND, "sources": rows,
             "protected": context["observation"]["protected211"],
             "history_observations": context["history"]["history_observations"],
             "explicit_maps": context["history"]["explicit_maps"],
             "accepted_history_input_records": context["history"]["input_records"],
             "accepted_history_authority": context["plan"]["history"]["complete_source_authority"],
             "history_reaudited_as_current": False, "resolved_generations": generations,
             "control_before": controls, "preconditions": context["before_check"]}
    return write_json(Path(context["command"]["output_paths"]["source_before"]), value)


def cas_author(path, expected_raw, value):
    require(stable_bytes(path) == expected_raw, "author immediate full-bytes CAS failed")
    raw = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    temporary = path.with_name(path.name + ".r258-next")
    write_bytes(temporary, raw)
    require(stable_bytes(path) == expected_raw, "author changed before atomic replacement")
    os.replace(temporary, path)
    require(stable_bytes(path) == raw, "author exact mutation readback differs")
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


def parse_junit(path, expected):
    raw = stable_bytes(path)
    tree = ET.fromstring(raw)
    nodes, details = [], []
    for element in tree.iter("testcase"):
        node = element.attrib["classname"].replace(".", "/") + ".py::" + element.attrib["name"]
        nodes.append(node)
        errors = []
        for child in element:
            if child.tag in {"failure", "error", "skipped"}:
                errors.append({"tag": child.tag, "attributes": dict(child.attrib), "text": child.text})
        details.append({"nodeid": node, "attributes": dict(element.attrib), "outcomes": errors})
    failures = sum(any(v["tag"] == "failure" for v in row["outcomes"]) for row in details)
    errors = sum(any(v["tag"] == "error" for v in row["outcomes"]) for row in details)
    skips = sum(any(v["tag"] == "skipped" for v in row["outcomes"]) for row in details)
    passes = sum(not row["outcomes"] for row in details)
    return {"pin": bytes_pin(path, raw), "nodeids": nodes, "tests": len(nodes),
            "passes": passes, "failures": failures, "errors": errors, "skips": skips,
            "exact_order_unique": nodes == expected and len(set(nodes)) == 7,
            "all_passed": nodes == expected and len(set(nodes)) == 7
                          and passes == 7 and failures == errors == skips == 0,
            "failure_details": details}


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


def capture_cases(summary, index, pid):
    records = []
    for row in summary["records"]:
        data = row["data"]
        records.append({"nodeid": None if data is None else data["nodeid"], "pid": pid,
                        "sidecar_pin": row["pin"], "sidecar_full_data": data,
                        "scenarios": None if data is None else data["observations"].get("scenarios"),
                        "observation_error": row["error"]})
    files = []
    for row in index:
        path = Path(row["path"])
        if stat.S_ISREG(row["mode"]) and path.name in CASE_NAMES:
            raw = stable_bytes(path)
            files.append({"pin": bytes_pin(path, raw), "relative_path": str(path.relative_to(
                Path(D / "implementation/green/persistent-basetemp"))),
                          "base64": base64.b64encode(raw).decode("ascii")})
    require({Path(row["pin"]["path"]).name for row in files} == CASE_NAMES,
            "all six frozen scenario file families must be preserved")
    return {"round": "R258", "command_id": COMMAND, "records": records,
            "scenario_files": files, "file_node_association": "Only actual sidecar node/PID links; "
            "scenario files retain real relative paths without invented per-node ownership."}


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
                        "provenance": "This genuine new R258 run only; old bytes not recovered"})
    return records


def main():
    context = preconditions()
    command, reservation = context["command"], context["reservation"]
    paths = {name: Path(value) for name, value in command["output_paths"].items()}
    source_before = save_before(context)
    author = copy.deepcopy(context["author_before"])
    entry = author["commands"][COMMAND]
    entry.update(state="RESERVED", used=1, remaining=0,
                 reservation_id=reservation["reservation_id"])
    entry.setdefault("continuation", {})["R258"] = context["continuation"]
    reserved_raw = cas_author(context["author_path"], context["author_raw"], author)
    reserved_pin = bytes_pin(context["author_path"], reserved_raw)
    write_bytes(paths["evidence"] / "before/author-reserved.json", reserved_raw)
    outcome = {"round": "R258", "command_id": COMMAND, "reservation_id": reservation["reservation_id"],
               "attempt": 1, "retry": 0, "started": False, "pid": None,
               "child_exit": None, "wrapper_exit": 2, "accepted_command_outcome": False,
               "timed_out": False, "interrupted": False, "errors": [], "cleanup": None,
               "JUnit": None, "resource_summary": None, "cases": None,
               "persistent_index": None, "prerequisite": None, "source_before": source_before,
               "source_after": None, "new_retained_databases": None,
               "author_reserved": reserved_pin, "author_spent": None,
               "runtime_evidence": "One original GREEN7 child; subject to independent ROOT acceptance",
               "unobserved": {"OS_handles": None, "external_models": None,
                              "GPU_native": None, "network_calls": None}}
    process, previous_term = None, signal.getsignal(signal.SIGTERM)
    started = time.monotonic()

    def on_term(signum, frame):
        outcome["interrupted"] = True
        raise InterruptedError("outer TERM: enter the same owned-group cleanup")

    def capture_error(stage, error):
        outcome["errors"].append({"stage": stage, "type": type(error).__name__,
                                   "message": str(error), "traceback": traceback.format_exc()})

    invocation = {"round": "R258", "command_id": COMMAND, "reservation_id": reservation["reservation_id"],
                  "argv": command["effective_argv"], "cwd": command["cwd"],
                  "actual_environment": command["finite_child_environment"], "shell": False,
                  "start_new_session": True, "stdin": "DEVNULL", "max_attempts": 1,
                  "timeout_seconds": 600, "cleanup_total_seconds": 15, "TERM_grace_seconds": 5,
                  "launcher_argv": command["launcher_argv"],
                  "exact_outer_tool_arguments": reservation["exact_tool_arguments"],
                  "stdout": str(paths["stdout"]), "stderr": str(paths["stderr"]),
                  "source_before": source_before, "runner": context["own"],
                  "root_reservation": _t2_pin(D / "root-parent-green7-reservation.json"),
                  "source_gate": reservation["source_gate"], "script_gate": reservation["script_gate"],
                  "author_before": reservation["author_role_before"],
                  "author_reserved": reserved_pin, "control_before": reservation["role_before"],
                  "context_before": reservation["context_before"],
                  "context_history": reservation["context_history"],
                  "input_records": context["before_check"]["input_records"],
                  "fixture_map": str(PARENT / "implementation/t2/fixture-map.json"),
                  "resource_sink": str(paths["evidence"] / "resources"),
                  "resource_caps": context["plan"]["resources"],
                  "independent_tool_stdout": None, "independent_tool_stderr": None}
    try:
        write_json(paths["invocation"], invocation)
        signal.signal(signal.SIGTERM, on_term)
        with paths["stdout"].open("xb") as stdout, paths["stderr"].open("xb") as stderr:
            try:
                process = subprocess.Popen(command["effective_argv"], cwd=str(ROOT),
                                           env=command["finite_child_environment"],
                                           stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                           shell=False, start_new_session=True)
                outcome.update(started=True, pid=process.pid)
                try:
                    process.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    outcome["timed_out"] = True
            finally:
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                if process is not None:
                    outcome["cleanup"] = _t2_cleanup(process)
                    outcome["child_exit"] = process.returncode
    except BaseException as error:
        capture_error("single child/cleanup", error)
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        # Each independent artifact is retained before any GREEN predicate is evaluated.
        tasks = [
            ("JUnit", lambda: parse_junit(paths["JUnit"], command["exact_nodes"])),
            ("prerequisite", lambda: prerequisite(paths["prerequisite"],
                                                  context["plan"]["prerequisite"], outcome["pid"])),
            ("resource_summary", lambda: _t2_resources(paths["evidence"] / "resources", COMMAND,
                                                        command["effective_argv"], outcome["pid"])),
        ]
        captured = {}
        for name, action in tasks:
            try:
                captured[name] = action()
                if name == "resource_summary":
                    outcome[name] = write_json(paths[name], captured[name])
                else:
                    outcome[name] = captured[name]
            except BaseException as error:
                capture_error(name, error)
        index = None
        try:
            index = strict_index(paths["basetemp"])
            new_dbs = retained_new_databases(index, paths["evidence"])
            outcome["new_retained_databases"] = new_dbs
            outcome["persistent_index"] = write_json(paths["file_database_index"], {
                "round": "R258", "root": str(paths["basetemp"]), "records": index,
                "new_retained_databases": new_dbs, "SQL_executed": False,
                "database_hash_policy": "Each real regular DB has its own stable full-byte SHA.",
                "old_missing_recovered": False})
        except BaseException as error:
            capture_error("persistent nofollow index/new DB retention", error)
        try:
            if "resource_summary" in captured and index is not None:
                outcome["cases"] = write_json(paths["cases"], capture_cases(
                    captured["resource_summary"], index, outcome["pid"]))
        except BaseException as error:
            capture_error("actual sidecars/scenario files", error)
        try:
            after = verify_authorities(context)
            require(after == context["before_check"], "pre/post frozen authority observation differs")
            outcome["source_after"] = write_json(paths["source_after"], after)
        except BaseException as error:
            capture_error("strict source/history/DB postconditions", error)
        for name in ("stdout", "stderr"):
            try:
                outcome.setdefault("streams", {})[name] = _t2_pin(paths[name])
            except BaseException as error:
                capture_error("independent child " + name, error)
        try:
            outcome["file_index"] = _t2_index(paths["evidence"])
        except BaseException as error:
            capture_error("full evidence index", error)
        # The same keyed original allowance is spent even when evidence or the child fails.
        try:
            spent = copy.deepcopy(author)
            spent_entry = spent["commands"][COMMAND]
            spent_entry.update(state="SPENT", result_path=str(paths["result"]))
            write_bytes(paths["evidence"] / "before/author-before-spend.json", reserved_raw)
            spent_raw = cas_author(context["author_path"], reserved_raw, spent)
            outcome["author_spent"] = bytes_pin(context["author_path"], spent_raw)
            write_bytes(paths["evidence"] / "author-spent.json", spent_raw)
        except BaseException as error:
            capture_error("author original-key spent CAS", error)
        cleanup = outcome["cleanup"]
        outcome["accepted_command_outcome"] = bool(
            outcome["started"] and outcome["child_exit"] == 0
            and not outcome["timed_out"] and not outcome["interrupted"] and not outcome["errors"]
            and cleanup is not None and cleanup["leader_reaped"]
            and cleanup["group_remaining"] is False and not cleanup["cleanup_errors"]
            and captured.get("JUnit", {}).get("all_passed") is True
            and captured.get("prerequisite", {}).get("accepted") is True
            and captured.get("resource_summary", {}).get("all_records_valid") is True
            and outcome["cases"] is not None and outcome["persistent_index"] is not None
            and outcome["source_after"] is not None and outcome["author_spent"] is not None)
        outcome["wrapper_exit"] = 0 if outcome["accepted_command_outcome"] else 2
        outcome["elapsed_seconds"] = time.monotonic() - started
        outcome["classification"] = ("GREEN7_CANDIDATE_REQUIRES_ROOT_INDEPENDENT_ACCEPTANCE"
                                     if outcome["accepted_command_outcome"]
                                     else "UNEXPECTED_OUTCOME_STOP_NEXT_ASTRA")
        result_pin = write_json(paths["result"], outcome)
        display = {"round": "R258", "command_id": COMMAND, "child_exit": outcome["child_exit"],
                   "wrapper_exit": outcome["wrapper_exit"],
                   "accepted_command_outcome": outcome["accepted_command_outcome"],
                   "timed_out": outcome["timed_out"], "error_count": len(outcome["errors"]),
                   "result": result_pin}
        rendered = json.dumps(display, ensure_ascii=False)
        require(len((rendered + "\n").encode("utf-8")) <= 6000, "bounded summary exceeded")
        print(rendered)
    return outcome["wrapper_exit"]


if __name__ == "__main__":
    raise SystemExit(main())
