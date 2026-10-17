"""ROOT R182 single standard-library settlement; no product imports or execution."""
from collections import Counter
from pathlib import Path
import base64
import hashlib
import json
import os
import signal
import sys
import traceback
import xml.etree.ElementTree as ET

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014")
PARENT = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014")
PLAN_SHA = "82100de3713beccb61ceeb0da87d40d3cbb6a4552890c6c72337d899fad96c5d"
PIN_KEYS = ("path", "bytes", "sha256")
SHARED = str(ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py")
AUXILIARY = str(ROOT / "tests/test_local_temporal_projection_closure.py")
FROZEN = {
    str(ROOT / "tests/test_operational_runtime_closure.py"):
        (168003, "66b6c373123299b52f17a6946dd7a77a0d2962b31ce6391261a93f8b01f0612f"),
    str(ROOT / "src/cloud_edge_robot_arm/repositories/event_autonomy/visual_verification.py"):
        (49612, "fe5f8e89e8be95e3251bac4119cfe9daa1751aef2cbc60bffef145d81c7399d8"),
}
# Frozen pins are finalized by ROOT from the actual full source gate before release.
PARENT_SCRIPTS = {
    "prepare-evidence.py": (12691, "8ea8a72f39cce758ab43cf9a6d6e33327191395e420b156d34ce96a08d3aa97f"),
    "run-command.py": (14179, "049d873e6328f89641d20d9577de448818d6ff9ff9161054abebaeb27f4bc84e"),
    "root-settlement.py": (16271, "542f408da66cc5dabf061a994d3877d73dd90c227f2e4d0c48e07eaf3dbfca94"),
}
MUTABLE = {str(round_path / name) for round_path in (D, PARENT)
           for name in ("script-gate.json", "command-ledger.json",
                        "root-command-ledger.json", "root-activation.json")}
MUTABLE.update(str(ROOT / "artifacts/research/process/20261004-ced-development" /
                   "t12-sol-handoff-20261007" / name)
               for name in ("active-t12-state.json", "phase-summary.md"))

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
    if history is not None and record["path"] in history:
        assert history[record["path"]] == expected
    else:
        assert pin(record["path"]) == expected


def unarchive(record):
    raw = base64.b64decode(record["base64"], validate=True)
    assert len(raw) == record["bytes"] and sha(raw) == record["sha256"]
    return raw


def write(path, value):
    with Path(path).open("xb") as f:
        f.write((json.dumps(value, ensure_ascii=False, sort_keys=True,
                            indent=2, allow_nan=False) + "\n").encode())
    return pin(path)


def load_archived_role(record):
    return json.loads(unarchive(record))


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



def command_for(plan, name):
    return next(command for command in plan["commands"] if command["id"] == name)


def actual_tool(directory, expected_exit, result):
    tool = load(directory / "tool-return.json")
    check(tool["result_pin"])
    assert tool["result_pin"] == pin(directory / "result.json")
    assert tool["attempt"] == 1 and tool["retry"] == 0
    actual = tool["completion"] if tool["completion"] is not None else tool["initial"]
    assert actual["exit_code"] == expected_exit and actual.get("session_id") is None
    for record in tool["outer_streams"].values():
        check(record)
    return tool


def metadata_snapshot(phase, current):
    directory = D / "implementation" / ("prepare_" + phase)
    result = load(directory / "result.json")
    assert result["command"] == "prepare_" + phase and result["exit_code"] == 0
    assert result["attempt"] == 1 and result["retry"] == 0
    assert result["test_execution"] is False and result["product_commands"] == 0
    tool = actual_tool(directory, 0, result)
    assert tool["actual_summary"] == result
    assert len(result["outputs"]) == 6
    for record in result["outputs"]:
        check(record)
    snap = load(directory / "candidate-snapshot.json")
    assert snap["phase"] == phase and snap["round"] == "R182"
    check(snap["baseline"])
    assert snap["baseline"] == pin(D / "original-static-finding.json")
    assert len(snap["sources"]) == 25 and len(snap["protected"]) == 211
    original_protected = load(D / "original-static-finding.json")["protected211"]
    assert sorted(tuple(record[key] for key in PIN_KEYS) for record in snap["protected"]) == sorted(
        tuple(record[key] for key in PIN_KEYS) for record in original_protected)
    sources = {}
    for record in snap["sources"]:
        raw = unarchive(record)
        assert record["path"] not in sources
        if current:
            assert Path(record["path"]).read_bytes() == raw
        sources[record["path"]] = record
    assert AUXILIARY in sources and SHARED in sources
    for record in snap["protected"]:
        check(record)
    proof = load(directory / "source-scope-proof.json")
    for field, expected in GATE["preparation_proof_contract"][phase].items():
        assert proof[field] == expected
    inv = load(directory / "invocation.json")
    command = command_for(PLAN, "prepare_" + phase)
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert inv[key] == command[key]
    assert inv["attempt"] == 1 and inv["retry"] == 0
    assert load_archived_role(inv["author_ledger_before"])["commands"]["prepare_" + phase]["used"] == 0
    return {"sources": sources, "result": pin(directory / "result.json"),
            "tool": pin(directory / "tool-return.json"),
            "proof": pin(directory / "source-scope-proof.json")}


def child_evidence(name, history=None):
    directory = D / "implementation" / name
    result = load(directory / "result.json")
    inv = load(directory / "invocation.json")
    command = command_for(PLAN, name)
    expected_exit = 1 if name == "red" else 0
    assert result["child_exit"] == result["wrapper_exit"] == expected_exit
    assert result["accepted_command_outcome"] is True and not result["timed_out"]
    assert result["attempt"] == 1 and result["retry"] == 0 and not result["failures"]
    assert result["cleanup"] == {"leader_reaped": True, "group_remaining": False, "cleanup_notes": []}
    assert inv["child_argv"] == command["argv"] and inv["child_cwd"] == command["cwd"]
    assert inv["child_environment"] == command["finite_env"]
    assert inv["timeout_seconds"] == command["timeout_seconds"]
    assert inv["shell"] is False and inv["new_process_session"] is True
    assert inv["attempt"] == 1 and inv["retry"] == 0
    assert inv["launcher_argv"] == [str(ROOT / ".venv/bin/python"),
                                   str(D / "implementation/run-command.py"), name]
    check(inv["script_pin"])
    assert load_archived_role(inv["author_ledger_before"])["commands"][name]["used"] == 0
    check(result["invocation"])
    for record in result["streams"].values():
        check(record)
    for record in result["input_records"]:
        check(record, history)
    tool = actual_tool(directory, expected_exit, result)
    assert tool["actual_summary"]["child_exit"] == expected_exit
    assert tool["actual_summary"]["wrapper_exit"] == expected_exit
    observation = {"command": name, "actual_child_exit": expected_exit,
                   "actual_wrapper_exit": expected_exit,
                   "result": pin(directory / "result.json"),
                   "tool": pin(directory / "tool-return.json")}
    if name == "ruff":
        assert result["JUnit"] is None and result["resource_summary"] is None
        return observation
    cases = ET.parse(directory / "junit.xml").getroot().findall(".//testcase")
    expected = PLAN["tests"][name + "_nodes"]
    assert Counter(c.attrib["name"] for c in cases) == Counter(n.split("::", 1)[1] for n in expected)
    assert all(c.find("error") is None and c.find("skipped") is None for c in cases)
    failures = [c for c in cases if c.find("failure") is not None]
    if name == "red":
        assert len(cases) == len(failures) == 8
        assert all("DID NOT RAISE" in c.find("failure").text for c in failures)
    else:
        assert len(cases) == 13 and not failures
    mapping = GATES["commands"][name]["resource_map"]["helper_calls_by_node"]
    assert mapping == dict.fromkeys(expected, 1)
    summary = load(directory / "resource-summary.json")
    assert summary == result["resource_summary"]
    observation.update(JUnit=pin(directory / "junit.xml"),
                       tests=len(cases), failures=len(failures),
                       resources=memory_records(summary, mapping, result["process_pid"]))
    return observation


def parent_settlement():
    directory = PARENT / "implementation/root_settlement"
    result = load(directory / "result.json")
    assert result["round"] == "R179" and result["command"] == "root_settlement"
    assert result["status"] == "ROOT_ACCEPTED_R179_ACTUAL_SOFTWARE_EVIDENCE_REVIEW_PENDING"
    assert result["exit_code"] == 0 and result["attempt"] == 1 and result["retry"] == 0
    assert result["product_commands"] == 0 and not result["failures"]
    assert result["T1_complete"] is False and result["T12_complete"] is False
    actual_tool(directory, 0, result)
    observations = result["observations"]
    assert observations["red"]["tests"] == 19 and observations["red"]["failures"] == 19
    assert observations["green"]["tests"] == 38 and observations["green"]["failures"] == 0
    assert observations["ruff"]["actual_child_exit"] == 0
    for key in ("red_preparation", "green_preparation"):
        for field in ("result", "tool", "proof"):
            check(observations[key][field])
    for key in ("red", "ruff", "green"):
        record = observations[key]
        check(record["result"])
        check(record["tool"])
        if key != "ruff":
            check(record["JUnit"])
            child = load(record["result"]["path"])
            summary = load(PARENT / "implementation" / key / "resource-summary.json")
            expected = load(PARENT / "script-gate.json")["commands"][key]["resource_map"]["helper_calls_by_node"]
            verified = memory_records(summary, expected, child["process_pid"])
            assert verified == record["resources"]
    parent_sources = observations["green_preparation"]["sources"]
    assert len(parent_sources) == 24
    for record in parent_sources.values():
        check(record)
    return {"result": pin(directory / "result.json"),
            "tool": pin(directory / "tool-return.json"),
            "green_sources": parent_sources, "RED19": 19, "GREEN38": 38}


def alarm_handler(signum, frame):
    raise TimeoutError("ROOT R182 120-second metadata cap")


def main():
    global PLAN, GATES, GATE
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(120)
    assert Path.cwd() == ROOT and len(sys.argv) == 1
    assert sha((D / "plan.json").read_bytes()) == PLAN_SHA
    PLAN = load(D / "plan.json")
    GATES = load(D / "script-gate.json")
    GATE = GATES["commands"]["root_settlement"]
    command = command_for(PLAN, "root_settlement")
    assert GATE["state"] == "APPROVED"
    assert GATE["argv"] == command["argv"] == [sys.executable, str(Path(__file__).absolute())]
    assert dict(os.environ) == command["finite_env"]
    check(GATE["script_pin"])
    assert all(record["path"] not in MUTABLE for record in GATE["input_records"])
    for record in GATE["input_records"]:
        check(record)
    roles = load(D / "root-command-ledger.json")
    slot = roles["commands"]["root_settlement"]
    assert (slot["used"], slot["remaining"], slot["state"]) == (1, 0, "RESERVED_BY_ROOT")
    assert slot["reservation_id"] == GATE["reservation_id"]
    author_path = D / "command-ledger.json"
    author_before = author_path.read_bytes()
    author = json.loads(author_before)
    author_slot = author["commands"]["root_settlement"]
    assert (author_slot["used"], author_slot["remaining"], author_slot["state"]) == (0, 1, "HELD")
    author_slot.update(used=1, remaining=0, state="SPENT_BY_ROOT_BEFORE_ACTION",
                       reservation_id=GATE["reservation_id"], attempts=1, retries=0)
    author_path.write_text(json.dumps(author, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    directory = D / "implementation/root_settlement"
    directory.mkdir(exist_ok=False)
    write(directory / "invocation.json", {
        "argv": command["argv"], "cwd": str(ROOT), "finite_env": command["finite_env"],
        "timeout_seconds": 120, "hard_cap": "SIGALRM", "attempt": 1, "retry": 0,
        "script_pin": pin(Path(__file__).absolute()), "reservation_id": GATE["reservation_id"],
        "author_ledger_before": {"bytes": len(author_before), "sha256": sha(author_before),
                                "base64": base64.b64encode(author_before).decode()},
        "outer_capture": GATE["transport"], "product_execution": False})
    failures = []
    observations = None
    try:
        red = metadata_snapshot("red", False)
        green = metadata_snapshot("green", True)
        assert set(red["sources"]) == set(green["sources"])
        assert {path for path in red["sources"]
                if unarchive(red["sources"][path]) != unarchive(green["sources"][path])} <= {SHARED}
        assert (red["sources"][SHARED]["bytes"], red["sources"][SHARED]["sha256"]) == (
            104539, "8090c6d7a7e3911ecbd9cc13678f950980dc35834174dc762ca3d507e6aa866b")
        assert GATE["frozen_source_pins"] == {path: list(values) for path, values in FROZEN.items()}
        for path, (length, digest) in FROZEN.items():
            assert (green["sources"][path]["bytes"], green["sources"][path]["sha256"]) == (length, digest)
        assert unarchive(red["sources"][AUXILIARY]) == unarchive(green["sources"][AUXILIARY])
        for name, (length, digest) in PARENT_SCRIPTS.items():
            record = pin(PARENT / "implementation" / name)
            assert (record["bytes"], record["sha256"]) == (length, digest)
        original = load(D / "original-static-finding.json")
        before = {record["path"]: record for record in original["before_R179_draft_sources"]}
        assert set(before) == set(red["sources"]) - {AUXILIARY}
        for path, record in before.items():
            assert unarchive(record) == unarchive(red["sources"][path])
        red_history = {path: {key: record[key] for key in PIN_KEYS}
                       for path, record in red["sources"].items()}
        red_actual = child_evidence("red", red_history)
        ruff_actual = child_evidence("ruff")
        green_actual = child_evidence("green")
        parent = parent_settlement()
        assert set(parent["green_sources"]) == set(green["sources"]) - {AUXILIARY}
        for path, record in parent["green_sources"].items():
            assert record == {key: green["sources"][path][key] for key in PIN_KEYS}
        parent_nodes = command_for(load(PARENT / "plan.json"), "green")["argv"][6:-2]
        own_nodes = PLAN["tests"]["green_nodes"]
        assert len(own_nodes) == 13 and len(parent_nodes) == 38
        assert not set(own_nodes).intersection(parent_nodes)
        assert len(set(own_nodes).union(parent_nodes)) == 51
        for name in ("prepare_red", "red", "prepare_green", "ruff", "green"):
            a, r = author["commands"][name], roles["commands"][name]
            assert (a["used"], a["remaining"], a["attempts"], a["retries"]) == (1, 0, 1, 0)
            assert (r["used"], r["remaining"]) == (1, 0)
        for record in GATE["input_records"]:
            check(record)
        observations = {"red_preparation": red, "green_preparation": green,
                        "red": red_actual, "ruff": ruff_actual, "green": green_actual,
                        "parent": parent, "protected": 211, "sources": 25,
                        "original_test_and_verifier_unchanged": True,
                        "auxiliary_frozen_since_RED": True, "parent_scripts_unchanged": True,
                        "two_actual_GREEN_runs": [13, 38], "unique_GREEN_nodes": 51,
                        "reporting_erratum": "R184", "old_failure_evidence_preserved": True,
                        "budgets_reset": False, "fresh_reviewer_remaining_batches": 8}
    except BaseException as error:
        failures.append({"type": type(error).__name__, "message": str(error),
                         "traceback": "".join(traceback.format_exception(error))})
    result = {"round": "R182", "command": "root_settlement", "attempt": 1, "retry": 0,
              "status": "ROOT_ACCEPTED_R182_ACTUAL_SOFTWARE_EVIDENCE_REVIEW_PENDING" if not failures
                        else "ROOT_SETTLEMENT_FAILED",
              "exit_code": 0 if not failures else 1, "product_commands": 0,
              "observations": observations, "failures": failures,
              "input_records": GATE["input_records"], "T1_complete": False,
              "B9_complete": False, "T12_complete": False,
              "native_actual": False, "formal_research_accepted": False}
    saved = write(directory / "result.json", result)
    signal.alarm(0)
    print(json.dumps({"command": "root_settlement", "exit_code": result["exit_code"], "result": saved}))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
