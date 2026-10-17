"""R179 exact gated child runner; no product import and no implicit commands."""
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
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014"
PLAN_SHA = "dc0cae1b743d6244469625e3f9a4fd14200efbb3e3669c422f1639f59b4be05e"


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


def reserve(command, gate):
    assert gate["state"] == "APPROVED"
    assert gate["launcher_argv"] == [sys.executable, str(Path(__file__).absolute()), command["id"]]
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert gate[key] == command[key]
    check(gate["script_pin"])
    assert gate["script_pin"]["path"] == str(Path(__file__).absolute())
    mutable = {str(D / name) for name in ("script-gate.json", "command-ledger.json",
                                        "root-command-ledger.json", "root-activation.json")}
    assert all(record["path"] not in mutable for record in gate["input_records"])
    for record in gate["input_records"]:
        check(record)
    root_slot = load(D / "root-command-ledger.json")["commands"][command["id"]]
    assert (root_slot["authorized"], root_slot["used"], root_slot["remaining"],
            root_slot["state"]) == (1, 1, 0, "RESERVED_BY_ROOT")
    assert root_slot["reservation_id"] == gate["reservation_id"]
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert root_slot[key] == command[key]
    path = D / "command-ledger.json"
    author = load(path)
    slot = author["commands"][command["id"]]
    assert (slot["authorized"], slot["used"], slot["remaining"], slot["state"]) == (1, 0, 1, "HELD")
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert slot[key] == command[key]
    before = path.read_bytes()
    slot.update(used=1, remaining=0, state="SPENT_BEFORE_SPAWN",
                reservation_id=gate["reservation_id"], attempts=1, retries=0)
    assert path.read_bytes() == before
    path.write_text(json.dumps(author, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return {"bytes": len(before), "sha256": digest(before),
            "base64": base64.b64encode(before).decode()}


def group_exists(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    return True


def terminate(process):
    errors = []
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if not group_exists(process.pid):
            break
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            errors.append("leader still running after " + sig.name)
        deadline = time.monotonic() + 5
        while group_exists(process.pid) and time.monotonic() < deadline:
            time.sleep(0.02)
    process.wait(timeout=5)
    return {"leader_reaped": process.returncode is not None,
            "group_remaining": group_exists(process.pid), "cleanup_notes": errors}


def junit(path, expected, phase):
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    names = Counter(case.attrib["name"] for case in cases)
    assert names == Counter(node.split("::", 1)[1] for node in expected)
    failures = [case for case in cases if case.find("failure") is not None]
    errors = [case for case in cases if case.find("error") is not None]
    skips = [case for case in cases if case.find("skipped") is not None]
    assert not errors and not skips
    if phase == "red":
        assert len(failures) == len(expected) == 19
        assert all("DID NOT RAISE" in (case.find("failure").text or "")
                   for case in failures), "RED must be named missing rejection after accepted baseline"
    else:
        assert not failures and len(cases) == 38
    return {"tests": len(cases), "failures": len(failures), "errors": len(errors),
            "skips": len(skips), "passes": len(cases) - len(failures)}


def resources(directory, process_pid, expected_map):
    counts = Counter()
    helper_nodes = Counter()
    sidecars = []
    for path in sorted(directory.iterdir()):
        assert path.suffix == ".json" and path.is_file() and not path.is_symlink()
        value = load(path)
        assert value["schema_version"] == "bigsmall.r175-memory-lifecycle.v1"
        assert value["pid"] == process_pid and value["success"] is True
        assert value["nodeid"] in expected_map
        helper_nodes[value["nodeid"]] += 1
        assert value["PYTEST_CURRENT_TEST"] == value["nodeid"] + " (call)"
        assert type(value["thread"]) is int and type(value["native_thread"]) is int
        assert value["thread"] > 0 and value["native_thread"] > 0
        assert value["repository_class_module"] == "cloud_edge_robot_arm.repositories.event_autonomy.memory"
        assert value["repository_class_qualname"] == "InMemoryEventAutonomyRepository"
        assert not value["untracked_close_calls"] and not value["failures"]
        assert all(value["methods_restored"].values()) and all(value["local_checks"].values())
        assert value["original_method_ids"] == value["restored_method_ids"]
        fields = {"_events", "_budgets", "_active_contracts", "_checkpoints"}
        assert set(value["observed_fields"]) == fields
        observed = Counter(allocation_attempts=len(value["objects"]))
        for obj in value["objects"]:
            assert obj["class_module"] == value["repository_class_module"]
            assert obj["class_qualname"] == value["repository_class_qualname"]
            assert obj["init_attempted"] is True and obj["initialized"] is True
            assert obj["init_error"] is None and obj["successful_close_observed"] is True
            assert obj["init_thread"] == value["thread"]
            assert obj["init_native_thread"] == value["native_thread"]
            observed["initialized"] += 1
            observed[obj["role"]] += 1
            successes = 0
            for call in obj["close_calls"]:
                observed["close_attempts"] += 1
                assert call["thread"] == value["thread"] and call["native_thread"] == value["native_thread"]
                assert call["returned"] is True and call["successful"] is True and call["error"] is None
                assert set(call["post_close_field_counts"]) == fields
                assert all(size == 0 for size in call["post_close_field_counts"].values())
                observed["close_returns"] += 1
                successes += 1
            assert successes >= 1
            observed["initialized_successfully_closed"] += 1
        for key in value["counts"]:
            assert value["counts"][key] == observed[key]
        counts.update(value["counts"])
        sidecars.append(pin(path))
    assert helper_nodes == Counter(expected_map)
    return {"actual_helper_calls": len(sidecars), "counts": dict(counts), "sidecars": sidecars,
            "actual_helper_calls_by_node": dict(helper_nodes),
            "observed_memory_closed": counts["initialized"] == counts["initialized_successfully_closed"],
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
                assert len(result) <= 10000, "bounded evidence file index"
    return result


def main():
    assert len(sys.argv) == 2 and sys.argv[1] in {"red", "ruff", "green"}
    phase = sys.argv[1]
    raw_plan = (D / "plan.json").read_bytes()
    assert digest(raw_plan) == PLAN_SHA and Path.cwd() == ROOT
    plan = json.loads(raw_plan)
    command = next(item for item in plan["commands"] if item["id"] == phase)
    assert command["timeout_seconds"] == (120 if phase == "ruff" else 600)
    gate = load(D / "script-gate.json")["commands"][phase]
    ledger_before = reserve(command, gate)
    evidence = Path(command["evidence_dir"])
    evidence.mkdir(parents=True, exist_ok=False)
    invocation_pin = write(evidence / "invocation.json", {
        "launcher_argv": [sys.executable, str(Path(__file__).absolute()), phase],
        "child_argv": command["argv"], "child_cwd": command["cwd"],
        "child_environment": command["finite_env"], "timeout_seconds": command["timeout_seconds"],
        "shell": False, "new_process_session": True, "attempt": 1, "retry": 0,
        "script_pin": pin(Path(__file__).absolute()), "reservation_id": gate["reservation_id"],
        "author_ledger_before": ledger_before, "outer_capture": gate["transport"],
    })
    process = None
    timed_out = False
    cleanup = None
    failures = []
    counts = None
    resource_summary = None
    temp = None
    try:
        if phase != "ruff":
            resource_dir = Path(command["finite_env"]["BIGSMALL_R175_RESOURCE_DIR"])
            assert resource_dir == evidence / "resources"
            resource_dir.mkdir(exist_ok=False)
            temp = Path(next(arg.split("=", 1)[1] for arg in command["argv"]
                             if arg.startswith("--basetemp=")))
            assert not temp.exists() and not temp.is_symlink()
        with (evidence / "stdout.txt").open("xb") as out, (evidence / "stderr.txt").open("xb") as err:
            process = subprocess.Popen(command["argv"], cwd=command["cwd"],
                env=dict(command["finite_env"]), shell=False, start_new_session=True,
                stdout=out, stderr=err)
            try:
                process.wait(timeout=command["timeout_seconds"])
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                cleanup = terminate(process)
        assert not timed_out and cleanup["leader_reaped"] and not cleanup["group_remaining"]
        expected_exit = 1 if phase == "red" else 0
        assert process.returncode == expected_exit
        if phase != "ruff":
            expected = plan["tests"][phase + "_nodes"]
            counts = junit(evidence / "junit.xml", expected, phase)
            mapping = gate["resource_map"]["helper_calls_by_node"]
            assert set(mapping) <= set(expected)
            assert all(type(value) is int and 0 <= value <= 1 for value in mapping.values())
            resource_summary = resources(resource_dir, process.pid, mapping)
            write(evidence / "resource-summary.json", resource_summary)
        for record in gate["input_records"]:
            check(record)
    except BaseException as error:
        failures.append({"type": type(error).__name__, "message": str(error),
                         "traceback": "".join(traceback.format_exception(error))})
        if process is not None and cleanup is None:
            cleanup = terminate(process)
    accepted = not failures
    child_exit = None if process is None else process.returncode
    wrapper_exit = child_exit if accepted else 2
    streams = {name: pin(evidence / name) if (evidence / name).exists() else None
               for name in ("stdout.txt", "stderr.txt")}
    result = {"round": "R179", "command": phase, "attempt": 1, "retry": 0,
              "child_exit": child_exit, "wrapper_exit": wrapper_exit, "timed_out": timed_out,
              "process_pid": None if process is None else process.pid, "cleanup": cleanup,
              "invocation": invocation_pin, "streams": streams, "JUnit": counts,
              "resource_summary": resource_summary, "failures": failures,
              "accepted_command_outcome": accepted, "T1_complete": False,
              "outer_capture": gate["transport"], "input_records": gate["input_records"],
              "file_index": index(evidence),
              "temp_index": [] if temp is None else index(temp)}
    result_pin = write(evidence / "result.json", result)
    print(json.dumps({"command": phase, "child_exit": child_exit,
                     "wrapper_exit": wrapper_exit, "result": result_pin,
                     "tests": counts, "accepted": accepted}))
    raise SystemExit(wrapper_exit)


if __name__ == "__main__":
    main()
