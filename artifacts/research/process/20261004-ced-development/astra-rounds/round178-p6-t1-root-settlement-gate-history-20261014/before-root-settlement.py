from pathlib import Path
import base64
import hashlib
import json
import signal
import traceback
from xml.etree import ElementTree as ET

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUNDS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
ROUND = ROUNDS / "round175-p6-t1-transitive-memory-fixture-closure-20261014"
OUT = ROUND / "implementation"
RAW = OUT / "recovery7"
PLAN_SHA = "990947b3491a5fdd432c75fbde321cccd417681adf3cec062b4252a8ef100e63"
FIELDS = {"_events", "_budgets", "_active_contracts", "_checkpoints"}
COUNT_KEYS = {"allocation_attempts", "initialized", "init_failed", "primary", "transitive",
              "close_attempts", "close_returns", "close_errors", "initialized_successfully_closed"}

def timeout(signum, frame):
    raise TimeoutError("R175 ROOT settlement exceeded 120 seconds")

signal.signal(signal.SIGALRM, timeout)
signal.alarm(120)

def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def pin(path):
    path = Path(path)
    assert path.is_file() and not path.is_symlink(), str(path)
    assert path.is_relative_to(ROOT), str(path)
    assert all(not parent.is_symlink() for parent in path.parents), str(path)
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": sha(raw)}

def checked(record):
    assert type(record) is dict
    actual = pin(record["path"])
    assert actual["bytes"] == record["bytes"] and actual["sha256"] == record["sha256"], record["path"]
    return actual

def pairs(items):
    result = {}
    for key, value in items:
        assert key not in result, ("duplicate JSON key", key)
        result[key] = value
    return result

def read(path):
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))

def exclusive(path, value):
    raw = encode(value)
    with path.open("xb") as stream:
        stream.write(raw)
    assert path.read_bytes() == raw
    return pin(path)

def actual_exit(document):
    assert type(document) is dict and type(document["initial"]) is dict
    final = document.get("completion")
    if final is None:
        final = document["initial"]
    assert type(final) is dict and type(final["exit_code"]) is int
    return final["exit_code"]

def positive(value):
    return type(value) is int and value > 0

def validate_call(observation, expected_nodes, pid):
    assert observation["schema_version"] == "bigsmall.r175-memory-lifecycle.v1"
    assert observation["nodeid"] in expected_nodes
    assert observation["PYTEST_CURRENT_TEST"].rsplit(" (", 1)[0] == observation["nodeid"]
    assert positive(observation["pid"]) and observation["pid"] == pid
    assert positive(observation["thread"]) and positive(observation["native_thread"])
    assert observation["success"] is True and observation["failures"] == []
    assert observation["untracked_close_calls"] == []
    assert set(observation["observed_fields"]) == FIELDS
    assert observation["repository_class_module"] == "cloud_edge_robot_arm.repositories.event_autonomy.memory"
    assert observation["repository_class_qualname"] == "InMemoryEventAutonomyRepository"
    assert set(observation["methods_restored"]) == {"__init__", "close"}
    assert all(value is True for value in observation["methods_restored"].values())
    assert observation["original_method_ids"] == observation["restored_method_ids"]
    assert set(observation["original_method_ids"]) == {"__init__", "close"}
    assert all(positive(value) for value in observation["original_method_ids"].values())
    assert observation["local_checks"] and all(value is True for value in observation["local_checks"].values())
    objects = observation["objects"]
    assert type(objects) is list and objects
    ids = [item["object_id"] for item in objects]
    assert all(positive(value) for value in ids) and len(ids) == len(set(ids))
    counts = dict.fromkeys(COUNT_KEYS, 0)
    for item in objects:
        assert item["init_attempted"] is True and item["initialized"] is True
        assert item["init_error"] is None and item["safe_real_close_available"] is True
        assert item["init_return_type"] == "NoneType"
        assert item["class_module"] == observation["repository_class_module"]
        assert item["class_qualname"] == observation["repository_class_qualname"]
        assert item["role"] in ("primary", "transitive")
        assert item["init_thread"] == observation["thread"]
        assert item["init_native_thread"] == observation["native_thread"]
        counts["allocation_attempts"] += 1
        counts["initialized"] += 1
        counts[item["role"]] += 1
        assert item["successful_close_observed"] is True
        attempts = item["close_calls"]
        assert type(attempts) is list and attempts
        for attempt in attempts:
            counts["close_attempts"] += 1
            assert attempt["thread"] == observation["thread"]
            assert attempt["native_thread"] == observation["native_thread"]
            assert attempt["returned"] is True and attempt["successful"] is True
            assert attempt["error"] is None and attempt["return_type"] == "NoneType"
            assert attempt["return_value"] is None
            fields = attempt["post_close_field_counts"]
            assert set(fields) == FIELDS
            assert all(type(value) is int and value == 0 for value in fields.values())
            counts["close_returns"] += 1
        counts["initialized_successfully_closed"] += 1
    assert set(observation["counts"]) == COUNT_KEYS
    assert all(type(value) is int for value in observation["counts"].values())
    assert counts == observation["counts"]
    assert counts["primary"] == 1 and counts["transitive"] >= 1
    assert counts["allocation_attempts"] == counts["initialized"] == counts["initialized_successfully_closed"]
    assert counts["init_failed"] == counts["close_errors"] == 0
    assert all(value is None for value in observation["unobserved"].values())
    return counts

