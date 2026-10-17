"""ROOT-only R232 continuation of the original R223 settlement slot; stdlib only."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time
import traceback

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUND = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round223-p6-t2-public-writer-binding-race-20261015"
RECOVERY_ROUND = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round232-p6-t2-genuine-poll-observer-caller-identity-20261015"
OUT = RECOVERY_ROUND / "implementation/root_settlement"
RECOVERY_PLAN_SHA = "e960d36fe679dc2b24860346e564682a65a6acddd0663f8eeb824d3a3540bc0f"
PLAN_SHA = "b186bd493c25197c7d1f50c11b0725772d7d88f1d086c85bc0bc588da7275dff"
KEYS = ("R223:prepare_red", "R223:red", "R232:prepare_red", "R232:red", "R223:prepare_green", "R223:ruff", "R223:green")
CHECKS: list[dict] = []
PINS: list[dict] = []


def require(name: str, passed: bool, detail: object = None) -> None:
    CHECKS.append({"name": name, "passed": bool(passed), "detail": detail})
    if not passed:
        raise ValueError(name)


def read_json(path: Path) -> object:
    return json.loads(path.read_bytes())


def pin(path: Path) -> dict:
    value = path.read_bytes()
    return {"path": str(path), "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}


def identity(record: dict) -> dict:
    return {key: record[key] for key in ("path", "bytes", "sha256")}


def verify(record: dict, label: str) -> dict:
    require(label + ".record", isinstance(record, dict))
    expected = identity(record)
    actual = pin(Path(expected["path"]))
    PINS.append({"label": label, "expected": record, "observed": actual, "matches": actual == expected})
    require(label + ".pin", actual == expected)
    return actual


def document(record: dict, label: str) -> object:
    verify(record, label)
    return read_json(Path(record["path"]))


def write_json(path: Path, value: object) -> dict:
    with path.open("xb") as stream:
        stream.write((json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    return pin(path)


def lookup(value: object, field_path: list) -> object:
    for key in field_path:
        if isinstance(value, dict) and isinstance(key, str):
            value = value[key]
        elif isinstance(value, list) and isinstance(key, int) and not isinstance(key, bool):
            value = value[key]
        else:
            raise TypeError("Invalid explicit evidence field path")
    return value


def exact_json(left: object, right: object) -> bool:
    options = {"sort_keys": True, "separators": (",", ":"), "allow_nan": False}
    return json.dumps(left, **options) == json.dumps(right, **options)


def predecessor_result(key: str, result: dict, slot: dict, *, historical_failure: bool = False) -> None:
    require(key + ".command", result["command"] == key and result["attempt"] == 1 and result["retry"] == 0)
    if key.startswith("prepare_"):
        require(key + ".metadata_success", type(result["exit_code"]) is int and result["exit_code"] == 0 and result["test_execution"] is False and result["product_commands"] == 0)
        require(key + ".metadata_checks", bool(result["checks"]) and all(row["passed"] is True for row in result["checks"]))
        for index, row in enumerate(result["outputs"]):
            verify(row, key + ".output." + str(index))
        return
    expected_exit = 1 if key == "red" else 0
    require(key + ".actual_numeric_outcome", type(result["child_exit"]) is int and result["child_exit"] == expected_exit and result["wrapper_exit"] == expected_exit and result["accepted_command_outcome"] is (not historical_failure) and result["timed_out"] is False)
    require(key + ".transport_cleanup", result["cleanup"]["leader_reaped"] is True and result["cleanup"]["group_remaining"] is False and result["runner_exception"] is None and result["observation_errors"] == [])
    require(key + ".invocation", result["invocation"]["argv"] == slot["argv"] and result["invocation"]["finite_env"] == slot["finite_env"] and result["invocation"]["timeout_seconds"] == slot["timeout_seconds"])
    for stream in ("stdout", "stderr"):
        verify(result["streams"][stream], key + ".stream." + stream)
    if key == "ruff":
        require("ruff.no_runtime_evidence", result["JUnit"] is None and result["resource_summary"] is None and result["cases"] == [])
        return
    nodes = [arg for arg in slot["argv"] if "::" in arg]
    junit = result["JUnit"]
    expected = (3, 0, 3, 0, 0) if key == "red" else (9, 9, 0, 0, 0)
    observed = tuple(junit[name] for name in ("tests", "passes", "failures", "errors", "skips"))
    require(key + ".junit", observed == expected and junit["nodeids"] == nodes and junit["names_exact"] is True)
    if key == "red":
        failure_text = "only genuine exact worker poll opens session" if historical_failure else "R223 late local binding was not rejected"
        require("red.exact_failure_generation", len(junit["failure_details"]) == 3 and all(failure_text in row["text"] for row in junit["failure_details"]))
    resources = result["resource_summary"]
    require(key + ".resources", resources["all_records_valid"] is True and resources["validation_errors"] == [] and resources["actual_node_attempts"] == len(nodes) and resources["actual_node_counts"] == {node: 1 for node in nodes})
    require(key + ".resource_caps", type(resources["counts"]["attempted_poll_lifecycles"]) is int and resources["counts"]["attempted_poll_lifecycles"] <= 18 and resources["counts"]["attempted_poll_lifecycles"] <= 64 and resources["peak_active_polls_per_node"] <= 2)
    require(key + ".unknown_measurements", all(value is None for value in resources["unobserved"].values()))
    for index, row in enumerate(resources["records"]):
        verify(row["pin"], key + ".resource." + str(index))
        require(key + ".resource_bytes." + str(index), exact_json(read_json(Path(row["pin"]["path"])), row["data"]))
        require(key + ".resource_cleanup." + str(index), row["error"] is None and row["data"]["cleanup_errors"] == [] and row["data"]["observations"]["observers_restored"] is True and all(resource["cleanup_observed"] is True for resource in row["data"]["resources"]))
        if key == "green":
            require("green.assertions_completed." + str(index), row["data"]["observations"]["assertions_completed"] is True)
    cases = result["cases"]
    require(key + ".cases", len(cases) == len(nodes) and {Path(row["pin"]["path"]).name for row in cases} == {hashlib.sha256(node.encode()).hexdigest() + ".json" for node in nodes})
    for index, row in enumerate(cases):
        verify(row["pin"], key + ".case." + str(index))
        require(key + ".case_bytes." + str(index), exact_json(read_json(Path(row["pin"]["path"])), row["data"]))
        if key == "red":
            data = row["data"]
            if historical_failure:
                require("historical_red.never_bootstrapped." + str(index), data["bootstrap_complete"] is False)
            else:
                require("red.real_vulnerable_behavior." + str(index), data["bootstrap_complete"] is True and data["writer"]["returned"] is True and data["writer"]["exception"] is None and data["legacy_after"] != data["legacy_before"] and data["writer_joined"] is True)


def source_records(record: dict, label: str) -> dict:
    data = document(record, label)
    require(label + ".schema", isinstance(data, dict) and isinstance(data.get("sources"), list))
    result = {}
    for index, row in enumerate(data["sources"]):
        require(label + ".source_shape." + str(index), isinstance(row, dict))
        original = identity(row)
        require(label + ".unique." + str(index), original["path"] not in result)
        decoded = base64.b64decode(row["base64"], validate=True)
        require(label + ".full_bytes." + str(index), len(decoded) == original["bytes"] and hashlib.sha256(decoded).hexdigest() == original["sha256"])
        result[original["path"]] = row
    return result


def verify_source_archives(label: str, sources: dict, records: list) -> None:
    require(label + ".archive_count", isinstance(records, list) and len(records) == 27)
    require(label + ".archive_paths", {row["source_path"] for row in records} == set(sources))
    for index, row in enumerate(records):
        source = sources[row["source_path"]]
        archive = verify(row["archive"], label + ".archive." + str(index))
        require(label + ".archive_bytes." + str(index), archive["bytes"] == source["bytes"] and archive["sha256"] == source["sha256"] and Path(archive["path"]).read_bytes() == base64.b64decode(source["base64"], validate=True))


def main() -> dict:
    started = time.time()
    require("cwd", Path.cwd() == ROOT)
    require("plan", pin(ROUND / "plan.json")["sha256"] == PLAN_SHA)
    require("recovery_plan", pin(RECOVERY_ROUND / "plan.json")["sha256"] == RECOVERY_PLAN_SHA)
    gate = read_json(ROUND / "script-gate.json")
    ledger = read_json(ROUND / "root-command-ledger.json")
    require("gate_object", isinstance(gate, dict) and isinstance(gate.get("commands"), dict))
    command = gate["commands"]["root_settlement"]
    require("gate_fully_reviewed", command.get("full_source_reviewed") is True)
    verify(command["source"], "settlement_source")
    require("own_source", Path(command["source"]["path"]) == Path(__file__).absolute())
    require("own_root_reservation", ledger["commands"]["root_settlement"]["used"] == 1 and ledger["commands"]["root_settlement"]["remaining"] == 0 and ledger["commands"]["root_settlement"]["state"] == "RESERVED_BY_ROOT")
    plan = read_json(ROUND / "plan.json")
    recovery_plan = read_json(RECOVERY_ROUND / "plan.json")
    original_slots = {row["key"]: row for row in plan["execution"]["new_slots"]}
    recovery_slots = {row["key"]: row for row in recovery_plan["execution"]["new_slots"]}
    slots = {"R223:" + key: value for key, value in original_slots.items()}
    slots.update({"R232:" + key: value for key, value in recovery_slots.items()})
    slot = recovery_plan["continuation"]["settlement_replacement"]
    require("actual_settlement_argv", sys.argv == slot["argv"][1:] and command["argv"] == slot["argv"])
    require("settlement_finite_environment", command["finite_env"] == slot["finite_env"] and {name: os.environ.get(name) for name in slot["finite_env"]} == slot["finite_env"] and command["timeout_seconds"] == 120)
    require("own_reservation_identity", command["reservation_id"] == ledger["commands"]["root_settlement"]["reservation_id"])
    write_json(OUT / "invocation.json", {"round": "R223", "command": "root_settlement", "argv": slot["argv"], "cwd": str(ROOT), "finite_env": slot["finite_env"], "timeout_seconds": 120, "attempt": 1, "retry": 0, "source": command["source"], "reservation_id": command["reservation_id"], "script_gate": pin(ROUND / "script-gate.json"), "root_ledger": pin(ROUND / "root-command-ledger.json"), "outer_capture": command["transport"], "independent_tool_streams": None})
    require("inputs_nonempty", isinstance(command.get("input_records"), list) and bool(command["input_records"]))
    for index, row in enumerate(command["input_records"]):
        verify(row, "gate_input." + str(index))
    contract = command["settlement_contract"]
    require("contract_version", contract["schema_version"] == "r232-r223-root-settlement-contract.v1")
    require("exact_predecessors", set(contract["predecessors"]) == set(KEYS))
    for key in KEYS:
        item = contract["predecessors"][key]
        result = document(item["result"], key + ".result")
        actual = document(item["actual_tool_return"], key + ".actual_tool_return")
        acceptance = document(item["root_acceptance"], key + ".root_acceptance")
        require(key + ".raw_objects", isinstance(result, dict) and isinstance(actual, dict) and isinstance(acceptance, dict))
        round_name, command_key = key.split(":", 1)
        predecessor_result(command_key, result, slots[key], historical_failure=key == "R223:red")
        role_ledger = ledger if round_name == "R223" else read_json(RECOVERY_ROUND / "root-command-ledger.json")
        root_entry = role_ledger["commands"][command_key]
        require(key + ".root_spent", root_entry["used"] == 1 and root_entry["remaining"] == 0)
        if key == "R223:red":
            require("historical_red.permanently_failed", root_entry["state"] == "SPENT_UNEXPECTED_STARTUP_GUARD_NOT_LEGAL_RED_R232")
        for index, row in enumerate(item["raw_records"]):
            verify(row, key + ".raw." + str(index))
    author = read_json(ROUND / "command-ledger.json")
    require("author_commands", isinstance(author, dict) and isinstance(author.get("commands"), dict))
    recovery_author = read_json(RECOVERY_ROUND / "command-ledger.json")
    for key in KEYS:
        round_name, command_key = key.split(":", 1)
        role_author = author if round_name == "R223" else recovery_author
        require(key + ".author_spent", role_author["commands"][command_key]["used"] == 1 and role_author["commands"][command_key]["remaining"] == 0)
    require("root_only_author_entry_unspent", author["commands"]["root_settlement"]["used"] == 0 and author["commands"]["root_settlement"]["remaining"] == 1)
    require("field_checks_nonempty", isinstance(contract["field_checks"], list) and bool(contract["field_checks"]))
    categories = set()
    for index, row in enumerate(contract["field_checks"]):
        doc = document(row["document"], "field_document." + str(index))
        actual = lookup(doc, row["field_path"])
        require("field." + str(index) + "." + row["name"], exact_json(actual, row["expected"]), {"field_path": row["field_path"], "observed": actual, "expected": row["expected"]})
        categories.add(row["category"])
    require("field_categories", categories >= {"transport", "red", "green", "ruff", "resource", "cleanup", "case", "scope", "roles", "historical_red", "recovery_baseline"})
    historical = source_records(contract["historical_source_index"], "historical_sources")
    red = source_records(contract["red_source_index"], "red_sources")
    green = source_records(contract["green_source_index"], "green_sources")
    verify_source_archives("historical_sources", historical, contract["historical_source_archives"])
    verify_source_archives("red_sources", red, contract["red_source_archives"])
    verify_source_archives("green_sources", green, contract["green_source_archives"])
    paths = contract["source_paths"]
    event_paths = contract["event_product_paths"]
    parent_paths = contract["parent_product_paths"]
    parent_plan_path = ROUND.parent / "round158-p6-stage-b-local-temporal-publication-20261013/plan.json"
    parent_manifest_path = parent_plan_path.parent / "input-pins.json"
    parent_plan = document(next(row for row in plan["inputs"] if row["path"] == str(parent_plan_path)), "original_parent_plan")
    parent_manifest = document(next(row for row in plan["inputs"] if row["path"] == str(parent_manifest_path)), "original_parent_manifest")
    expected_paths = parent_plan["scope"]["owned_paths"] + [str(ROOT / "tests/test_local_temporal_projection_closure.py"), str(ROOT / "tests/test_local_temporal_promotion_bindings.py"), plan["scope"]["test_new"]]
    require("source_paths_27", len(paths) == 27 and len(set(paths)) == 27 and set(historical) == set(red) == set(paths) == set(green))
    require("source_paths_exact_authority", set(paths) == set(expected_paths))
    require("event_paths_3", len(event_paths) == 3 and len(set(event_paths)) == 3 and set(event_paths) <= set(paths))
    require("event_paths_exact_authority", event_paths == plan["scope"]["product"])
    require("parent_paths_19", len(parent_paths) == 19 and len(set(parent_paths)) == 19 and set(parent_paths) <= set(paths))
    require("parent_paths_exact_authority", parent_paths == [str(ROOT / path) for path in parent_plan["tasks"][1]["owned_paths"] if path.startswith("src/")])
    caller_paths = recovery_plan["scope"]["product"]
    require("caller_paths_2", len(caller_paths) == 2 and len(set(caller_paths)) == 2 and set(caller_paths) <= set(paths) and not set(caller_paths).intersection(event_paths))
    for path in paths:
        if path in caller_paths:
            require("caller_delta_before_recovery_red." + path, identity(historical[path]) != identity(red[path]))
        else:
            require("frozen_before_recovery_red." + path, identity(historical[path]) == identity(red[path]) and historical[path]["mode"] == red[path]["mode"])
        verify(green[path], "live_candidate." + path)
        require("live_mode." + path, Path(path).stat().st_mode == green[path]["mode"])
        if path not in event_paths:
            require("frozen_red_to_green." + path, identity(red[path]) == identity(green[path]) and red[path]["mode"] == green[path]["mode"])
        else:
            require("event_delta." + path, identity(red[path]) != identity(green[path]))
    protected = contract["protected"]
    require("protected211", len(protected) == 211 and len({row["path"] for row in protected}) == 211)
    require("protected_exact_authority", exact_json(protected, parent_manifest["protected"]))
    for index, row in enumerate(protected):
        verify(row, "protected." + str(index))
    for index, row in enumerate(contract["frozen_test_runner"]):
        verify(row, "frozen_test_runner." + str(index))
    require("frozen_test_runner_count", len(contract["frozen_test_runner"]) == 2)
    scope = document(contract["writer_fence_scope"], "writer_fence_scope")
    entries = scope["entries"]
    require("writer_inventory72", isinstance(entries, list) and len(entries) == 72)
    pairs = {(row["backend"], row["method"]) for row in entries}
    expected_pairs = {(backend, name) for backend in ("memory", "sqlite") for name in contract["writer_names"]}
    require("writer_names36", len(contract["writer_names"]) == 36 and len(set(contract["writer_names"])) == 36)
    require("writer_inventory_complete", len(pairs) == 72 and pairs == expected_pairs)
    for index, row in enumerate(entries):
        require("writer_entry_fields." + str(index), all(key in row for key in ("backend", "method", "path", "qualified_function", "lock", "transaction", "guard_location", "first_effect", "source_pin")))
        require("writer_entry_candidate." + str(index), row["path"] in event_paths and identity(row["source_pin"]) == identity(green[row["path"]]))
        require("writer_entry_review." + str(index), row == contract["reviewed_writer_fence_inventory"][index])
    require("all_checks", all(row["passed"] for row in CHECKS))
    report = {
        "schema_version": "r232-r223-root-settlement.v1", "status": "PASS_BOUNDED_R223_SOFTWARE_ONLY",
        "recovery_round": "R232", "historical_RED_accepted": False, "recovery_RED_accepted": True,
        "source_intervals": {"historical_to_recovery": "caller2 only", "recovery_to_GREEN": "event3 only"},
        "round": "R223", "checks": CHECKS, "pin_records": PINS, "elapsed_seconds": time.time() - started,
        "candidate_sources": [identity(green[path]) for path in paths],
        "source_inventory_entries": 72, "runtime_cases_green": 9,
        "product_execution": False, "parent_T2_complete": False,
        "original_GREEN7_released": False, "native_or_formal_acceptance": False,
        "limits": "Source inventory72 is not72 runtime tests; parent T2 GREEN7 and fresh review remain required.",
    }
    output = write_json(OUT / "settlement.json", report)
    summary = json.dumps({"status": report["status"], "checks": len(CHECKS), "pins": len(PINS), "settlement": output, "T2_complete": False}, ensure_ascii=False)
    require("stdout_cap", len(summary.encode("utf-8")) <= 6000)
    return output


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("R223 ROOT settlement 120s")))
        signal.alarm(120)
        output = main()
        result = write_json(OUT / "result.json", {"round": "R223", "command": "root_settlement", "exit_code": 0, "attempt": 1, "retry": 0, "test_execution": False, "product_commands": 0, "outputs": [pin(OUT / "invocation.json"), output], "checks": CHECKS, "T2_complete": False})
        signal.alarm(0)
        print(json.dumps({"command": "root_settlement", "exit_code": 0, "result": result, "settlement": output, "T2_complete": False}, ensure_ascii=False))
    except BaseException as error:
        signal.alarm(0)
        target = OUT / "failure.json"
        if not target.exists():
            write_json(target, {"round": "R223", "status": "FAILED_NO_RETRY", "error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc(), "checks": CHECKS, "pin_records": PINS, "product_execution": False, "T2_complete": False})
        if not (OUT / "result.json").exists():
            write_json(OUT / "result.json", {"round": "R223", "command": "root_settlement", "exit_code": 1, "attempt": 1, "retry": 0, "test_execution": False, "product_commands": 0, "failure": pin(target), "T2_complete": False})
        print(json.dumps({"command": "root_settlement", "exit_code": 1, "result": str(OUT / "result.json")}, ensure_ascii=False))
        raise SystemExit(1)
