"""ROOT R196 independent one-shot stdlib settlement. No product imports or execution."""
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
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014"
P192 = D.parent / "round192-p6-t1-original-green38-unexpected-outcome-20261014"
SHARED = str(ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py")
PLAN_SHA = "c06e7433d113754a00438440e6c7777c2d4ba28236d228e886cc4dc1418a4338"
INITIAL_MANIFEST_SHA = "0295c8825c68314d40d88d16c82310fd365d99abb97696e6f9d9dd23c7ac3cd3"
PIN_KEYS = ("path", "bytes", "sha256")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    path = Path(path)
    assert path.is_absolute() and not path.is_symlink()
    assert all(not parent.is_symlink() for parent in path.parents)
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": sha(raw)}


def load(path):
    return json.loads(Path(path).read_bytes())


def normalized(record):
    return {key: record[key] for key in PIN_KEYS}


def check(record):
    assert pin(record["path"]) == normalized(record), normalized(record)


def unarchive(record):
    raw = base64.b64decode(record["base64"], validate=True)
    assert (len(raw), sha(raw)) == (record["bytes"], record["sha256"])
    return raw


def write(path, value):
    with Path(path).open("xb") as stream:
        stream.write((json.dumps(value, ensure_ascii=False, sort_keys=True,
                                 allow_nan=False, indent=2) + "\n").encode())
    return pin(path)


def command_for(name):
    return next(value for value in PLAN["commands"] if value["id"] == name)


def input_check(record, historical_shared=False):
    # The sole controlled source exception is the exact initial shared file,
    # verified against its physical R196 archive. Other paths use current bytes.
    if historical_shared and record["path"] == SHARED:
        archive = INITIAL_ARCHIVES[SHARED]
        assert normalized(record) == archive["original"]
        check(archive["archive"])
        assert Path(archive["archive"]["path"]).read_bytes() == INITIAL_SHARED
    else:
        check(record)


def actual_tool(directory, expected_exit, result, child=False):
    tool = load(directory / "tool-return.json")
    check(tool["result_pin"])
    assert normalized(tool["result_pin"]) == pin(directory / "result.json")
    assert tool["attempt"] == 1 and tool["retry"] == 0
    actual = tool["completion"] if tool["completion"] is not None else tool["initial"]
    assert actual["exit_code"] == expected_exit and actual.get("session_id") is None
    for record in tool["outer_streams"].values():
        check(record)
    summary = tool["actual_summary"]
    if child:
        required = {"JUnit", "accepted_command_outcome", "child_exit",
                    "cleanup", "timed_out", "wrapper_exit"}
        optional = {"command", "failures", "process_pid"}
        assert summary == result or (
            required <= set(summary) <= required | optional
            and all(value == result[key] for key, value in summary.items()))
    else:
        assert summary == result
    return pin(directory / "tool-return.json")


def historical_metadata(record):
    raw = unarchive(record)
    key = tuple(record[name] for name in PIN_KEYS)
    assert key in HISTORY, normalized(record)
    archive = HISTORY[key]
    check(archive)
    assert Path(archive["path"]).read_bytes() == raw
    return json.loads(raw)


def invocation_before(invocation, name):
    command = command_for(name)
    gate = historical_metadata(invocation["gate_before"])["commands"][name]
    root = historical_metadata(invocation["root_ledger_before"])
    author = historical_metadata(invocation["author_ledger_before"])
    historical_metadata(invocation["activation_before"])
    assert gate["state"] == "APPROVED"
    assert gate["reservation_id"] == invocation["reservation_id"]
    for key in ("argv", "cwd", "finite_env", "timeout_seconds", "child_finite_env"):
        assert gate[key] == command[key]
    assert (root["commands"][name]["used"], root["commands"][name]["remaining"],
            root["commands"][name]["state"]) == (1, 0, "RESERVED_BY_ROOT")
    assert root["commands"][name]["gate_pin"] == normalized(invocation["gate_before"])
    assert (author["commands"][name]["used"], author["commands"][name]["remaining"],
            author["commands"][name]["state"]) == (0, 1, "HELD_PENDING_ROOT_GATE")
    return gate


def junit(path, expected, red=False, old_failed=False):
    cases = ET.parse(path).getroot().findall(".//testcase")
    observed = Counter(case.attrib["classname"].replace(".", "/") + ".py::" +
                       case.attrib["name"] for case in cases)
    assert observed == Counter(expected)
    assert all(case.find("error") is None and case.find("skipped") is None for case in cases)
    failures = {case.attrib["name"]: case.find("failure") for case in cases
                if case.find("failure") is not None}
    if red:
        local = "test_r196_full_promotion_history[local]"
        legacy = "test_r196_full_promotion_history[legacy]"
        assert len(cases) == 8 and len(failures) == 7
        assert set(failures) == {node.split("::", 1)[1] for node in expected} - {legacy}
        for name, failure in failures.items():
            message = (failure.text or "") + "\n" + (failure.get("message") or "")
            if name == local:
                assert "ValueError: local history has no UTC authority deadline" in message
                assert "_bootstrap_promotion_source" in message
            else:
                assert "DID NOT RAISE <class 'ValueError'>" in message
    elif old_failed:
        assert set(failures) == {"test_r179_publication_history_getters[local]"}
    else:
        assert not failures
    return {"tests": len(cases), "passes": len(cases) - len(failures),
            "failures": len(failures), "errors": 0, "skips": 0}


def indexes(result):
    for item in result["file_index"]:
        if item.get("sha256") is not None:
            check(item)
    for item in result["temp_index"]:
        path = Path(item["path"])
        metadata = path.lstat()
        assert (metadata.st_mode, metadata.st_size) == (item["mode"], item["bytes"])
        assert path.is_symlink() == item["symlink"]
        if item["symlink"]:
            assert os.readlink(path) == item["link_target"]
        elif item.get("sha256") is not None:
            assert stat.S_ISREG(metadata.st_mode)
            check(item)
    return {"raw_entries": len(result["file_index"]),
            "temp_entries": len(result["temp_index"]), "database_query_count": 0}


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



def initial_controls():
    global INITIAL_ARCHIVES, INITIAL_SHARED, HISTORY
    path = D / "implementation/before/manifest.json"
    assert pin(path)["sha256"] == INITIAL_MANIFEST_SHA
    manifest = load(path)
    assert manifest["initial_inputs"] == PLAN["inputs"]
    INITIAL_ARCHIVES = {value["original"]["path"]: value for value in manifest["archives"]}
    assert len(INITIAL_ARCHIVES) == 7
    for value in INITIAL_ARCHIVES.values():
        check(value["archive"])
        assert (value["original"]["bytes"], value["original"]["sha256"]) == (
            value["archive"]["bytes"], value["archive"]["sha256"])
    INITIAL_SHARED = Path(INITIAL_ARCHIVES[SHARED]["archive"]["path"]).read_bytes()
    assert len(INITIAL_SHARED) == 111212
    assert sha(INITIAL_SHARED) == "f01520073140a08b0e15b947a00c840f486d45bd7dcc434bf44a894b6aae591c"
    mutable = set(PLAN["input_roles"]["mutable_start_paths"])
    for value in PLAN["inputs"]:
        if value["path"] in mutable or value["path"] == SHARED:
            assert value == INITIAL_ARCHIVES[value["path"]]["original"]
        else:
            check(value)
    state_path, phase_path = PLAN["input_roles"]["mutable_start_paths"]
    original_state = load(INITIAL_ARCHIVES[state_path]["archive"]["path"])
    current_state = load(state_path)
    assert "R196" not in original_state["planning"]
    current_state["planning"].pop("R196")
    assert current_state == original_state
    assert Path(phase_path).read_bytes().startswith(
        Path(INITIAL_ARCHIVES[phase_path]["archive"]["path"]).read_bytes())
    protected = set(PLAN["input_roles"]["protected_paths"])
    assert len(protected) == 211
    HISTORY = {}
    mutable_roles = {str(D / name) for name in (
        "script-gate.json", "root-command-ledger.json", "command-ledger.json", "root-activation.json")}
    for value in GATE["historical_metadata"]:
        assert value["original"]["path"] in mutable_roles
        check(value["archive"])
        assert (value["original"]["bytes"], value["original"]["sha256"]) == (
            value["archive"]["bytes"], value["archive"]["sha256"])
        HISTORY[tuple(value["original"][key] for key in PIN_KEYS)] = value["archive"]
    return {"initial_inputs": len(PLAN["inputs"]), "protected": 211,
            "before_archives": len(INITIAL_ARCHIVES), "historical_metadata": len(HISTORY)}


def bounded_source(before, after):
    def ranges(raw):
        result = []
        for name in (b"_join_audit_original", b"_bootstrap_promotion_source"):
            marker = b"\ndef " + name + b"("
            assert raw.count(marker) == 1
            start = raw.index(marker) + 1
            header_end = raw.index(b") -> None:\n", start) + len(b") -> None:\n")
            end = raw.index(b"\ndef ", header_end) + 1
            result.append((start, header_end, end))
        begin = b'    if tag == "visual.verification.route.local.v1":\n'
        end_marker = b'    if tag == "visual.verification.effect-completion.local.v1":\n'
        assert raw.count(begin) == raw.count(end_marker) == 1
        start = raw.index(begin)
        result.append((start, start + len(begin), raw.index(end_marker)))
        return sorted(result)
    left, right = ranges(before), ranges(after)
    masked, regions = [], []
    for raw, bounds in ((before, left), (after, right)):
        cursor, parts = 0, []
        for start, header_end, end in bounds:
            parts.append(raw[cursor:header_end])
            parts.append(b"<R196_ALLOWED_BODY>")
            cursor = end
        parts.append(raw[cursor:])
        masked.append(b"".join(parts))
    assert before != after and masked[0] == masked[1]
    for a, b in zip(left, right):
        assert before[a[0]:a[1]] == after[b[0]:b[1]]
        regions.append({"before_sha256": sha(before[a[1]:a[2]]),
                        "after_sha256": sha(after[b[1]:b[2]])})
    return {"three_regions": regions, "outside_bytes_identical": True,
            "signature_bytes_identical": True, "before_sha256": sha(before), "after_sha256": sha(after)}


def preparation(phase):
    directory = D / "implementation" / ("prepare_" + phase)
    value = load(directory / "result.json")
    assert value["command"] == "prepare_" + phase and value["round"] == "R196"
    assert value["exit_code"] == 0 and value["attempt"] == 1 and value["retry"] == 0
    assert value["test_execution"] is False and value["product_commands"] == 0
    tool = actual_tool(directory, 0, value)
    for record in value["outputs"]:
        check(record)
    for record in value["input_records"]:
        input_check(record, phase == "red")
    invocation = load(directory / "invocation.json")
    command = command_for("prepare_" + phase)
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert invocation[key] == command[key]
    invocation_before(invocation, "prepare_" + phase)
    for record in invocation["script_pins"]:
        check(record)
    snapshot = load(directory / "candidate-snapshot.json")
    assert normalized(value["candidate"]) == pin(directory / "candidate-snapshot.json")
    assert snapshot["round"] == "R196" and snapshot["phase"] == phase
    sources = {item["path"]: item for item in snapshot["sources"]}
    protected = {item["path"]: item for item in snapshot["protected"]}
    expected_sources = {item["path"] for item in PLAN["inputs"]
                        if item["path"].startswith((str(ROOT / "src") + "/", str(ROOT / "tests") + "/"))
                        and item["path"] not in PLAN["input_roles"]["protected_paths"]}
    expected_sources.add(PLAN["scope"]["new_test"])
    assert set(sources) == expected_sources and len(sources) == 26
    assert set(protected) == set(PLAN["input_roles"]["protected_paths"]) and len(protected) == 211
    expected_inputs = {item["path"]: item for item in PLAN["inputs"]}
    for path, record in protected.items():
        assert normalized(record) == expected_inputs[path]
        check(record)
    for path, record in sources.items():
        raw = unarchive(record)
        if path == SHARED and phase == "red":
            assert raw == INITIAL_SHARED
        else:
            assert Path(path).read_bytes() == raw
        if path not in (SHARED, PLAN["scope"]["new_test"]):
            assert normalized(record) == expected_inputs[path]
    proof = load(directory / "scope-proof.json")
    assert proof["test_execution"] is False and proof["product_commands"] == 0
    assert proof["owned_count"] == 26 and proof["protected_count"] == 211
    assert proof["both_old_test_files_whole_preserved"] is True
    check(proof["new_test_pin"])
    if phase == "red":
        assert not proof["permitted_product_regions"]
    return {"result": pin(directory / "result.json"), "tool": tool,
            "snapshot": pin(directory / "candidate-snapshot.json"),
            "scope": pin(directory / "scope-proof.json"), "sources": {path: normalized(record) for path, record in sources.items()}}


def case_records(value, expected):
    assert value["errors"] == [] and value["names_match"] is value["all_valid"] is True
    names, records = Counter(), []
    for record in value["records"]:
        check(record["pin"])
        assert record["error"] is None and record["data"] == load(record["pin"]["path"])
        data = record["data"]
        assert data["schema_version"] == "bigsmall.r196-case.v1"
        node = data["nodeid"]
        assert node in expected and Path(record["path"]).name == sha(node.encode()) + ".json"
        assert data["hash_kind"] == "CANONICAL_RAW_ENVELOPE_SHA256"
        assert data["no_live_authority_created_by_test"] is True
        assert data["decoder_calls"] and data["mutation"] is not None
        for key in ("baseline_payload", "changed_payload"):
            assert isinstance(data[key], dict)
            canonical = json.dumps(data[key], allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
            assert sha(canonical) == data[key + "_sha256"]
        names[node] += 1
        records.append(record["pin"])
    assert names == Counter(expected) and dict(names) == value["actual_node_counts"]
    return records


def child(name):
    directory = D / "implementation" / name
    value = load(directory / "result.json")
    command = command_for(name)
    expected_exit = command["expected_exit"]
    assert value["round"] == "R196" and value["command"] == name
    assert value["attempt"] == 1 and value["retry"] == 0
    assert value["child_exit"] == value["wrapper_exit"] == expected_exit
    assert value["accepted_command_outcome"] is True and not value["failures"] and not value["timed_out"]
    assert value["cleanup"]["leader_reaped"] is True and value["cleanup"]["group_remaining"] is False
    check(value["invocation"])
    invocation = load(value["invocation"]["path"])
    invocation_before(invocation, name)
    assert invocation["launcher_argv"] == command["argv"]
    assert invocation["launcher_environment"] == command["finite_env"]
    assert invocation["child_argv"] == command["child_argv"]
    assert invocation["child_cwd"] == command["cwd"]
    assert invocation["child_environment"] == command["child_finite_env"]
    assert invocation["timeout_seconds"] == command["timeout_seconds"]
    assert invocation["shell"] is False and invocation["new_process_session"] is True
    assert invocation["cleanup_grace_max_seconds"] == 15
    check(invocation["script_pin"])
    for record in value["input_records"]:
        input_check(record, name == "red8")
    for record in value["streams"].values():
        check(record)
    receipt = actual_tool(directory, expected_exit, value, child=True)
    observations = {"result": pin(directory / "result.json"), "tool": receipt,
                    "child_exit": value["child_exit"], "wrapper_exit": value["wrapper_exit"],
                    "cleanup": value["cleanup"], "indexes": indexes(value)}
    if name == "ruff":
        assert value["JUnit"] is value["resource_summary"] is value["case_evidence"] is None
        return observations
    expected = PLAN["tests"]["red_nodes" if name == "red8" else "green_nodes"]
    counts = junit(directory / "junit.xml", expected, red=name == "red8")
    assert value["JUnit"] == counts
    summary = load(directory / "resource-summary.json")
    assert summary == value["resource_summary"] and summary["all_sidecars_validated"] is True
    mappings = {**PLAN["resources"]["old_helper_calls"], **PLAN["resources"]["new_helper_calls"]}
    mapping = {node: mappings[node] for node in expected}
    assert mapping == dict.fromkeys(expected, 1)
    observations["resources"] = memory_records(summary, mapping, value["process_pid"])
    raw = summary["raw_sidecar_observations"]
    assert len(raw) == len(summary["sidecars"])
    for item in raw:
        assert item["error"] is None
        check(item["pin"])
        assert item["data"] == load(item["pin"]["path"])
    assert Counter(tuple(normalized(item["pin"]).values()) for item in raw) == Counter(
        tuple(normalized(item).values()) for item in summary["sidecars"])
    new_nodes = [node for node in expected if node in PLAN["resources"]["new_helper_calls"]]
    observations["cases"] = case_records(value["case_evidence"], new_nodes)
    observations["JUnit"] = counts
    return observations


def historical_outcomes():
    accepted = load(P192 / "implementation/root-final-software-evidence-acceptance-review-pending.json")
    assert accepted["candidate_source"]["sha256"] == "f01520073140a08b0e15b947a00c840f486d45bd7dcc434bf44a894b6aae591c"
    assert accepted["T1_complete"] is accepted["T12_complete"] is False
    old_settlement = load(P192 / "implementation/root_settlement/settlement.json")
    evidence = old_settlement["observations"]["original_evidence"]
    for stages in evidence["preparations"].values():
        for receipt in stages.values():
            check(receipt["result"])
            check(receipt["tool"])
    for stages in evidence["children"].values():
        for receipt in stages.values():
            check(receipt["result"])
            check(receipt["tool"])
            value = load(receipt["result"]["path"])
            for record in value["streams"].values():
                check(record)
            for record in value["file_index"]:
                if record.get("sha256") is not None:
                    check(record)
    original38 = accepted["original38_failed"]
    assert (original38["tests"], original38["passes"], original38["failures"],
            original38["child_exit"], original38["wrapper_exit"]) == (38, 37, 1, 1, 2)
    assert original38["original_resource_summary"] is None
    check(original38["result"])
    actual38 = load(original38["result"]["path"])
    assert actual38["JUnit"] is actual38["resource_summary"] is None
    assert not (Path(original38["result"]["path"]).parent / "resource-summary.json").exists()
    for key, total in (("original13_old_source_only", 13), ("new_GREEN51", 51)):
        previous = accepted[key]
        assert previous["tests"] == previous["passes"] == total
        assert previous["failures"] == previous["errors"] == previous["skips"] == 0
        for name in ("result", "tool", "JUnit"):
            check(previous[name])
        for record in previous["resources"]["sidecars"]:
            check(record)
    for record in accepted["all_original_budgets_preserved"]["ledgers"]:
        check(record)
    activation = load(P192 / "root-activation.json")
    for transition in activation["parent_ledger_transitions"]:
        check(transition["current_after"])
    for name in ("command-ledger.json", "root-command-ledger.json"):
        previous = load(P192 / name)
        assert len(previous["commands"]) == 4
        assert all((slot["used"], slot["remaining"]) == (1, 0) for slot in previous["commands"].values())
    review = load(P192 / "review/continuation-read-ledger.json")
    assert review["cumulative"] == {"authorized": 17, "used": 17, "remaining": 0}
    return {"original38": original38, "original13": accepted["original13_old_source_only"],
            "old51": accepted["new_GREEN51"], "old_budgets_reset": False,
            "original_review_spent": 17}



def alarm_handler(signum, frame):
    raise TimeoutError("R196 ROOT metadata cap 120 seconds")


def main():
    global PLAN, GATE
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(120)
    started = time.monotonic()
    assert len(sys.argv) == 1 and Path.cwd() == ROOT
    assert sha((D / "plan.json").read_bytes()) == PLAN_SHA
    PLAN = load(D / "plan.json")
    GATE = load(D / "script-gate.json")["commands"]["root_settlement"]
    command = command_for("root_settlement")
    assert GATE["state"] == "APPROVED"
    assert command["argv"] == GATE["argv"] == [sys.executable, str(Path(__file__).absolute())]
    assert dict(os.environ) == command["finite_env"] == GATE["finite_env"]
    assert command["timeout_seconds"] == GATE["timeout_seconds"] == 120
    check(GATE["script_pin"])
    assert GATE["script_pin"]["path"] == str(Path(__file__).absolute())
    for record in GATE["input_records"]:
        check(record)
    controls = initial_controls()
    root_path, author_path = D / "root-command-ledger.json", D / "command-ledger.json"
    root_raw, author_raw = root_path.read_bytes(), author_path.read_bytes()
    root, author = json.loads(root_raw), json.loads(author_raw)
    assert root["schema_version"] == author["schema_version"] == "bigsmall.r196.command-ledger.v1"
    assert set(root["commands"]) == set(author["commands"]) == {item["id"] for item in PLAN["commands"]}
    root_slot, author_slot = root["commands"]["root_settlement"], author["commands"]["root_settlement"]
    assert (root_slot["used"], root_slot["remaining"], root_slot["state"]) == (1, 0, "RESERVED_BY_ROOT")
    assert root_slot["reservation_id"] == GATE["reservation_id"]
    assert root_slot["gate_pin"] == pin(D / "script-gate.json")
    assert (author_slot["used"], author_slot["remaining"], author_slot["state"]) == (0, 1, "HELD_PENDING_ROOT_GATE")
    for name in ("prepare_red", "red8", "prepare_green", "ruff", "green63"):
        assert (author["commands"][name]["used"], author["commands"][name]["remaining"],
                author["commands"][name]["attempts"]) == (1, 0, 1)
        assert (root["commands"][name]["used"], root["commands"][name]["remaining"]) == (1, 0)
        assert root["commands"][name]["state"].startswith("SPENT_ACTUAL")
    for ledger in (root, author):
        extension = ledger["review_extension"]
        assert extension["previous_used"] == 17 and extension["previous_remaining"] == 0
        assert extension["new_authorized"] == extension["remaining"] == 6
        assert extension["used"] == 0 and extension["released"] is False
    directory = D / "implementation/root_settlement"
    directory.mkdir(exist_ok=False)
    before = {}
    for name, raw in (("root_ledger", root_raw), ("author_ledger", author_raw),
                      ("gate", (D / "script-gate.json").read_bytes()),
                      ("activation", (D / "root-activation.json").read_bytes())):
        physical = directory / (name + "-before.json")
        with physical.open("xb") as stream:
            stream.write(raw)
        before[name] = {**pin(physical), "base64": base64.b64encode(raw).decode()}
    invocation = write(directory / "invocation.json", {
        "round": "R196", "command": "root_settlement", "argv": command["argv"],
        "cwd": str(ROOT), "finite_env": command["finite_env"], "timeout_seconds": 120,
        "attempt": 1, "retry": 0, "script_pin": pin(Path(__file__).absolute()),
        "reservation_id": GATE["reservation_id"], "before_metadata": before,
        "outer_capture": GATE["transport"], "product_execution": False})
    author_slot.update(used=1, remaining=0, state="SPENT_BY_ROOT_BEFORE_ACTION",
                       attempts=1, retry=0, reservation_id=GATE["reservation_id"])
    assert author_path.read_bytes() == author_raw
    author_path.write_text(json.dumps(author, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    failures, observations = [], None
    try:
        previous = historical_outcomes()
        red_prepare, green_prepare = preparation("red"), preparation("green")
        assert set(red_prepare["sources"]) == set(green_prepare["sources"])
        for path in red_prepare["sources"]:
            if path != SHARED:
                assert red_prepare["sources"][path] == green_prepare["sources"][path]
        source = bounded_source(INITIAL_SHARED, Path(SHARED).read_bytes())
        red, ruff, green = child("red8"), child("ruff"), child("green63")
        for record in GATE["input_records"]:
            check(record)
        observations = {"controls": controls, "historical_software_only": previous,
                        "prepare_red": red_prepare, "prepare_green": green_prepare,
                        "source_proof": source, "new_RED8": red, "new_ruff": ruff,
                        "new_GREEN63": green, "previous_review_used": 17,
                        "new_same_seat_review_batches_held": 6,
                        "T1_requires_independent_review": True}
    except BaseException as error:
        failures.append({"type": type(error).__name__, "message": str(error),
                         "traceback": "".join(traceback.format_exception(error))})
    settlement = write(directory / "settlement.json", {
        "round": "R196", "status": "SOFTWARE_EVIDENCE_ACCEPTED_REVIEW_PENDING" if not failures else "FAILED",
        "observations": observations, "failures": failures, "T1_complete": False,
        "T12_complete": False, "native": False, "formal": False})
    result = {"round": "R196", "command": "root_settlement", "attempt": 1, "retry": 0,
              "exit_code": 0 if not failures else 1, "product_commands": 0,
              "test_execution": False, "elapsed_seconds": time.monotonic() - started,
              "timed_out": any(value["type"] == "TimeoutError" for value in failures),
              "invocation": invocation, "settlement": settlement,
              "input_records": GATE["input_records"], "failures": failures,
              "T1_complete": False, "T12_complete": False, "native": False, "formal": False}
    record = write(directory / "result.json", result)
    signal.alarm(0)
    print(json.dumps({"round": "R196", "command": "root_settlement",
                      "exit_code": result["exit_code"], "result": record}))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