assert Path.cwd() == ROOT
plan = read(ROUND / "plan.json")
assert pin(ROUND / "plan.json")["sha256"] == PLAN_SHA
gate = read(ROUND / "script-gate.json")["commands"]["ROOT_settlement_metadata"]
assert gate["state"] == "APPROVED"
assert gate["argv"] == plan["command_budget"]["ROOT_settlement_metadata"]["argv"]
assert gate["cwd"] == str(ROOT) and gate["timeout_seconds"] == 120
assert checked(gate["source_pin"])["path"] == str(Path(__file__))
author_path = ROUND / "command-ledger.json"
root_path = ROUND / "root-command-ledger.json"
author_bytes, root_bytes = author_path.read_bytes(), root_path.read_bytes()
author, root_ledger = read(author_path), read(root_path)
for role, ledger in (("author", author), ("root", root_ledger)):
    assert ledger["schema_version"] == "bigsmall.r175-" + ("command" if role == "author" else "root-command") + "-ledger.v1"
    assert ledger["role"] == role and ledger["round"] == "R175"
    assert ledger["plan_sha256"] == PLAN_SHA and ledger["no_retry"] is True
    assert set(ledger["commands"]) == {"preparation_metadata", "recovery7", "ROOT_settlement_metadata"}
    for name, entry in ledger["commands"].items():
        contract = plan["command_budget"][name]
        assert entry["authorized"] == entry["max_attempts"] == 1
        assert entry["argv"] == contract.get("argv")
        assert entry["outer_runner_argv"] == contract.get("outer_runner_argv")
        assert entry["cwd"] == str(ROOT) and entry["timeout_seconds"] == contract["timeout_seconds"]
        if name != "ROOT_settlement_metadata":
            assert entry["used"] == 1 and entry["remaining"] == 0
            assert entry["state"] == ("RESERVED_BY_ROOT" if role == "root" and name == "recovery7" else "SPENT")
selected_root = root_ledger["commands"]["ROOT_settlement_metadata"]
assert selected_root["state"] == "RESERVED_BY_ROOT" and selected_root["used"] == 1 and selected_root["remaining"] == 0
selected = author["commands"]["ROOT_settlement_metadata"]
assert selected["state"] == "HELD" and selected["used"] == 0 and selected["remaining"] == 1
selected.update({"state": "SPENT", "used": 1, "remaining": 0, "attempts": 1, "retries": 0,
                 "reservation_id": selected_root["reservation_id"]})
assert author_path.read_bytes() == author_bytes
author_path.write_bytes(encode(author))
spent_author_bytes = author_path.read_bytes()
result = {"schema_version": "bigsmall.r175-root-settlement-result.v1",
          "used": 1, "remaining": 0, "attempts": 1, "retries": 0,
          "reservation_id": selected_root["reservation_id"], "exit_code": None}
