"""R158 finite runner. ROOT must reserve exactly one command before invocation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUND = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013"
PLAN_SHA = "70f51381f8f401c5456304d9eb12f019e7f903a582407ab7819447b8cd1f871b"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise ValueError(f"object metadata required: {path}")
    return value


def write_new(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def replace_ledger(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".reserved")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


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



def main() -> int:
    if len(sys.argv) != 2:
        raise ValueError("exactly one R158 command id required")
    command_id = sys.argv[1]
    is_t2 = command_id in {"t2_red", "t2_green"}
    if Path.cwd().resolve() != ROOT:
        raise ValueError("exact R158 cwd required")
    if Path(sys.executable).absolute() != ROOT / ".venv/bin/python":
        raise ValueError("use the exact project .venv/bin/python")
    if sha(ROUND / "plan.json") != PLAN_SHA:
        raise ValueError("frozen R158 plan changed")
    plan = read_json(ROUND / "plan.json")
    commands = plan["commands"]
    if type(commands) is not dict or len(commands) != 15 or command_id not in commands:
        raise ValueError("exact frozen command dictionary required")
    command = commands[command_id]
    root_ledger = read_json(ROUND / "root-command-ledger.json")
    root_entry = root_ledger["commands"][command_id]
    if (
        root_entry["state"] != "RESERVED_BY_ROOT"
        or root_entry["authorized"] != 1
        or root_entry["used"] != 1
        or root_entry["remaining"] != 0
        or root_entry["argv"] != command["argv"]
        or root_entry["cwd"] != command["cwd"]
    ):
        raise ValueError("ROOT must reserve exact argv/cwd once before calling")
    reservation = root_entry["reservation_id"]
    if type(reservation) is not str or not reservation:
        raise ValueError("nonempty ROOT reservation id required")
    ledger_path = ROUND / "command-ledger.json"
    ledger = read_json(ledger_path)
    entry = ledger["commands"][command_id]
    if entry["used"] != 0 or entry["remaining"] != 1 or entry["state"] != "HELD":
        raise ValueError("author command already consumed or not held")
    # ROOT reservation already consumes the command. Any uncertainty after this
    # point remains spent; the runner never restores an allowance.
    entry.update(used=1, remaining=0, state="RESERVED", reservation_id=reservation)
    replace_ledger(ledger_path, ledger)
    evidence = Path(command["evidence_dir"])
    evidence.mkdir(exist_ok=False)
    stdout_path = evidence / "stdout.txt"
    stderr_path = evidence / "stderr.txt"
    outcome = {
        "command_id": command_id, "reservation_id": reservation, "used": 1,
        "remaining": 0, "retry": 0, "exit_code": None, "timed_out": False,
        "started": False, "classification": "UNKNOWN_NOT_VALIDATED",
    }
    process = None
    started = time.monotonic()
    try:
        gate = read_json(ROUND / "script-gate.json")
        approved = gate["commands"][command_id]
        if (
            gate["schema_version"] != "bigsmall.r158-script-gate.v1"
            or approved["state"] != "APPROVED"
            or approved["reservation_id"] != reservation
            or approved["runner_sha256"] != sha(Path(__file__))
            or approved["argv"] != command["argv"]
            or approved["cwd"] != command["cwd"]
            or approved["env"] != command["env"]
            or approved["timeout_seconds"] != command["timeout_seconds"]
            or approved["timeout_seconds"] != 600
        ):
            raise ValueError("ROOT full-text/hash script gate does not match exact command")
        if command["timeout_seconds"] != 600:
            raise ValueError("exact600s timeout required")
        records = approved["input_records"]
        if type(records) is not list or not records:
            raise ValueError("current exact source/fixture pin gate required")
        for record in records:
            path = Path(record["path"])
            if not path.is_absolute() or len(path.read_bytes()) != record["bytes"] or sha(path) != record["sha256"]:
                raise ValueError(f"gate input changed: {path}")
        if command_id in {"mypy_baseline", "t1_red"}:
            before = read_json(ROUND / "implementation/t1/before.json")
            for source in before["sources"]:
                if source["relative_path"] != "tests/test_operational_runtime_closure.py":
                    if sha(Path(source["path"])) != source["sha256"]:
                        raise ValueError("production edit before baseline/RED")
            if (ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py").exists():
                raise ValueError("new product module must remain absent before RED")
        # No inherited credential or auto-configuration environment is emitted.
        # ROOT approves this exact finite process environment with the command.
        environment = {"PATH": str(ROOT / ".venv/bin") + ":/usr/bin:/bin", "LANG": "C.UTF-8"}
        environment.update(command["env"])
        fixture_controls = {}
        if command_id in {"t1_red", "t1_green", "final_new23"}:
            fixture_controls = {
                "BIGSMALL_R158_COMMAND": command_id,
                "BIGSMALL_R158_LEGACY_GOLDENS": str(Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round166-p6-t1-legacy-supervision-claim-timing-20261013/implementation/legacy_control/legacy-goldens.json")),
            }
        if is_t2:
            fixture_controls = {
                "BIGSMALL_R158_COMMAND": command_id,
                "BIGSMALL_R158_T2_RESOURCE_DIR": str(evidence / "resources"),
            }
        environment.update(fixture_controls)
        if approved["actual_environment"] != environment:
            raise ValueError("ROOT must approve the exact effective finite environment")
        fixture_map = ROUND / "implementation/t1/fixture-map.json"
        fixture_map_pin = None
        if is_t2:
            fixture_map = ROUND / "implementation/t2/fixture-map.json"
            fixture_map_pin = _t2_pin(fixture_map)
            if approved["fixture_map_pin"] != fixture_map_pin:
                raise ValueError("ROOT must approve the exact T2 fixture map")
            (evidence / "resources").mkdir(exist_ok=False)
        invocation = {
            "command_id": command_id, "reservation_id": reservation,
            "argv": command["argv"], "cwd": command["cwd"],
            "plan_env": command["env"],
            "actual_environment": environment, "fixture_controls": fixture_controls,
            "timeout_seconds": 600, "shell": False, "max_attempts": 1,
            "stdout": str(stdout_path), "stderr": str(stderr_path),
            "fixture_map": str(fixture_map),
            "runner_sha256": sha(Path(__file__)),
            "root_gate_sha256": sha(ROUND / "script-gate.json"),
            "root_ledger_sha256": sha(ROUND / "root-command-ledger.json"),
            "resource_caps": plan["fixture"]["caps"],
            "acceptance": "Raw actual process result only; ROOT evaluates RED and all later gates.",
        }
        if is_t2:
            invocation.update(fixture_map_pin=fixture_map_pin,
                              resource_sink=str(evidence / "resources"),
                              cleanup_grace_max_seconds=15)
        write_new(evidence / "invocation.json", invocation)
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            process = subprocess.Popen(
                command["argv"], cwd=command["cwd"], env=environment,
                stdout=stdout, stderr=stderr, shell=False, start_new_session=True,
            )
            outcome["started"] = True
            outcome["pid"] = process.pid
            try:
                outcome["exit_code"] = process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                outcome["timed_out"] = True
                if not is_t2:
                    os.killpg(process.pid, signal.SIGKILL)
                    outcome["exit_code"] = process.wait()
            finally:
                if is_t2:
                    outcome["cleanup"] = _t2_cleanup(process)
                    outcome["exit_code"] = process.returncode
        expected = command["expected_exit"]
        allowed = expected if type(expected) is list else [expected]
        outcome["expected_exit"] = expected
        outcome["expected_numeric_exit_matched"] = (
            not outcome["timed_out"] and outcome["exit_code"] in allowed
        )
        outcome["classification"] = (
            "ACTUAL_EXPECTED_NUMERIC_EXIT_REQUIRES_ROOT_CONTENT_REVIEW"
            if outcome["expected_numeric_exit_matched"]
            else "UNEXPECTED_FAILURE_STOP_NEXT_ASTRA"
        )
        for name, path in (("stdout", stdout_path), ("stderr", stderr_path)):
            outcome[name] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}
        if "-m" in command["argv"] and "pytest" in command["argv"]:
            junit = evidence / "junit.xml"
            outcome["junit"] = (
                {"path": str(junit), "bytes": junit.stat().st_size, "sha256": sha(junit)}
                if junit.is_file() else None
            )
            if outcome["junit"] is None:
                outcome["classification"] = "MISSING_JUNIT_STOP_NEXT_ASTRA"
        if is_t2:
            summary = _t2_resources(evidence / "resources", command_id, command["argv"],
                                    None if process is None else process.pid)
            write_new(evidence / "resource-summary.json", summary)
            outcome["resource_summary"] = _t2_pin(evidence / "resource-summary.json")
            outcome["resource_observations"] = summary
            outcome["file_index"] = _t2_index(evidence)
            temp = Path(next(arg.split("=", 1)[1] for arg in command["argv"]
                             if arg.startswith("--basetemp=")))
            outcome["temp_index"] = _t2_index(temp)
            cleanup = outcome["cleanup"]
            if (not cleanup["leader_reaped"] or cleanup["group_remaining"] is not False
                    or cleanup["cleanup_errors"] or not summary["all_records_valid"]):
                outcome["classification"] = "T2_RESOURCE_OR_PROCESS_CLOSURE_STOP_NEXT_ASTRA"
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        outcome["runner_failure"] = {"type": type(error).__name__, "message": str(error)}
        outcome["classification"] = "RUNNER_FAILURE_STOP_NEXT_ASTRA"
    finally:
        if is_t2 and "resource_summary" not in outcome:
            # Even a pre-spawn/gate failure retains every available real sidecar.
            try:
                summary = _t2_resources(evidence / "resources", command_id, command["argv"],
                                        None if process is None else process.pid)
                write_new(evidence / "resource-summary.json", summary)
                outcome["resource_summary"] = _t2_pin(evidence / "resource-summary.json")
                outcome["resource_observations"] = summary
                outcome["file_index"] = _t2_index(evidence)
                temp = Path(next(arg.split("=", 1)[1] for arg in command["argv"]
                                 if arg.startswith("--basetemp=")))
                outcome["temp_index"] = _t2_index(temp)
            except (OSError, ValueError, KeyError, TypeError) as error:
                outcome["t2_capture_failure"] = {"type": type(error).__name__,
                                                 "message": str(error)}
                outcome["classification"] = "T2_CAPTURE_FAILURE_STOP_NEXT_ASTRA"
        outcome["elapsed_seconds"] = time.monotonic() - started
        write_new(evidence / "result.json", outcome)
        entry.update(state="SPENT", result_path=str(evidence / "result.json"))
        replace_ledger(ledger_path, ledger)
    if is_t2:
        display = {
            "schema_version": "r158.t2-tool-summary.v1",
            **{key: outcome.get(key) for key in (
                "command_id", "classification", "exit_code", "timed_out", "started",
                "expected_numeric_exit_matched",
            )},
            "result": _t2_pin(evidence / "result.json"),
        }
        for key in ("stdout", "stderr", "junit", "resource_summary"):
            display[key] = outcome.get(key)
        rendered = json.dumps(display, ensure_ascii=False)
        if len((rendered + "\n").encode("utf-8")) > 6000:
            display = {
                "schema_version": "r158.t2-tool-summary.v1",
                "command_id": command_id, "result": _t2_pin(evidence / "result.json"),
                "display_omitted": True,
            }
            rendered = json.dumps(display, ensure_ascii=False)
        if len((rendered + "\n").encode("utf-8")) > 6000:
            raise ValueError("fixed T2 result-pin display exceeds byte bound")
        print(rendered)
    else:
        print(json.dumps(outcome, ensure_ascii=False))
    if outcome["classification"].endswith("STOP_NEXT_ASTRA"):
        return 2
    # RED1 and mypy1 remain their actual numeric exits; never relabel as exit0.
    return outcome["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
