"""ROOT R179 single metadata settlement; never imports product code."""
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
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014"
PLAN_SHA = "dc0cae1b743d6244469625e3f9a4fd14200efbb3e3669c422f1639f59b4be05e"
PIN_KEYS = ("path", "bytes", "sha256")
MUTABLE = {str(D / n) for n in ("script-gate.json", "command-ledger.json",
                                 "root-command-ledger.json", "root-activation.json")}


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


def metadata_snapshot(phase, current):
    directory = D / "implementation" / ("prepare_" + phase)
    result = load(directory / "result.json")
    tool = load(directory / "tool-return.json")
    assert result["command"] == "prepare_" + phase and result["exit_code"] == 0
    assert result["attempt"] == 1 and result["retry"] == 0
    assert result["test_execution"] is False and result["product_commands"] == 0
    assert tool["actual_summary"] == result
    check(tool["result_pin"])
    actual = tool["completion"] if tool["completion"] is not None else tool["initial"]
    assert actual["exit_code"] == 0
    assert tool["attempt"] == 1 and tool["retry"] == 0
    for record in tool["outer_streams"].values():
        check(record)
    for record in result["outputs"]:
        check(record)
    assert len(result["outputs"]) == 6
    snap = load(directory / "candidate-snapshot.json")
    assert snap["phase"] == phase and snap["round"] == "R179"
    check(snap["baseline"])
    assert len(snap["sources"]) == 24 and len(snap["protected"]) == 211
    sources = {}
    for record in snap["sources"]:
        raw = unarchive(record)
        if current:
            assert Path(record["path"]).read_bytes() == raw
        sources[record["path"]] = {k: record[k] for k in PIN_KEYS}
    for record in snap["protected"]:
        check(record)
    proof = load(directory / "source-scope-proof.json")
    assert proof["owned_count"] == 24 and proof["protected_count"] == 211
    assert proof["A80556_preserved"] is True
    assert proof["other_owned_unchanged"] == 21
    assert proof["runtime_authority_claim"] is False
    assert proof["tests_collected_or_run"] is False
    invocation = load(directory / "invocation.json")
    command = next(c for c in PLAN["commands"] if c["id"] == "prepare_" + phase)
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert invocation[key] == command[key]
    assert invocation["attempt"] == 1 and invocation["retry"] == 0
    old_author = load_archived_role(invocation["author_ledger_before"])
    assert old_author["commands"]["prepare_" + phase]["used"] == 0
    return {"phase": phase, "result": pin(directory / "result.json"),
            "tool": pin(directory / "tool-return.json"), "sources": sources,
            "proof": pin(directory / "source-scope-proof.json")}


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


def child_evidence(name, history=None):
    directory = D / "implementation" / name
    result = load(directory / "result.json")
    tool = load(directory / "tool-return.json")
    inv = load(directory / "invocation.json")
    command = next(c for c in PLAN["commands"] if c["id"] == name)
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
    assert inv["launcher_argv"] == [str(ROOT / ".venv/bin/python"), str(D / "implementation/run-command.py"), name]
    check(inv["script_pin"])
    assert load_archived_role(inv["author_ledger_before"])["commands"][name]["used"] == 0
    check(result["invocation"])
    for record in result["streams"].values():
        check(record)
    for record in result["input_records"]:
        check(record, history)
    check(tool["result_pin"])
    for record in tool["outer_streams"].values():
        check(record)
    actual = tool["completion"] if tool["completion"] is not None else tool["initial"]
    assert actual["exit_code"] == expected_exit
    assert tool["attempt"] == 1 and tool["retry"] == 0
    assert tool["actual_summary"]["child_exit"] == expected_exit
    assert tool["actual_summary"]["wrapper_exit"] == expected_exit
    result_record = {"command": name, "actual_child_exit": expected_exit,
                     "actual_wrapper_exit": expected_exit,
                     "result": pin(directory / "result.json"),
                     "tool": pin(directory / "tool-return.json")}
    if name == "ruff":
        assert result["JUnit"] is None and result["resource_summary"] is None
        return result_record
    cases = ET.parse(directory / "junit.xml").getroot().findall(".//testcase")
    expected = PLAN["tests"][name + "_nodes"]
    assert Counter(c.attrib["name"] for c in cases) == Counter(n.split("::", 1)[1] for n in expected)
    assert all(c.find("error") is None and c.find("skipped") is None for c in cases)
    failures = [c for c in cases if c.find("failure") is not None]
    if name == "red":
        assert len(cases) == len(failures) == 19
        assert all("DID NOT RAISE" in c.find("failure").text for c in failures)
    else:
        assert len(cases) == 38 and not failures
    mapping = GATES["commands"][name]["resource_map"]["helper_calls_by_node"]
    summary = load(directory / "resource-summary.json")
    assert summary == result["resource_summary"]
    result_record.update(JUnit=pin(directory / "junit.xml"),
                         tests=len(cases), failures=len(failures),
                         resources=memory_records(summary, mapping, result["process_pid"]))
    return result_record


def alarm_handler(signum, frame):
    raise TimeoutError("ROOT R179 120-second metadata cap")


