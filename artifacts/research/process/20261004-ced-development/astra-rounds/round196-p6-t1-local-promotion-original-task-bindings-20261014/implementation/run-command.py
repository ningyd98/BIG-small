"""R196 exact child runner; capture observations before deciding legal outcome."""
from collections import Counter
from pathlib import Path
import base64
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
import traceback
import xml.etree.ElementTree as ET

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014"
PLAN_SHA = "c06e7433d113754a00438440e6c7777c2d4ba28236d228e886cc4dc1418a4338"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    path = Path(path)
    assert path.is_absolute() and not path.is_symlink()
    assert all(not parent.is_symlink() for parent in path.parents)
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": digest(raw)}


def check(record):
    assert pin(record["path"]) == {key: record[key] for key in ("path", "bytes", "sha256")}


def load(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with Path(path).open("xb") as stream:
        stream.write((json.dumps(value, ensure_ascii=False, sort_keys=True,
                                 allow_nan=False, indent=2) + "\n").encode())
    return pin(path)


def archived(path):
    raw = Path(path).read_bytes()
    return {**pin(path), "base64": base64.b64encode(raw).decode()}


def reserve(plan, command, gate):
    assert gate["state"] == "APPROVED"
    assert gate["launcher_argv"] == command["argv"]
    keys = ("argv", "child_argv", "cwd", "finite_env", "child_finite_env", "timeout_seconds", "expected_exit")
    for key in keys:
        assert gate[key] == command[key]
    check(gate["script_pin"])
    assert gate["script_pin"]["path"] == str(Path(__file__).absolute())
    mutable = {str(D / name) for name in ("script-gate.json", "command-ledger.json",
                                        "root-command-ledger.json", "root-activation.json")}
    assert all(record["path"] not in mutable for record in gate["input_records"])
    for record in gate["input_records"]:
        check(record)
    root_path, path = D / "root-command-ledger.json", D / "command-ledger.json"
    root_before, author_before = archived(root_path), archived(path)
    root, author = load(root_path), load(path)
    ids = {item["id"] for item in plan["commands"]}
    assert set(root["commands"]) == set(author["commands"]) == ids and len(ids) == 6
    assert root["schema_version"] == author["schema_version"] == "bigsmall.r196.command-ledger.v1"
    root_slot = root["commands"][command["id"]]
    assert (root_slot["authorized"], root_slot["used"], root_slot["remaining"],
            root_slot["state"]) == (1, 1, 0, "RESERVED_BY_ROOT")
    assert root_slot["reservation_id"] == gate["reservation_id"]
    assert root_slot["gate_pin"] == pin(D / "script-gate.json")
    slot = author["commands"][command["id"]]
    assert (slot["authorized"], slot["used"], slot["remaining"], slot["state"]) == (
        1, 0, 1, "HELD_PENDING_ROOT_GATE")
    for item in (slot, root_slot):
        for key in keys:
            assert item[key] == command[key]
    evidence = Path(command["evidence_dir"])
    evidence.mkdir(parents=True, exist_ok=False)
    invocation = write(evidence / "invocation.json", {
        "round": "R196", "command": command["id"], "argv": command["argv"],
        "launcher_argv": command["argv"], "launcher_environment": command["finite_env"],
        "child_argv": command["child_argv"], "child_cwd": command["cwd"],
        "child_environment": command["child_finite_env"], "timeout_seconds": command["timeout_seconds"],
        "cleanup_grace_max_seconds": 15, "shell": False, "new_process_session": True,
        "attempt": 1, "retry": 0, "script_pin": pin(Path(__file__).absolute()),
        "reservation_id": gate["reservation_id"], "author_ledger_before": author_before,
        "root_ledger_before": root_before, "gate_before": archived(D / "script-gate.json"),
        "activation_before": archived(D / "root-activation.json"), "outer_capture": gate["transport"]})
    assert pin(path) == {key: author_before[key] for key in ("path", "bytes", "sha256")}
    slot.update(used=1, remaining=0, state="SPENT_BEFORE_SPAWN",
                reservation_id=gate["reservation_id"], attempts=1, retry=0)
    path.write_text(json.dumps(author, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return evidence, invocation


def group_exists(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    return True


def terminate(process):
    """Only this process group; one cleanup deadline, at most 15 seconds."""
    deadline = time.monotonic() + 15
    notes = []
    if group_exists(process.pid):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=min(2, max(0, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            notes.append("leader required SIGKILL")
        if group_exists(process.pid):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    remaining = max(0, deadline - time.monotonic())
    try:
        process.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        notes.append("leader not reaped within cleanup deadline")
    while group_exists(process.pid) and time.monotonic() < deadline:
        time.sleep(min(0.02, max(0, deadline - time.monotonic())))
    return {"leader_reaped": process.returncode is not None,
            "group_remaining": group_exists(process.pid), "cleanup_notes": notes}


def junit_observation(path, expected):
    """Capture actual counts first; expected-success checks run afterwards."""
    parsed = ET.parse(path).getroot()
    cases = parsed.findall(".//testcase")
    failures = [case for case in cases if case.find("failure") is not None]
    errors = [case for case in cases if case.find("error") is not None]
    skips = [case for case in cases if case.find("skipped") is not None]
    names = Counter(case.attrib["name"] for case in cases)
    return ({"tests": len(cases), "passes": len(cases) - len(failures) - len(errors) - len(skips),
             "failures": len(failures), "errors": len(errors), "skips": len(skips)},
            {"pin": pin(path), "actual_names": dict(names),
             "names_match": names == Counter(node.split("::", 1)[1] for node in expected),
             "failure_details": [{"name": case.attrib["name"],
                                  "text": case.find("failure").text,
                                  "message": case.find("failure").get("message")}
                                 for case in failures],
             "error_details": [{"name": case.attrib["name"], "text": case.find("error").text}
                               for case in errors]})


def validated_sidecar(value, process_pid, expected_map):
    assert value["schema_version"] == "bigsmall.r175-memory-lifecycle.v1"
    assert value["pid"] == process_pid and value["success"] is True
    assert value["nodeid"] in expected_map
    assert value["PYTEST_CURRENT_TEST"] == value["nodeid"] + " (call)"
    assert type(value["thread"]) is int and value["thread"] > 0
    assert type(value["native_thread"]) is int and value["native_thread"] > 0
    assert value["repository_class_module"] == "cloud_edge_robot_arm.repositories.event_autonomy.memory"
    assert value["repository_class_qualname"] == "InMemoryEventAutonomyRepository"
    assert not value["untracked_close_calls"] and not value["failures"]
    assert value["methods_restored"] and all(value["methods_restored"].values())
    assert value["local_checks"] and all(value["local_checks"].values())
    assert value["original_method_ids"] == value["restored_method_ids"]
    fields = {"_events", "_budgets", "_active_contracts", "_checkpoints"}
    assert set(value["observed_fields"]) == fields
    actual = Counter(allocation_attempts=len(value["objects"]))
    for obj in value["objects"]:
        assert obj["class_module"] == value["repository_class_module"]
        assert obj["class_qualname"] == value["repository_class_qualname"]
        assert obj["init_attempted"] is True and obj["initialized"] is True
        assert obj["init_error"] is None and obj["successful_close_observed"] is True
        assert obj["init_thread"] == value["thread"]
        assert obj["init_native_thread"] == value["native_thread"]
        assert obj["role"] in {"primary", "transitive"}
        actual["initialized"] += 1
        actual[obj["role"]] += 1
        successes = 0
        for call in obj["close_calls"]:
            actual["close_attempts"] += 1
            assert call["thread"] == value["thread"] and call["native_thread"] == value["native_thread"]
            assert call["returned"] is True and call["successful"] is True and call["error"] is None
            assert set(call["post_close_field_counts"]) == fields
            assert all(size == 0 for size in call["post_close_field_counts"].values())
            actual["close_returns"] += 1
            successes += 1
        assert successes >= 1
        actual["initialized_successfully_closed"] += 1
    assert set(value["counts"]) == {
        "allocation_attempts", "initialized", "init_failed", "close_attempts",
        "close_returns", "close_errors", "initialized_successfully_closed", "primary", "transitive",
    }
    for key, count in value["counts"].items():
        assert count == actual[key]
    return Counter({key: actual[key] for key in value["counts"]})


def resource_observation(directory, process_pid, expected_map):
    # First retain every available raw sidecar identity and parsed observation.
    # A validation error below never prevents capture of later sidecars.
    records = []
    failures = []
    if directory.exists():
        paths = sorted(directory.iterdir())
        assert len(paths) <= 10000
        for path in paths:
            entry = {"path": str(path), "pin": None, "data": None, "error": None}
            try:
                assert path.suffix == ".json" and not path.is_symlink() and path.is_file()
                entry["pin"] = pin(path)
                entry["data"] = load(path)
            except (ValueError, OSError, AssertionError) as error:
                entry["error"] = {"type": type(error).__name__, "message": str(error)}
                failures.append({"path": str(path), **entry["error"]})
            records.append(entry)
    helper_nodes = Counter()
    counts = Counter()
    validated = 0
    for entry in records:
        if entry["data"] is None:
            continue
        try:
            value = entry["data"]
            actual = validated_sidecar(value, process_pid, expected_map)
            helper_nodes[value["nodeid"]] += 1
            counts.update(actual)
            validated += 1
        except (ValueError, TypeError, KeyError, AssertionError) as error:
            failures.append({"path": entry["path"], "type": type(error).__name__,
                             "message": str(error), "traceback": "".join(traceback.format_exception(error))})
    mapping_match = helper_nodes == Counter(expected_map)
    valid = not failures and mapping_match and validated == len(records)
    return {"actual_helper_calls": len(records), "actual_helper_calls_by_node": dict(helper_nodes),
            "counts": dict(counts) if valid else None, "all_sidecars_validated": valid,
            "helper_map_matches": mapping_match, "validation_errors": failures,
            "sidecars": [entry["pin"] for entry in records if entry["pin"] is not None],
            "raw_sidecar_observations": records,
            "observed_memory_closed": counts["initialized"] == counts["initialized_successfully_closed"] if valid else None,
            "unobserved": {"worker_lifecycles": None, "broker_threads": None,
                           "heartbeat_threads": None, "OS_handles": None,
                           "model_calls": None, "network_calls": None, "GPU_native": None}}


def index(root):
    result = []
    if not root.exists():
        return result
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                metadata = entry.stat(follow_symlinks=False)
                item = {"path": str(path), "mode": metadata.st_mode, "bytes": metadata.st_size,
                        "inode": metadata.st_ino, "symlink": stat.S_ISLNK(metadata.st_mode)}
                if item["symlink"]:
                    item["link_target"] = os.readlink(path)
                elif stat.S_ISDIR(metadata.st_mode):
                    pending.append(path)
                elif stat.S_ISREG(metadata.st_mode):
                    database = path.suffix in {".db", ".sqlite", ".sqlite3"} or path.name.endswith(("-wal", "-shm", "-journal"))
                    item["sha256"] = None if database else digest(path.read_bytes())
                    item["database_content_read"] = False
                result.append(item)
                assert len(result) <= 10000
    return result


def case_observation(directory, expected):
    records, errors = [], []
    names = Counter()
    for path in sorted(directory.iterdir()):
        entry = {"path": str(path), "pin": None, "data": None, "error": None}
        try:
            assert not path.is_symlink() and path.is_file() and path.suffix == ".json"
            entry["pin"] = pin(path)
            value = load(path)
            entry["data"] = value
            assert value["schema_version"] == "bigsmall.r196-case.v1"
            node = value["nodeid"]
            names[node] += 1
            assert node in expected
            assert path.name == digest(node.encode()) + ".json"
            assert value["hash_kind"] == "CANONICAL_RAW_ENVELOPE_SHA256"
            assert value["decoder_calls"] and value["mutation"] is not None
            for key in ("baseline_payload", "changed_payload"):
                assert isinstance(value[key], dict)
                raw = json.dumps(value[key], allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
                assert digest(raw) == value[key + "_sha256"]
        except (OSError, ValueError, TypeError, KeyError, AssertionError) as error:
            entry["error"] = {"type": type(error).__name__, "message": str(error)}
            errors.append({"path": str(path), **entry["error"]})
        records.append(entry)
        assert len(records) <= 64
    return {"records": records, "actual_node_counts": dict(names), "errors": errors,
            "names_match": names == Counter(expected),
            "all_valid": not errors and names == Counter(expected)}


def red_outcome(counts, observation, expected):
    if counts != {"tests": 8, "passes": 1, "failures": 7, "errors": 0, "skips": 0}:
        return False
    if observation is None or not observation["names_match"]:
        return False
    local = "test_r196_full_promotion_history[local]"
    legacy = "test_r196_full_promotion_history[legacy]"
    failures = {item["name"]: item for item in observation["failure_details"]}
    failed_names = {node.split("::", 1)[1] for node in expected} - {legacy}
    if set(failures) != failed_names or len(observation["failure_details"]) != 7:
        return False
    local_failure = failures[local]
    local_text = (local_failure["text"] or "") + "\n" + (local_failure["message"] or "")
    if ("ValueError: local history has no UTC authority deadline" not in local_text
            or "_bootstrap_promotion_source" not in local_text):
        return False
    for name, item in failures.items():
        if name != local and "DID NOT RAISE <class 'ValueError'>" not in (
                (item["text"] or "") + "\n" + (item["message"] or "")):
            return False
    return True


def main():
    assert len(sys.argv) == 2 and sys.argv[1] in {"red8", "ruff", "green63"}
    phase = sys.argv[1]
    raw_plan = (D / "plan.json").read_bytes()
    assert digest(raw_plan) == PLAN_SHA and Path.cwd() == ROOT
    plan = json.loads(raw_plan)
    command = next(item for item in plan["commands"] if item["id"] == phase)
    assert [sys.executable, str(Path(__file__).absolute()), phase] == command["argv"]
    assert dict(os.environ) == command["finite_env"]
    assert command["timeout_seconds"] == (120 if phase == "ruff" else 600)
    gate = load(D / "script-gate.json")["commands"][phase]
    evidence, invocation_pin = reserve(plan, command, gate)
    process, cleanup, counts, observation, resource_summary, cases = None, None, None, None, None, None
    timed_out, failures, temp = False, [], None
    started = time.monotonic()
    expected, mapping, new_nodes = [], {}, []
    try:
        if phase != "ruff":
            expected = plan["tests"]["red_nodes" if phase == "red8" else "green_nodes"]
            assert len(expected) == len(set(expected)) == (8 if phase == "red8" else 63)
            assert [arg for arg in command["child_argv"] if "::" in arg] == expected
            all_helpers = {**plan["resources"]["old_helper_calls"], **plan["resources"]["new_helper_calls"]}
            mapping = {node: all_helpers[node] for node in expected}
            assert mapping == {node: 1 for node in expected}
            assert gate["resource_map"]["helper_calls_by_node"] == mapping
            new_nodes = [node for node in expected if node in plan["resources"]["new_helper_calls"]]
            assert len(new_nodes) == (8 if phase == "red8" else 12)
            resource_dir = Path(command["child_finite_env"]["BIGSMALL_R175_RESOURCE_DIR"])
            assert resource_dir == evidence / "resources"
            resource_dir.mkdir(exist_ok=False)
            (evidence / "cases").mkdir(exist_ok=False)
            temp = Path(next(arg.split("=", 1)[1] for arg in command["child_argv"] if arg.startswith("--basetemp=")))
            assert not temp.exists() and not temp.is_symlink()
        with (evidence / "stdout.txt").open("xb") as out, (evidence / "stderr.txt").open("xb") as err:
            process = subprocess.Popen(command["child_argv"], cwd=command["cwd"],
                env=dict(command["child_finite_env"]), shell=False, start_new_session=True,
                stdout=out, stderr=err)
            try:
                process.wait(timeout=command["timeout_seconds"])
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                cleanup = terminate(process)
    except BaseException as error:
        failures.append({"stage": "spawn/wait", "type": type(error).__name__, "message": str(error),
                         "traceback": "".join(traceback.format_exception(error))})
        if process is not None and cleanup is None:
            cleanup = terminate(process)
    # Observation capture is independent from all expected-exit assertions.
    if phase != "ruff":
        try:
            if (evidence / "junit.xml").exists():
                counts, observation = junit_observation(evidence / "junit.xml", expected)
            else:
                failures.append({"stage": "JUnit", "type": "MissingEvidence", "message": "junit.xml absent"})
        except (ValueError, OSError, ET.ParseError, KeyError) as error:
            failures.append({"stage": "JUnit", "type": type(error).__name__, "message": str(error)})
        try:
            resource_summary = resource_observation(
                evidence / "resources", None if process is None else process.pid, mapping)
            write(evidence / "resource-summary.json", resource_summary)
        except (ValueError, OSError, TypeError, KeyError, AssertionError) as error:
            failures.append({"stage": "resources", "type": type(error).__name__, "message": str(error)})
        try:
            cases = case_observation(evidence / "cases", new_nodes)
        except (ValueError, OSError, TypeError, KeyError, AssertionError) as error:
            failures.append({"stage": "case capture", "type": type(error).__name__, "message": str(error)})
    child_exit = None if process is None else process.returncode
    if timed_out or cleanup is None or not cleanup["leader_reaped"] or cleanup["group_remaining"]:
        failures.append({"stage": "outcome", "type": "TimeoutOrCleanup", "message": "child/group not cleanly closed"})
    if child_exit != command["expected_exit"]:
        failures.append({"stage": "outcome", "type": "UnexpectedExit", "message": str(child_exit)})
    if phase != "ruff":
        legal = red_outcome(counts, observation, expected) if phase == "red8" else (
            counts == {"tests": 63, "passes": 63, "failures": 0, "errors": 0, "skips": 0}
            and observation is not None and observation["names_match"])
        if not legal:
            failures.append({"stage": "outcome", "type": "JUnitMismatch", "message": "exact planned node outcome not met"})
        if resource_summary is None or not resource_summary["all_sidecars_validated"]:
            failures.append({"stage": "outcome", "type": "ResourceMismatch", "message": "actual helper/close evidence not valid"})
        if cases is None or not cases["all_valid"]:
            failures.append({"stage": "outcome", "type": "CaseMismatch", "message": "new-node finally evidence incomplete"})
    try:
        for record in gate["input_records"]:
            check(record)
    except (OSError, ValueError, AssertionError) as error:
        failures.append({"stage": "input recheck", "type": type(error).__name__, "message": str(error)})
    accepted = not failures
    wrapper_exit = (1 if phase == "red8" else 0) if accepted else 2
    streams = {name: pin(evidence / name) if (evidence / name).exists() else None
               for name in ("stdout.txt", "stderr.txt")}
    result = {"round": "R196", "command": phase, "attempt": 1, "retry": 0,
              "child_exit": child_exit, "wrapper_exit": wrapper_exit, "timed_out": timed_out,
              "elapsed_seconds": time.monotonic() - started,
              "process_pid": None if process is None else process.pid, "cleanup": cleanup,
              "invocation": invocation_pin, "streams": streams, "JUnit": counts,
              "JUnit_observation": observation, "resource_summary": resource_summary,
              "case_evidence": cases, "failures": failures, "accepted_command_outcome": accepted,
              "T1_complete": False, "outer_capture": gate["transport"], "input_records": gate["input_records"],
              "file_index": index(evidence), "temp_index": [] if temp is None else index(temp)}
    result_pin = write(evidence / "result.json", result)
    print(json.dumps({"command": phase, "child_exit": child_exit, "wrapper_exit": wrapper_exit,
                      "result": result_pin, "JUnit": counts, "accepted": accepted}))
    raise SystemExit(wrapper_exit)


if __name__ == "__main__":
    main()