try:
    stable = [checked(record) for record in gate["input_records"]]
    snapshot = read(OUT / "candidate-snapshot.json")
    assert len(snapshot["sources"]) == 24 and len(snapshot["protected"]) == 211
    for item in snapshot["sources"]:
        raw = base64.b64decode(item["base64"], validate=True)
        assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
        assert Path(item["path"]).read_bytes() == raw
    for item in snapshot["protected"] + snapshot["parent_ledger_pins"]:
        checked(item)
    proof = read(OUT / "scope-proof.json")
    for key in ("test_outside_helper_byte_identical", "R174_JSON_boundary_helper_byte_identical",
                "production_23_byte_identical_to_settled_snapshot", "seven_bodies_unchanged", "A80556_unchanged"):
        assert proof[key] is True
    archives = read(OUT / "before-t1-reports.json")["records"]
    assert len(archives) == 13
    assert [{key: item[key] for key in ("path", "bytes", "sha256")} for item in archives] == plan["preparation"]["archive_reports"]
    for item in archives:
        raw = base64.b64decode(item["base64"], validate=True)
        assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
    assert pin(OUT / "before-test.py")["bytes"] == 125299
    assert pin(OUT / "before-test.py")["sha256"] == "42a5a079bbd41b3d52adf683ce4e5c07d8678333adf367d7833dee496d4825d6"
    actual = read(RAW / "actual-tool-return.json")
    assert actual_exit(actual) == 0
    raw_result = read(RAW / "result.json")
    assert raw_result["product_exit"] == raw_result["runner_exit"] == 0
    assert raw_result["started"] is True and raw_result["timed_out"] is False
    assert raw_result["used"] == 1 and raw_result["remaining"] == 0 and raw_result["attempts"] == 1 and raw_result["retries"] == 0
    assert raw_result["spawn_error"] is None and raw_result["evidence_errors"] == []
    assert raw_result["cleanup"]["errors"] == []
    assert raw_result["cleanup"]["leader_reaped"] is True
    assert raw_result["cleanup"]["remaining_process_group_observed"] is False
    for item in raw_result["artifacts"]:
        checked(item)
    invocation = read(RAW / "invocation.json")
    contract = plan["command_budget"]["recovery7"]
    for key in ("argv", "outer_runner_argv", "cwd", "actual_environment", "timeout_seconds", "resource_caps"):
        assert invocation[key] == contract[key]
    assert invocation["shell"] is False and invocation["start_new_session"] is True
    assert invocation["attempts"] == 1 and invocation["retries"] == 0
    nodes = contract["argv"][6:13]
    cases = list(ET.fromstring((RAW / "junit.xml").read_bytes()).iter("testcase"))
    assert len(cases) == 7 and len({case.attrib["name"] for case in cases}) == 7
    assert {case.attrib["name"] for case in cases} == {node.split("::", 1)[1] for node in nodes}
    assert all(case.find(tag) is None for case in cases for tag in ("failure", "error", "skipped"))
    assert all(raw_result["junit"][key] == value for key, value in contract["expected_junit"].items())
    post = read(RAW / "post-run-input-pins.json")
    assert post["matches_pre_run"] is True and post["errors"] == []
    assert post["input_pins"] == invocation["pre_input_pins"]
    for item in post["input_pins"]:
        checked(item)
    resource = read(RAW / "resource-summary.json")
    assert resource["status"] == "MEMORY_LIFECYCLE_ACTUAL_RECORDS_VALIDATED"
    sidecars = sorted((RAW / "resources").iterdir())
    assert len(sidecars) == resource["call_count"] and sidecars
    assert all(path.is_file() and not path.is_symlink() and path.suffix == ".json" for path in sidecars)
    totals = dict.fromkeys(COUNT_KEYS, 0)
    calls, actual_sidecar_pins, call_ids = [], [], set()
    for path in sidecars:
        observation = read(path)
        assert path.name == observation["call_id"] + ".json"
        assert observation["call_id"] not in call_ids
        call_ids.add(observation["call_id"])
        counts = validate_call(observation, set(nodes), raw_result["pid"])
        totals = {key: totals[key] + counts[key] for key in COUNT_KEYS}
        calls.append(observation)
        actual_sidecar_pins.append(pin(path))
    assert {call["nodeid"] for call in calls} == set(nodes)
    assert resource["totals"] == totals and resource["node_count"] == 7
    assert resource["calls_per_node"] == {node: sum(call["nodeid"] == node for call in calls) for node in nodes}
    assert resource["calls"] == calls
    assert resource["sidecar_pins"] == actual_sidecar_pins
    assert raw_result["resource_evidence"]["memory_lifecycle"] == resource
    for key in ("worker_lifecycles", "maximum_workers_concurrent", "broker_threads_per_worker",
                "heartbeat_threads_per_worker", "external_model_calls", "network_calls",
                "GPU_native_calls", "worker_and_thread_closure", "test_lifecycle_evidence"):
        assert raw_result["resource_evidence"][key] is None
    assert all(value is None for value in resource["unobserved"].values())
    disposition = read(ROUND / "prior-slot-disposition.json")
    assert gate["old_settlement_disposition"] == "HELD_SUPERSEDED_BY_R175_NO_EXECUTION"
    prior = ROUNDS / "round174-p6-t1-legacy-condition-json-normalization-20261014/implementation/recovery7"
    prior_result = read(prior / "result.json")
    assert prior_result["product_exit"] == prior_result["runner_exit"] == 0
    prior_cases = list(ET.fromstring((prior / "junit.xml").read_bytes()).iter("testcase"))
    assert len(prior_cases) == 7
    assert all(case.find(tag) is None for case in prior_cases for tag in ("failure", "error", "skipped"))
    original = ROUNDS / "round158-p6-stage-b-local-temporal-publication-20261013/implementation/t1_green"
    original_cases = list(ET.fromstring((original / "junit.xml").read_bytes()).iter("testcase"))
    assert len(original_cases) == 7 and sum(case.find("failure") is not None for case in original_cases) == 2
    assert all(case.find(tag) is None for case in original_cases for tag in ("error", "skipped"))
    assert snapshot["usage"]["R158_used"] == 3 and snapshot["usage"]["R158_remaining"] == 12
    for record in gate["input_records"]:
        checked(record)
    assert root_path.read_bytes() == root_bytes and author_path.read_bytes() == spent_author_bytes
    settlement = {"schema_version": "bigsmall.r175-root-settlement.v1",
                  "status": "ROOT_ACCEPTED_ACTUAL_7PASS_AND_OBSERVED_MEMORY_LIFECYCLE_ONLY",
                  "source_scope_verified": True, "protected_inputs": 211, "owned_sources": 24,
                  "original_reports_archived": 13, "actual_counts": contract["expected_junit"],
                  "product_exit": 0, "runner_exit": 0, "resource_totals": totals,
                  "resource_call_count": len(calls), "resource_node_count": 7,
                  "sidecar_pins": actual_sidecar_pins, "stable_inputs": stable,
                  "prior_R174_7PASS_preserved": True, "original_GREEN_5PASS_2FAIL_preserved": True,
                  "old_R174_ROOT_settlement_used": 0,
                  "old_R174_ROOT_settlement_effective": gate["old_settlement_disposition"],
                  "R158_used": 3, "R158_remaining": 12, "fresh_T1_review_started": False,
                  "targeted_R173_accessor_execution": False,
                  "T1_complete": False, "B9_complete": False, "T12_complete": False,
                  "native": False, "actual": False, "formal": False,
                  "limits": "Observed Memory lifecycle only; unchanged clock assertions remain separate. No unobserved runtime counter invented.",
                  "raw_pins": [pin(RAW / name) for name in
                               ("actual-tool-return.json", "result.json", "stdout.txt", "stderr.txt",
                                "junit.xml", "invocation.json", "resource-summary.json",
                                "post-run-input-pins.json", "fixture-index.json")]}
    result["settlement_pin"] = exclusive(OUT / "root-settlement.json", settlement)
    result["exit_code"] = 0
except BaseException as error:
    result["exit_code"] = 2
    result["error"] = {"type": type(error).__name__, "message": str(error),
                       "traceback": "".join(traceback.format_exception(error))}
result_pin = exclusive(OUT / "root-settlement-result.json", result)
print(json.dumps({"result": result_pin, "actual_result": result}, ensure_ascii=False, sort_keys=True))
raise SystemExit(result["exit_code"])
