"""ROOT R192 single bounded stdlib evidence settlement; no product imports/execution."""
from collections import Counter
from pathlib import Path
import base64
import copy
import hashlib
import json
import os
import signal
import stat
import sys
import time
import traceback
import xml.etree.ElementTree as ET

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round192-p6-t1-original-green38-unexpected-outcome-20261014")
B = D.parent
PLAN_SHA = "5f47ed17d70a2f14008aa6b277ec83f719836ede1b555252d6014e41fbb1a8aa"
ACTIVATION_SHA = "eec924266d4e9279507a68e4b87c3200dbf101e227864c9e3976f40191b2aee6"
SHARED = str(ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py")
PIN_KEYS = ("path", "bytes", "sha256")
P179 = B / "round179-p6-t1-detached-causality-hash-audit-20261014"
P182 = B / "round182-p6-t1-recursive-local-projection-closure-20261014"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    path = Path(path)
    assert path.is_absolute() and not path.is_symlink()
    assert all(not p.is_symlink() for p in path.parents)
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": sha(raw)}


def load(path):
    return json.loads(Path(path).read_bytes())


def check(record, history=None):
    expected = {k: record[k] for k in PIN_KEYS}
    if history is not None and record["path"] in history and expected == history[record["path"]]:
        return
    assert pin(record["path"]) == expected, expected


def unarchive(record, key="base64"):
    raw = base64.b64decode(record[key], validate=True)
    assert len(raw) == record["bytes"] and sha(raw) == record["sha256"]
    return raw


def write(path, value):
    with Path(path).open("xb") as f:
        f.write((json.dumps(value, ensure_ascii=False, sort_keys=True,
                            indent=2, allow_nan=False) + "\n").encode())
    return pin(path)


def command_for(plan, name):
    return next(c for c in plan["commands"] if c["id"] == name)


def actual_tool(directory, expected_exit, result):
    tool = load(directory / "tool-return.json")
    check(tool["result_pin"])
    assert tool["result_pin"] == pin(directory / "result.json")
    assert tool["attempt"] == 1 and tool["retry"] == 0
    actual = tool["completion"] if tool["completion"] is not None else tool["initial"]
    assert actual["exit_code"] == expected_exit and actual.get("session_id") is None
    for record in tool["outer_streams"].values():
        check(record)
    assert tool["actual_summary"] == result
    return tool


def junit(path, expected, failures):
    root = ET.parse(path).getroot()
    cases = root.findall(".//testcase")
    assert len(cases) == len(expected)
    observed = Counter(c.attrib["classname"].replace(".", "/") + ".py::" + c.attrib["name"]
                       for c in cases)
    assert observed == Counter(expected), (observed, expected)
    assert all(c.find("error") is None and c.find("skipped") is None for c in cases)
    failed = [c for c in cases if c.find("failure") is not None]
    assert len(failed) == failures
    if failures == len(expected):
        assert all("DID NOT RAISE" in c.find("failure").text for c in failed)
    return {"JUnit": pin(path), "tests": len(cases), "passes": len(cases)-len(failed),
            "failures": len(failed), "errors": 0, "skips": 0,
            "failed_nodes": [c.attrib["classname"].replace(".", "/") + ".py::" + c.attrib["name"] for c in failed]}


def indexes(result, current_temp=False):
    for x in result["file_index"]:
        if x.get("sha256") is not None:
            check(x)
    # Preserve opaque temporary database boundaries; inspect metadata without reading DB bytes.
    for x in (result["temp_index"] if current_temp else []):
        path = Path(x["path"])
        st = path.lstat()
        assert st.st_mode == x["mode"] and st.st_size == x["bytes"]
        assert path.is_symlink() == x["symlink"]
        if x["symlink"]:
            assert os.readlink(path) == x["link_target"]
        elif x.get("sha256") is not None:
            assert stat.S_ISREG(st.st_mode)
            check(x)
    return {"raw_index_entries": len(result["file_index"]),
            "temp_index_entries": len(result["temp_index"]),
            "database_query_count": 0}

def memory_records(summary, expected_map, pid):
    assert all(v is None for v in summary["unobserved"].values())
    helper = Counter()
    totals = Counter()
    observed = []
    fields = {"_events", "_budgets", "_active_contracts", "_checkpoints"}
    for record in summary["sidecars"]:
        check(record)
        v = load(record["path"])
        assert v["schema_version"] == "bigsmall.r175-memory-lifecycle.v1"
        assert v["pid"] == pid and v["success"] is True
        assert v["repository_class_module"] == "cloud_edge_robot_arm.repositories.event_autonomy.memory"
        assert v["repository_class_qualname"] == "InMemoryEventAutonomyRepository"
        assert v["PYTEST_CURRENT_TEST"] == v["nodeid"] + " (call)"
        assert type(v["thread"]) is int and v["thread"] > 0
        assert type(v["native_thread"]) is int and v["native_thread"] > 0
        assert not v["untracked_close_calls"] and not v["failures"]
        assert all(v["methods_restored"].values()) and all(v["local_checks"].values())
        assert v["original_method_ids"] == v["restored_method_ids"]
        assert set(v["observed_fields"]) == fields
        counts = Counter(allocation_attempts=len(v["objects"]))
        for obj in v["objects"]:
            assert obj["init_attempted"] is True and obj["initialized"] is True
            assert obj["init_error"] is None and obj["successful_close_observed"] is True
            assert obj["class_module"] == v["repository_class_module"]
            assert obj["class_qualname"] == v["repository_class_qualname"]
            assert obj["init_thread"] == v["thread"] and obj["init_native_thread"] == v["native_thread"]
            assert obj["close_calls"]
            counts["initialized"] += 1
            counts[obj["role"]] += 1
            for call in obj["close_calls"]:
                assert call["thread"] == v["thread"] and call["native_thread"] == v["native_thread"]
                assert call["returned"] is True and call["successful"] is True and call["error"] is None
                assert set(call["post_close_field_counts"]) == fields
                assert all(n == 0 for n in call["post_close_field_counts"].values())
                counts["close_attempts"] += 1
                counts["close_returns"] += 1
            counts["initialized_successfully_closed"] += 1
        assert all(counts[k] == n for k, n in v["counts"].items())
        totals.update(v["counts"])
        helper[v["nodeid"]] += 1
        observed.append(record)
    assert helper == Counter(expected_map)
    assert dict(totals) == summary["counts"]
    assert totals["initialized"] == totals["initialized_successfully_closed"]
    assert summary["actual_helper_calls"] == len(observed)
    assert summary["actual_helper_calls_by_node"] == dict(helper)
    assert summary["observed_memory_closed"] is True
    return {"helper_calls": len(observed), "counts": dict(totals),
            "sidecars": observed, "unobserved": summary["unobserved"]}




def parent_transitions():
    activation = load(D / "root-activation.json")
    assert sha((D / "root-activation.json").read_bytes()) == ACTIVATION_SHA
    check(activation["before_shared"])
    check(activation["before_metadata"])
    before_metadata = load(activation["before_metadata"]["path"])
    records = before_metadata["records"]
    assert len({x["path"] for x in records}) == len(records)
    for record in records:
        unarchive(record, "full_before_base64")
    transitions = activation["parent_ledger_transitions"]
    assert len(transitions) == 4
    old_to_current = {}
    for transition in transitions:
        old = transition["before"]["original"]
        archive = transition["before"]["archive"]
        check(archive)
        raw = Path(archive["path"]).read_bytes()
        assert (len(raw), sha(raw)) == (old["bytes"], old["sha256"])
        record = next(x for x in records if x["path"] == old["path"])
        assert unarchive(record, "full_before_base64") == raw
        check(transition["current_after"])
        prior = json.loads(raw)
        current = load(old["path"])
        s = current["commands"]["root_settlement"]
        assert (s["authorized"], s["used"], s["remaining"], s["state"]) == (1, 0, 1, "HELD_SUPERSEDED_R192")
        assert s["executable"] is False and s["reservation_id"] is None
        assert s["superseded_by"]["round"] == "R192" and s["superseded_by"]["command"] == "root_settlement"
        assert not Path(s["evidence_dir"]).exists()
        comparison = copy.deepcopy(current)
        comparison["commands"]["root_settlement"] = prior["commands"]["root_settlement"]
        if old["path"] == str(P179 / "root-command-ledger.json"):
            oldg, g = prior["commands"]["green"], current["commands"]["green"]
            assert (oldg["used"], oldg["remaining"], oldg["state"]) == (1, 0, "RESERVED_BY_ROOT")
            assert (g["used"], g["remaining"]) == (1, 0)
            assert g["state"] == "SPENT_ACTUAL_CHILD1_WRAPPER2_UNEXPECTED_GREEN38_FAILURE_ROOT_RECORDED"
            assert (g["actual_child_exit"], g["actual_wrapper_exit"], g["actual_tests"], g["actual_passes"], g["actual_failures"]) == (1, 2, 38, 37, 1)
            assert g["accepted_command_outcome"] is False
            check(g["result"]); check(g["tool"]); check(g["forensic_JUnit"]["source"])
            comparison["commands"]["green"] = oldg
        assert comparison == prior
        for name in ("prepare_red", "red", "prepare_green", "ruff", "green"):
            slot = current["commands"][name]
            assert (slot["used"], slot["remaining"]) == (1, 0)
        old_to_current[old["path"]] = transition
    assert set(old_to_current) == set(PLAN["input_roles"]["authorized_mutable_parent_ledgers"])
    for record in PLAN["inputs"]:
        if record["path"] == SHARED:
            assert (record["bytes"], record["sha256"]) == (activation["before_shared"]["bytes"], activation["before_shared"]["sha256"])
        elif record["path"] in old_to_current:
            assert record == old_to_current[record["path"]]["before"]["original"]
        else:
            check(record)
    return {"activation": pin(D / "root-activation.json"), "parent_ledgers": transitions,
            "initial_inputs": len(PLAN["inputs"]), "parent_counts_reset": False}


def old_preparation(parent, phase):
    directory = parent / "implementation" / ("prepare_" + phase)
    result = load(directory / "result.json")
    assert result["exit_code"] == 0 and result["command"] == "prepare_" + phase
    assert result["attempt"] == 1 and result["retry"] == 0
    assert result["test_execution"] is False and result["product_commands"] == 0
    actual_tool(directory, 0, result)
    for record in result["outputs"]:
        check(record)
    snap = load(directory / "candidate-snapshot.json")
    assert snap["phase"] == phase
    assert len(snap["sources"]) == (24 if parent == P179 else 25)
    assert len(snap["protected"]) == 211
    for record in snap["sources"]:
        unarchive(record)
    for record in snap["protected"]:
        check(record)
    invocation = load(directory / "invocation.json")
    original_command = command_for(load(parent / "plan.json"), "prepare_" + phase)
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert invocation[key] == original_command[key]
    assert json.loads(unarchive(invocation["author_ledger_before"]))["commands"]["prepare_" + phase]["used"] == 0
    history = {x["path"]: {k:x[k] for k in PIN_KEYS} for x in snap["sources"]}
    if parent == P182 and phase == "red":
        archives = (
            (parent / "implementation/prepare-evidence.py",
             B / "round191-p6-t1-root-source-proof-record-shape-20261014/implementation/before-prepare-evidence.py",
             13233, "77cb39339ff2f7aa5d4293174d0fbefb284e9554f16bfd0049c7856516b8e852"),
            (parent / "implementation/root-settlement.py",
             B / "round191-p6-t1-root-source-proof-record-shape-20261014/implementation/before-root-settlement.py",
             20629, "20a365502526256d38039bbcef061c9d6f7b9b522935aafa45f4cfab656b6e9a"),
        )
        for logical, archive, size, digest in archives:
            r = pin(archive)
            assert (r["bytes"], r["sha256"]) == (size, digest)
            history[str(logical)] = {"path": str(logical), "bytes": size, "sha256": digest}
    return {"result": pin(directory / "result.json"), "tool": pin(directory / "tool-return.json"),
            "snapshot": pin(directory / "candidate-snapshot.json"),
            "scope": pin(directory / "source-scope-proof.json")}, snap, history


def old_child(parent, name, history):
    directory = parent / "implementation" / name
    result = load(directory / "result.json")
    invocation = load(directory / "invocation.json")
    original_command = command_for(load(parent / "plan.json"), name)
    failed_original = parent == P179 and name == "green"
    child_exit = 1 if name == "red" or failed_original else 0
    wrapper_exit = 2 if failed_original else child_exit
    assert result["child_exit"] == child_exit and result["wrapper_exit"] == wrapper_exit
    assert result["accepted_command_outcome"] is (not failed_original)
    assert not result["timed_out"] and result["attempt"] == 1 and result["retry"] == 0
    assert result["cleanup"] == {"leader_reaped": True, "group_remaining": False, "cleanup_notes": []}
    for key, source in (("child_argv", "argv"), ("child_cwd", "cwd"), ("child_environment", "finite_env"), ("timeout_seconds", "timeout_seconds")):
        assert invocation[key] == original_command[source]
    assert invocation["shell"] is False and invocation["new_process_session"] is True
    assert invocation["attempt"] == 1 and invocation["retry"] == 0
    check(invocation["script_pin"], history)
    check(result["invocation"])
    for record in result["streams"].values():
        check(record)
    for record in result["input_records"]:
        check(record, history)
    actual_tool(directory, wrapper_exit, result)
    observed = {"result": pin(directory / "result.json"), "tool": pin(directory / "tool-return.json"),
                "child_exit": child_exit, "wrapper_exit": wrapper_exit, "indexes": indexes(result)}
    if name == "ruff":
        assert result["JUnit"] is None and result["resource_summary"] is None
    else:
        nodes = original_command["argv"][6:-2]
        failures = len(nodes) if name == "red" else (1 if failed_original else 0)
        observed.update(junit(directory / "junit.xml", nodes, failures))
        if failed_original:
            assert observed["failed_nodes"] == ["tests/test_operational_runtime_closure.py::test_r179_publication_history_getters[local]"]
            assert result["JUnit"] is None and result["resource_summary"] is None
            assert not (directory / "resource-summary.json").exists()
            assert result["failures"]
            observed["original_resource_summary"] = None
            observed["kind"] = "Preserved original failure; no retrospective resource aggregation"
        else:
            assert not result["failures"]
            expected = {"tests": len(nodes), "passes": len(nodes)-failures, "failures": failures, "errors": 0, "skips": 0}
            assert result["JUnit"] == expected
            summary = load(directory / "resource-summary.json")
            assert summary == result["resource_summary"]
            observed["resources"] = memory_records(summary, dict.fromkeys(nodes, 1), result["process_pid"])
    return observed


def original_histories():
    preparations, children, snapshots = {}, {}, {}
    for parent in (P179, P182):
        preparations[parent.name], children[parent.name], snapshots[parent.name] = {}, {}, {}
        histories = {}
        for phase in ("red", "green"):
            receipt, snap, history = old_preparation(parent, phase)
            preparations[parent.name][phase] = receipt
            snapshots[parent.name][phase] = snap
            histories[phase] = history
        for name in ("red", "ruff", "green"):
            children[parent.name][name] = old_child(parent, name, histories["red" if name == "red" else "green"])
    green179 = {x["path"]:x for x in snapshots[P179.name]["green"]["sources"]}
    green182 = {x["path"]:x for x in snapshots[P182.name]["green"]["sources"]}
    assert len(green179) == 24 and len(green182) == 25
    assert set(green179) < set(green182)
    for path, record in green179.items():
        assert unarchive(record) == unarchive(green182[path])
    assert unarchive(green182[SHARED]) == (D / "implementation/before-local-temporal.py").read_bytes()
    for path, record in green182.items():
        if path != SHARED:
            assert Path(path).read_bytes() == unarchive(record)
    return {"preparations": preparations, "children": children,
            "original38_failed": True, "original13_old_source_only": True,
            "old_settlers_executed": False}, green182

def parent_budgets():
    expected = (
        ("round158-p6-stage-b-local-temporal-publication-20261013", "command-ledger.json", 32871, "0290f0e66648bf4e3251b5fec8552044cf0468fa663290ba693cfd0bf33fe63a"),
        ("round158-p6-stage-b-local-temporal-publication-20261013", "root-command-ledger.json", 75684, "c161cb83a22ec9aefef972da94f15bec09f78defc253993aa02c14c550315974"),
        ("round175-p6-t1-transitive-memory-fixture-closure-20261014", "command-ledger.json", 3935, "f2ef9c5f7df921bcf0895ce542f0a645c657d7593b1e5210a997573128968bdb"),
        ("round175-p6-t1-transitive-memory-fixture-closure-20261014", "root-command-ledger.json", 9158, "6bd724cab73e5b653ee1e8fab8527a07b632600316ba9de389373d477a85109f"),
    )
    observations = []
    spent158 = {"mypy_baseline", "t1_red", "t1_green"}
    held158 = {"t2_red", "t2_green", "t3_red", "t3_green", "import_sort", "formatter",
               "scope_proof", "ruff", "format_check", "mypy_final", "mypy_delta", "final_new23"}
    for round_name, name, size, digest in expected:
        record = pin(B / round_name / name)
        assert (record["bytes"], record["sha256"]) == (size, digest)
        value = load(record["path"])
        slots = value["commands"]
        if round_name.startswith("round158-"):
            assert set(slots) == spent158 | held158
            assert all((slots[n]["used"], slots[n]["remaining"]) == (1, 0) for n in spent158)
            assert all((slots[n]["used"], slots[n]["remaining"]) == (0, 1) for n in held158)
        else:
            assert len(slots) == 3
            assert all((x["used"], x["remaining"], x["attempts"], x["retries"]) == (1, 0, 1, 0) for x in slots.values())
        observations.append(record)
    return {"ledgers": observations, "R158_spent": 3, "R158_HELD": 12, "R175_spent": 3, "resets": 0}


def new_child(name):
    directory = D / "implementation" / name
    result = load(directory / "result.json")
    invocation = load(directory / "invocation.json")
    command = command_for(PLAN, name)
    assert result["command"] == name and result["round"] == "R192"
    assert result["child_exit"] == result["wrapper_exit"] == 0
    assert result["accepted_command_outcome"] is True
    assert not result["timed_out"] and not result["failures"]
    assert result["attempt"] == 1 and result["retry"] == 0
    assert result["cleanup"] == {"leader_reaped": True, "group_remaining": False, "cleanup_notes": []}
    assert invocation["child_argv"] == command["argv"] and invocation["child_cwd"] == command["cwd"]
    assert invocation["child_environment"] == command["finite_env"]
    assert invocation["timeout_seconds"] == command["timeout_seconds"]
    assert invocation["shell"] is False and invocation["new_process_session"] is True
    assert invocation["launcher_argv"] == PLAN["runner_contract"]["author_runner_launches"][name]
    assert invocation["attempt"] == 1 and invocation["retry"] == 0
    check(invocation["script_pin"])
    assert json.loads(unarchive(invocation["author_ledger_before"]))["commands"][name]["used"] == 0
    check(result["invocation"])
    for record in result["input_records"]:
        check(record)
    for record in result["streams"].values():
        check(record)
    actual_tool(directory, 0, result)
    observed = {"result": pin(directory / "result.json"), "tool": pin(directory / "tool-return.json"),
                "actual_child_exit": 0, "actual_wrapper_exit": 0, "indexes": indexes(result, current_temp=True)}
    if name == "ruff":
        assert result["JUnit"] is None and result["resource_summary"] is None
    else:
        expected = PLAN["tests"]["green_nodes"]
        observed.update(junit(directory / "junit.xml", expected, 0))
        assert len(expected) == len(set(expected)) == 51
        assert result["JUnit"] == {"tests": 51, "passes": 51, "failures": 0, "errors": 0, "skips": 0}
        summary = load(directory / "resource-summary.json")
        assert summary == result["resource_summary"]
        assert PLAN["resources"]["helper_calls_by_node"] == dict.fromkeys(expected, 1)
        observed["resources"] = memory_records(summary, PLAN["resources"]["helper_calls_by_node"], result["process_pid"])
        assert observed["resources"]["helper_calls"] == 51
    return observed


def new_preparation(old_sources):
    directory = D / "implementation/prepare"
    result = load(directory / "result.json")
    assert result["command"] == "prepare" and result["exit_code"] == 0
    assert result["attempt"] == 1 and result["retry"] == 0
    assert result["product_commands"] == 0 and result["test_execution"] is False
    actual_tool(directory, 0, result)
    for record in result["outputs"]:
        check(record)
    snap = load(directory / "candidate-snapshot.json")
    assert snap["round"] == "R192" and len(snap["sources"]) == 25 and len(snap["protected"]) == 211
    sources = {x["path"]: x for x in snap["sources"]}
    assert set(sources) == set(old_sources)
    for path, record in sources.items():
        raw = unarchive(record)
        assert Path(path).read_bytes() == raw
        if path != SHARED:
            assert raw == unarchive(old_sources[path])
    for record in snap["protected"]:
        check(record)
    original_protected = load(P182 / "implementation/prepare_green/candidate-snapshot.json")["protected"]
    assert sorted(tuple(x[k] for k in PIN_KEYS) for x in snap["protected"]) == sorted(tuple(x[k] for k in PIN_KEYS) for x in original_protected)
    before = (D / "implementation/before-local-temporal.py").read_bytes()
    after = unarchive(sources[SHARED])
    insertion = GATE["approved_dispatch_insertion"].encode()
    anchor = GATE["approved_dispatch_anchor"].encode()
    assert before.count(anchor) == 1 and before.count(insertion) == 0
    assert after == before.replace(anchor, insertion + anchor, 1)
    assert insertion == b'    elif "schema_version" in retry_raw:\n        raise ValueError("unsupported publication retry budget schema/tag")\n'
    invocation = load(directory / "invocation.json")
    command = command_for(PLAN, "prepare")
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert invocation[key] == command[key]
    assert json.loads(unarchive(invocation["author_ledger_before"]))["commands"]["prepare"]["used"] == 0
    return {"result": pin(directory / "result.json"), "tool": pin(directory / "tool-return.json"),
            "snapshot": pin(directory / "candidate-snapshot.json"), "scope": pin(directory / "scope-proof.json"),
            "sources": {path:{key:record[key] for key in PIN_KEYS} for path,record in sources.items()},
            "sources_count": 25, "protected_count": 211, "only_dispatch_insertion": True}


def alarm_handler(signum, frame):
    raise TimeoutError("ROOT R192 120-second metadata cap")


def main():
    global PLAN, GATE
    started = time.monotonic()
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(120)
    assert Path.cwd() == ROOT and len(sys.argv) == 1
    assert sha((D / "plan.json").read_bytes()) == PLAN_SHA
    PLAN = load(D / "plan.json")
    GATE = load(D / "script-gate.json")["commands"]["root_settlement"]
    command = command_for(PLAN, "root_settlement")
    assert GATE["state"] == "APPROVED"
    assert GATE["argv"] == command["argv"] == [str(ROOT / ".venv/bin/python"), str(Path(__file__).absolute())]
    assert dict(os.environ) == command["finite_env"]
    check(GATE["script_pin"])
    for record in GATE["input_records"]:
        check(record)
    roles = load(D / "root-command-ledger.json")
    slot = roles["commands"]["root_settlement"]
    assert (slot["used"], slot["remaining"], slot["state"]) == (1, 0, "RESERVED_BY_ROOT")
    assert slot["reservation_id"] == GATE["reservation_id"]
    assert slot["gate_pin"] == pin(D / "script-gate.json")
    author_path = D / "command-ledger.json"
    author_raw = author_path.read_bytes()
    author = json.loads(author_raw)
    author_slot = author["commands"]["root_settlement"]
    assert (author_slot["used"], author_slot["remaining"], author_slot["state"]) == (0, 1, "HELD_PENDING_ROOT_GATE")
    author_slot.update(used=1, remaining=0, state="SPENT_BY_ROOT_BEFORE_ACTION", attempts=1,
                       reservation_id=GATE["reservation_id"])
    for name in ("prepare", "ruff", "green51"):
        assert (author["commands"][name]["used"], author["commands"][name]["remaining"], author["commands"][name]["attempts"]) == (1, 0, 1)
        assert (roles["commands"][name]["used"], roles["commands"][name]["remaining"]) == (1, 0)
        assert roles["commands"][name]["state"].startswith("SPENT_ACTUAL")
    directory = D / "implementation/root_settlement"
    directory.mkdir(exist_ok=False)
    invocation = write(directory / "invocation.json", {
        "argv": command["argv"], "cwd": str(ROOT), "finite_env": command["finite_env"],
        "timeout_seconds": 120, "hard_cap": "SIGALRM", "attempt": 1, "retry": 0,
        "script_pin": pin(Path(__file__).absolute()), "reservation_id": GATE["reservation_id"],
        "author_ledger_before": {"bytes": len(author_raw), "sha256": sha(author_raw),
                                "base64": base64.b64encode(author_raw).decode()},
        "outer_capture": GATE["transport"], "product_execution": False})
    assert author_path.read_bytes() == author_raw
    author_path.write_text(json.dumps(author, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    failures, observations = [], None
    try:
        transitions = parent_transitions()
        originals, old_sources = original_histories()
        preparation = new_preparation(old_sources)
        ruff = new_child("ruff")
        green51 = new_child("green51")
        budgets = parent_budgets()
        for record in GATE["input_records"]:
            check(record)
        observations = {"source_and_parent_roles": transitions, "original_evidence": originals,
                        "new_preparation": preparation, "new_ruff": ruff, "new_green51": green51,
                        "original_budgets": budgets, "same_reviewer_remaining_batches": 8,
                        "T1_decision_requires_same_independent_review": True}
    except BaseException as error:
        failures.append({"type": type(error).__name__, "message": str(error),
                         "traceback": "".join(traceback.format_exception(error))})
    settlement = write(directory / "settlement.json", {
        "round": "R192", "kind": "ROOT independent consolidated software evidence settlement",
        "status": "ACTUAL_EVIDENCE_ACCEPTED_REVIEW_PENDING" if not failures else "FAILED",
        "observations": observations, "failures": failures,
        "T1_complete": False, "T12_complete": False, "native_actual": False, "formal_research_accepted": False})
    result = {"round": "R192", "command": "root_settlement", "attempt": 1, "retry": 0,
              "status": "ROOT_ACCEPTED_R192_SOFTWARE_EVIDENCE_REVIEW_PENDING" if not failures else "ROOT_SETTLEMENT_FAILED",
              "exit_code": 0 if not failures else 1, "product_commands": 0,
              "elapsed_seconds": time.monotonic() - started,
              "timed_out": any(x["type"] == "TimeoutError" for x in failures),
              "cleanup": {"product_child_spawned": False, "leader_reaped": None, "group_remaining": None},
              "invocation": invocation, "settlement": settlement, "failures": failures,
              "input_records": GATE["input_records"], "T1_complete": False, "T12_complete": False,
              "native_actual": False, "formal_research_accepted": False}
    saved = write(directory / "result.json", result)
    signal.alarm(0)
    print(json.dumps({"command": "root_settlement", "exit_code": result["exit_code"], "result": saved}))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