def main():
    global PLAN, GATES
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(120)
    assert Path.cwd() == ROOT and len(sys.argv) == 1
    assert sha((D / "plan.json").read_bytes()) == PLAN_SHA
    PLAN = load(D / "plan.json")
    GATES = load(D / "script-gate.json")
    command = next(c for c in PLAN["commands"] if c["id"] == "root_settlement")
    gate = GATES["commands"]["root_settlement"]
    assert gate["state"] == "APPROVED"
    assert gate["argv"] == command["argv"] == [sys.executable, str(Path(__file__).absolute())]
    assert dict(os.environ) == command["finite_env"]
    check(gate["script_pin"])
    assert all(r["path"] not in MUTABLE for r in gate["input_records"])
    for record in gate["input_records"]:
        check(record)
    roles = load(D / "root-command-ledger.json")
    slot = roles["commands"]["root_settlement"]
    assert (slot["used"], slot["remaining"], slot["state"]) == (1, 0, "RESERVED_BY_ROOT")
    assert slot["reservation_id"] == gate["reservation_id"]
    author_path = D / "command-ledger.json"
    author_before = author_path.read_bytes()
    author = json.loads(author_before)
    author_slot = author["commands"]["root_settlement"]
    assert (author_slot["used"], author_slot["remaining"], author_slot["state"]) == (0, 1, "HELD")
    author_slot.update(used=1, remaining=0, state="SPENT_BY_ROOT_BEFORE_ACTION",
                       reservation_id=gate["reservation_id"], attempts=1, retries=0)
    author_path.write_text(json.dumps(author, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    directory = D / "implementation/root_settlement"
    directory.mkdir(exist_ok=False)
    write(directory / "invocation.json", {
        "argv": command["argv"], "cwd": str(ROOT), "finite_env": command["finite_env"],
        "timeout_seconds": 120, "hard_cap": "SIGALRM", "attempt": 1, "retry": 0,
        "script_pin": pin(Path(__file__).absolute()), "reservation_id": gate["reservation_id"],
        "author_ledger_before": {"bytes": len(author_before), "sha256": sha(author_before),
                                "base64": base64.b64encode(author_before).decode()},
        "outer_capture": gate["transport"], "product_execution": False})
    failures = []
    observations = None
    try:
        red = metadata_snapshot("red", False)
        green = metadata_snapshot("green", True)
        original = load(D / "implementation/before/baseline-r175-snapshot.json")
        old = {r["path"]: unarchive(r) for r in original["sources"]}
        current = load(D / "implementation/prepare_green/candidate-snapshot.json")
        changed = []
        for record in current["sources"]:
            if unarchive(record) != old[record["path"]]:
                changed.append(record["path"])
        assert set(changed) <= set(PLAN["scope"]["owned_paths"])
        assert len(current["protected"]) == 211
        for record in current["protected"]:
            check(record)
        red_source = load(D / "implementation/prepare_red/candidate-snapshot.json")
        old_test = next(unarchive(r) for r in red_source["sources"] if "/tests/" in r["path"])
        new_test = next(unarchive(r) for r in current["sources"] if "/tests/" in r["path"])
        marker = b"# R179"
        # The literal marker is supplied by the reviewed final gate, never guessed.
        marker = gate["frozen_test_marker"].encode()
        assert old_test.count(marker) == 1 and new_test.count(marker) == 1
        assert old_test.split(marker, 1)[1] == new_test.split(marker, 1)[1]
        assert sha(new_test[:80556]) == "c1a68fe0b5ff88bdf604e4859a17da73f61f56b1fd934897f0e66a484d9ae861"
        red_actual = child_evidence("red", red["sources"])
        ruff_actual = child_evidence("ruff")
        green_actual = child_evidence("green")
        assert load(D / "implementation/root-red19-acceptance-and-implementation-release.json")["status"] == "EXPECTED_RED19_ACTUAL_EXIT1_ACCEPTED_IMPLEMENTATION_ONLY_RELEASED"
        for name in ("prepare_red", "red", "prepare_green", "ruff", "green"):
            a = author["commands"][name]
            r = roles["commands"][name]
            assert (a["used"], a["remaining"], a["attempts"], a["retries"]) == (1, 0, 1, 0)
            assert (r["used"], r["remaining"]) == (1, 0)
        for record in gate["input_records"]:
            check(record)
        observations = {"red_preparation": red, "green_preparation": green,
                        "changed_paths": changed, "protected": 211,
                        "frozen_new_tests_unchanged": True, "A80556_unchanged": True,
                        "red": red_actual, "ruff": ruff_actual, "green": green_actual,
                        "parent_budget_reset": False, "legacy_goldens_changed": False}
    except BaseException as error:
        failures.append({"type": type(error).__name__, "message": str(error),
                         "traceback": "".join(traceback.format_exception(error))})
    result = {"round": "R179", "command": "root_settlement", "attempt": 1, "retry": 0,
              "status": "ROOT_ACCEPTED_R179_ACTUAL_SOFTWARE_EVIDENCE_REVIEW_PENDING" if not failures else "ROOT_SETTLEMENT_FAILED",
              "exit_code": 0 if not failures else 1, "product_commands": 0,
              "observations": observations, "failures": failures,
              "input_records": gate["input_records"], "T1_complete": False,
              "B9_complete": False, "T12_complete": False,
              "native_actual": False, "formal_research_accepted": False}
    saved = write(directory / "result.json", result)
    signal.alarm(0)
    print(json.dumps({"command": "root_settlement", "exit_code": result["exit_code"], "result": saved}))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
