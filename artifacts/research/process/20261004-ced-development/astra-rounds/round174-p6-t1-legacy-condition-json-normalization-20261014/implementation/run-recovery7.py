from pathlib import Path
import json
import hashlib
import os
import stat
import signal
import subprocess
import time
import traceback
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
PROCESS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
D158 = PROCESS / "round158-p6-stage-b-local-temporal-publication-20261013"
D174 = PROCESS / "round174-p6-t1-legacy-condition-json-normalization-20261014"
PLAN_SHA = "7ed5507ab0105106caaf434711d0c90893a0b783995471ba7535997ee31e655e"
MD_SHA = "7311015236f959f498ef4483cf024929dbde283d2eb9ddbcdfaae8d77610037a"
CANDIDATE_TEST_PIN = {"path":str(ROOT/"tests/test_operational_runtime_closure.py"),
    "bytes":125299,"sha256":"42a5a079bbd41b3d52adf683ce4e5c07d8678333adf367d7833dee496d4825d6"}

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()

def file_pin(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def canonical(raw):
    assert isinstance(raw, str) and raw.strip(), ("nonempty path", raw)
    relative = Path(raw)
    assert ".." not in relative.parts, ("parent traversal forbidden", raw)
    path = relative if relative.is_absolute() else ROOT / relative
    assert path.is_relative_to(ROOT), ("outside fixed repository root", raw)
    assert not path.is_symlink(), ("symlink forbidden", raw)
    for parent in path.parents:
        assert not parent.is_symlink(), ("symlink parent forbidden", raw)
        if parent == ROOT:
            break
    return str(path)

def coordinates(raw_paths):
    result = [canonical(raw) for raw in raw_paths]
    assert len(result) == len(set(result)), ("duplicate canonical paths", raw_paths)
    return result

def checked_pin(record):
    path = Path(canonical(record["path"]))
    receipt = file_pin(path)
    assert receipt["bytes"] == record["bytes"], ("pinned bytes", str(path))
    assert receipt["sha256"] == record["sha256"], ("pinned SHA256", str(path))
    return receipt

def parent_ledger_guard(path, role, command_ids):
    document = json.loads(path.read_bytes())
    if role == "author":
        assert document["schema_version"] == "bigsmall.r158-author-command-ledger.v1"
    commands = document["commands"]
    assert type(commands) is dict and len(commands) == 15 and set(commands) == set(command_ids)
    for name, entry in commands.items():
        for key in ("authorized", "used", "remaining"):
            assert type(entry[key]) is int
        assert entry["authorized"] == 1
        assert entry["cwd"] == str(ROOT)
        assert type(entry["argv"]) is list
        if name in ("mypy_baseline", "t1_red", "t1_green"):
            assert entry["used"] == 1 and entry["remaining"] == 0
            expected_state = "SPENT" if role == "author" else (
                "SPENT_ACTUAL_DIAGNOSTIC_CENSUS" if name == "mypy_baseline"
                else "SPENT_ACTUAL_UNEXPECTED_LEGACY_CONTROL_FAILURE" if name == "t1_red"
                else "SPENT_ACTUAL_UNEXPECTED_T1_GREEN_FAILURE"
            )
        else:
            assert entry["used"] == 0 and entry["remaining"] == 1
            expected_state = "HELD" if role == "author" else "HELD_PENDING_ROOT_GATE"
        assert entry["state"] == expected_state, ("role-specific state", role, name)
    assert sum(entry["used"] for entry in commands.values()) == 3
    assert sum(entry["remaining"] for entry in commands.values()) == 12
    return file_pin(path)


def exclusive_json(path, document):
    raw = encode(document)
    with path.open("xb") as stream:
        stream.write(raw)
    assert path.read_bytes() == raw
    return file_pin(path)

def local_ledger_guard(document, role, plan, selected_used):
    schema = "bigsmall.r174-command-ledger.v1" if role == "author" else "bigsmall.r174-root-command-ledger.v1"
    assert document["schema_version"] == schema and document["round"] == "R174"
    assert document["role"] == role and document["no_retry"] is True
    assert document["plan_sha256"] == PLAN_SHA
    commands = document["commands"]
    assert set(commands) == {"preparation_metadata","recovery7","ROOT_settlement_metadata"}
    for name, entry in commands.items():
        contract = plan["command_budget"][name]
        assert entry["authorized"] == entry["max_attempts"] == 1
        assert entry["timeout_seconds"] == contract["timeout_seconds"]
        assert entry["argv"] == contract.get("argv")
        assert entry["outer_runner_argv"] == contract.get("outer_runner_argv")
        assert entry["cwd"] == str(ROOT)
        if name == "preparation_metadata":
            assert entry["used"] == 1 and entry["remaining"] == 0 and entry["state"] == "SPENT"
        elif name == "recovery7" and selected_used:
            assert entry["used"] == 1 and entry["remaining"] == 0
            assert entry["state"] == ("SPENT" if role == "author" else "RESERVED_BY_ROOT")
        else:
            assert entry["used"] == 0 and entry["remaining"] == 1
            assert entry["state"] == ("HELD" if role == "author" else "HELD_PENDING_ROOT_GATE")

def group_exists(pid):
    try:
        os.killpg(pid,0)
        return True
    except ProcessLookupError:
        return False

def terminate_and_reap(process, actions):
    if group_exists(process.pid):
        os.killpg(process.pid,signal.SIGTERM)
        actions.append({"signal":"SIGTERM","process_group":process.pid})
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if group_exists(process.pid):
            os.killpg(process.pid,signal.SIGKILL)
            actions.append({"signal":"SIGKILL","process_group":process.pid})
        process.wait(timeout=5)
    return process.returncode

def fixture_index(directory):
    items = []
    if not directory.exists():
        return {"directory":str(directory),"exists":False,"items":[]}
    assert not directory.is_symlink()
    def walk(path):
        with os.scandir(path) as entries:
            for entry in sorted(entries,key=lambda item:item.name):
                info = entry.stat(follow_symlinks=False)
                record = {"path":entry.path,"relative_path":str(Path(entry.path).relative_to(directory)),
                    "mode":info.st_mode,"bytes":info.st_size,"mtime_ns":info.st_mtime_ns}
                if stat.S_ISLNK(info.st_mode):
                    record.update({"kind":"symlink","target":os.readlink(entry.path),"followed":False})
                elif stat.S_ISDIR(info.st_mode):
                    record["kind"] = "directory"
                    items.append(record)
                    walk(Path(entry.path))
                    continue
                elif stat.S_ISREG(info.st_mode):
                    record.update({"kind":"regular","content_read":False,"sha256":None})
                else:
                    record["kind"] = "other"
                items.append(record)
    walk(directory)
    return {"directory":str(directory),"exists":True,"items":items,
        "content_policy":"Generated fixture files and databases are indexed by lstat metadata only; no file contents or database queries."}

def junit_counts(path, expected_nodes):
    document = ET.fromstring(path.read_bytes())
    cases = list(document.iter("testcase"))
    names = [item.attrib.get("name") for item in cases]
    expected_names = [node.split("::",1)[1] for node in expected_nodes]
    assert len(cases) == 7 and sorted(names) == sorted(expected_names)
    assert len(names) == len(set(names))
    failures = sum(item.find("failure") is not None for item in cases)
    errors = sum(item.find("error") is not None for item in cases)
    skipped = sum(item.find("skipped") is not None for item in cases)
    return {"tests":len(cases),"passes":len(cases)-failures-errors-skipped,
        "failures":failures,"errors":errors,"skipped":skipped,"case_names":names}

assert Path.cwd() == ROOT
plan_bytes = (D174/"plan.json").read_bytes()
md_bytes = (D174/"plan.md").read_bytes()
assert sha(plan_bytes) == PLAN_SHA and sha(md_bytes) == MD_SHA
plan = json.loads(plan_bytes)
contract = plan["command_budget"]["recovery7"]
assert contract["timeout_seconds"] == 600 and contract["shell"] is False
assert contract["expected_product_exit"] == contract["expected_runner_exit"] == 0
assert canonical(__file__) == canonical(contract["outer_runner_argv"][1])
gate_path = D174/"recovery-gate.json"
gate_bytes = gate_path.read_bytes()
gate = json.loads(gate_bytes)
assert gate["schema_version"] == "bigsmall.r174-recovery-gate.v1"
assert gate["command_id"] == "recovery7" and gate["state"] == "APPROVED"
for key in ("argv","outer_runner_argv","actual_environment","cwd","timeout_seconds","resource_caps"):
    assert gate[key] == contract[key]
assert gate["candidate_test_pin"] == CANDIDATE_TEST_PIN
assert gate["outer_runner_argv"] == [str(ROOT/".venv/bin/python"),canonical(__file__)]
checked_pin(gate["source_pin"])
assert canonical(gate["source_pin"]["path"]) == canonical(__file__)
checked_pin(gate["candidate_snapshot_pin"])
checked_pin(gate["scope_proof_pin"])
snapshot_bytes = Path(gate["candidate_snapshot_pin"]["path"]).read_bytes()
snapshot = json.loads(snapshot_bytes)
assert len(snapshot["sources"]) == 24 and len(snapshot["protected"]) == 211
assert snapshot["usage"]["R158_used"] == 3 and snapshot["usage"]["R158_remaining"] == 12
checked_pin(CANDIDATE_TEST_PIN)
input_records = gate["input_records"]
assert isinstance(input_records,list) and len(input_records) >= 24+211
coordinates([item["path"] for item in input_records])
mutable_paths = {str(D174/"command-ledger.json"),str(D174/"root-command-ledger.json"),str(gate_path)}
assert not mutable_paths.intersection(canonical(item["path"]) for item in input_records)
pre_input_pins = [checked_pin(item) for item in input_records]
for item in snapshot["source_pins"]+snapshot["protected"]+snapshot["parent_ledger_pins"]:
    checked_pin(item)
parent_plan = json.loads((D158/"plan.json").read_bytes())
parent_ledgers = [parent_ledger_guard(D158/"command-ledger.json","author",parent_plan["commands"]),
    parent_ledger_guard(D158/"root-command-ledger.json","root",parent_plan["commands"])]
assert parent_ledgers == snapshot["parent_ledger_pins"]
root_ledger_path = D174/"root-command-ledger.json"
author_ledger_path = D174/"command-ledger.json"
root_ledger_bytes = root_ledger_path.read_bytes()
author_ledger_bytes = author_ledger_path.read_bytes()
root_ledger = json.loads(root_ledger_bytes)
author_ledger = json.loads(author_ledger_bytes)
local_ledger_guard(root_ledger,"root",plan,True)
local_ledger_guard(author_ledger,"author",plan,False)
root_entry = root_ledger["commands"]["recovery7"]
assert isinstance(root_entry["reservation_id"],str) and root_entry["reservation_id"]
output = Path(canonical(contract["output_directory"]))
basetemp = Path(contract["basetemp"])
assert str(basetemp) == "/tmp/bigsmall-p6-r174-t1-green-recovery"
assert not output.exists() and not output.is_symlink()
assert not basetemp.exists() and not basetemp.is_symlink()
raw_paths = set(plan["evidence_outputs"]["raw"])
for name in ("invocation.json","result.json","stdout.txt","stderr.txt","junit.xml","fixture-index.json","post-run-input-pins.json"):
    assert str(output/name) in raw_paths
entry = author_ledger["commands"]["recovery7"]
entry.update({"used":1,"remaining":0,"state":"SPENT",
    "reservation_id":root_entry["reservation_id"],"attempts":1,"retries":0})
spent_author_bytes = encode(author_ledger)
assert author_ledger_path.read_bytes() == author_ledger_bytes
author_ledger_path.write_bytes(spent_author_bytes)
assert author_ledger_path.read_bytes() == spent_author_bytes
output.mkdir(parents=True,exist_ok=False)
started_utc = datetime.now(UTC).isoformat()
invocation = {"schema_version":"bigsmall.r174-recovery7-invocation.v1","command_id":"recovery7",
    "reservation_id":root_entry["reservation_id"],"argv":contract["argv"],
    "outer_runner_argv":contract["outer_runner_argv"],"cwd":str(ROOT),
    "actual_environment":contract["actual_environment"],"shell":False,
    "start_new_session":True,"timeout_seconds":600,"attempts":1,"retries":0,
    "source_pin":gate["source_pin"],"candidate_test_pin":CANDIDATE_TEST_PIN,
    "resource_caps":contract["resource_caps"],"started_utc":started_utc,
    "parent_commands_immutable":True,"pre_input_pins":pre_input_pins}
invocation_pin = exclusive_json(output/"invocation.json",invocation)
started = False
timed_out = False
process = None
product_exit = None
spawn_error = None
cleanup_errors = []
cleanup_actions = []
remaining_process_group = None
launch_monotonic = time.monotonic()
with (output/"stdout.txt").open("xb") as stdout_stream, (output/"stderr.txt").open("xb") as stderr_stream:
    try:
        process = subprocess.Popen(contract["argv"],cwd=str(ROOT),env=contract["actual_environment"],
            shell=False,start_new_session=True,stdout=stdout_stream,stderr=stderr_stream)
        started = True
        try:
            product_exit = process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            timed_out = True
            product_exit = terminate_and_reap(process,cleanup_actions)
    except (OSError,ValueError,subprocess.TimeoutExpired) as error:
        spawn_error = {"type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()}
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    product_exit = terminate_and_reap(process,cleanup_actions)
                remaining_process_group = group_exists(process.pid)
                if remaining_process_group:
                    os.killpg(process.pid,signal.SIGKILL)
                    cleanup_actions.append({"signal":"SIGKILL","reason":"remaining process group after leader exit","process_group":process.pid})
                    cleanup_errors.append("Unexpected descendants remained after main child exit; closure not established.")
            except (OSError,subprocess.TimeoutExpired) as error:
                cleanup_errors.append({"type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()})
child_elapsed = time.monotonic()-launch_monotonic
junit = None
evidence_errors = []
post_input_pins = []
try:
    if (output/"junit.xml").exists():
        junit = junit_counts(output/"junit.xml",contract["argv"][6:13])
    else:
        evidence_errors.append("JUnit absent")
except (ET.ParseError,AssertionError,OSError,TypeError,ValueError) as error:
    evidence_errors.append({"phase":"junit","type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()})
try:
    index = fixture_index(basetemp)
except (OSError,AssertionError) as error:
    index = {"directory":str(basetemp),"index_error":str(error),"closure":None}
    evidence_errors.append({"phase":"fixture index","type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()})
index_pin = exclusive_json(output/"fixture-index.json",index)
try:
    post_input_pins = [checked_pin(item) for item in input_records]
    assert post_input_pins == pre_input_pins
    for item in snapshot["source_pins"]+snapshot["protected"]+parent_ledgers:
        checked_pin(item)
    assert gate_path.read_bytes() == gate_bytes
    assert (D174/"plan.json").read_bytes() == plan_bytes and (D174/"plan.md").read_bytes() == md_bytes
    assert Path(gate["candidate_snapshot_pin"]["path"]).read_bytes() == snapshot_bytes
    assert root_ledger_path.read_bytes() == root_ledger_bytes
    assert author_ledger_path.read_bytes() == spent_author_bytes
    checked_pin(gate["source_pin"])
    checked_pin(gate["scope_proof_pin"])
except (OSError,AssertionError,ValueError) as error:
    evidence_errors.append({"phase":"post input guards","type":type(error).__name__,"message":str(error),"traceback":traceback.format_exc()})
post_pin = exclusive_json(output/"post-run-input-pins.json",{
    "schema_version":"bigsmall.r174-recovery7-post-input-pins.v1","input_pins":post_input_pins,
    "matches_pre_run":post_input_pins == pre_input_pins and not any(
        isinstance(item,dict) and item.get("phase") == "post input guards" for item in evidence_errors),
    "errors":evidence_errors})
expected = contract["expected_junit"]
junit_matched = junit is not None and all(junit[key] == value for key,value in expected.items())
numeric_matched = product_exit == contract["expected_product_exit"]
runner_exit = 0 if started and not timed_out and numeric_matched and junit_matched and not cleanup_errors and not evidence_errors and spawn_error is None else 2
artifacts = [invocation_pin,file_pin(output/"stdout.txt"),file_pin(output/"stderr.txt"),index_pin,post_pin]
if (output/"junit.xml").exists():
    artifacts.append(file_pin(output/"junit.xml"))
result = {"schema_version":"bigsmall.r174-recovery7-result.v1","command_id":"recovery7",
    "reservation_id":root_entry["reservation_id"],"used":1,"remaining":0,"attempts":1,"retries":0,
    "started":started,"pid":None if process is None else process.pid,
    "product_exit":product_exit,"runner_exit":runner_exit,"expected_product_exit":0,"expected_runner_exit":0,
    "numeric_exit_matched":numeric_matched,"junit":junit,"junit_matched":junit_matched,
    "timed_out":timed_out,"child_and_cleanup_elapsed_seconds":child_elapsed,
    "started_utc":started_utc,"finished_utc":datetime.now(UTC).isoformat(),
    "spawn_error":spawn_error,"cleanup":{"actions":cleanup_actions,"errors":cleanup_errors,
        "leader_reaped":None if process is None else process.poll() is not None,
        "remaining_process_group_observed":remaining_process_group},
    "resource_evidence":{"caps":contract["resource_caps"],
        "worker_lifecycles":None,"maximum_workers_concurrent":None,
        "broker_threads_per_worker":None,"heartbeat_threads_per_worker":None,
        "external_model_calls":None,"network_calls":None,"GPU_native_calls":None,
        "worker_and_thread_closure":None,"test_lifecycle_evidence":None,
        "limit":"No runtime counters or closure artifact was added to immutable tests. Unknown evidence stays unknown for ROOT settlement."},
    "evidence_errors":evidence_errors,"artifacts":artifacts,
    "classification":"EXPECTED_NUMERIC_AND_JUNIT_PENDING_ROOT_RESOURCE_SETTLEMENT" if runner_exit == 0 else "UNEXPECTED_FAILURE_STOP_NEXT_ASTRA",
    "original_R158_GREEN":{"spent":True,"passes":5,"failures":2,"reset":False},
    "targeted_R173_accessor_execution":False,"T1_complete":False,"B9_complete":False,
    "T12_complete":False,"native":False,"actual":False,"formal":False}
result_pin = exclusive_json(output/"result.json",result)
print(json.dumps({"command_id":"recovery7","reservation_id":root_entry["reservation_id"],
    "product_exit":product_exit,"runner_exit":runner_exit,"timed_out":timed_out,
    "junit":junit,"classification":result["classification"],"result":result_pin,
    "artifacts":artifacts,"resources":result["resource_evidence"]},sort_keys=True))
raise SystemExit(runner_exit)
