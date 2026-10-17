from pathlib import Path
import json
import hashlib
import difflib

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
PLAN_PATH = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round167-p6-root-held-ledger-schema-recovery-20261013/plan.json"
plan = json.loads(PLAN_PATH.read_text())
assert type(plan) is dict and plan["round"] == "R167"
assert type(plan["inputs"]) is list and len(plan["inputs"]) == 26

def pin(name):
    path = Path(name)
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

def check(record, require_relative=False):
    assert type(record) is dict
    assert type(record["path"]) is str and Path(record["path"]).is_absolute()
    assert type(record["bytes"]) is int and record["bytes"] >= 0
    assert type(record["sha256"]) is str and len(record["sha256"]) == 64
    assert all(char in "0123456789abcdef" for char in record["sha256"])
    if require_relative:
        assert {"path", "relative_path", "bytes", "sha256"} <= set(record)
        assert type(record["relative_path"]) is str
    actual = pin(record["path"])
    assert actual["bytes"] == record["bytes"] and actual["sha256"] == record["sha256"], record["path"]
    return actual

inputs = [check(record) for record in plan["inputs"]]
assert len({record["path"] for record in inputs}) == 26
control_plan_path = plan["inputs"][2]["path"]
control_plan = json.loads(Path(control_plan_path).read_text())
assert type(control_plan) is dict and control_plan["round"] == "R166"
scope = control_plan["scope"]
outputs = control_plan["outputs"]
old_test = Path(outputs["before_test"]).read_bytes()
new_test = Path(scope["test_path"]).read_bytes()
old_runner = Path(outputs["before_runner"]).read_bytes()
new_runner = Path(scope["runner_path"]).read_bytes()
test_delta = scope["exact_test_delta"]
runner_delta = scope["exact_runner_delta"]
assert test_delta["occurrences"] == 1 and old_test.count(test_delta["before"].encode()) == 1
assert new_test == old_test.replace(test_delta["before"].encode(), test_delta["after"].encode(), 1)
assert runner_delta["occurrences"] == 1 and old_runner.count(runner_delta["before"].encode()) == 1
assert new_runner == old_runner.replace(runner_delta["before"].encode(), runner_delta["after"].encode(), 1)
start = old_test.index(b"def _b_legacy_sources(")
end = old_test.index(b"\ndef _b_fields()", start)
assert start < old_test.index(test_delta["before"].encode()) < end
assert old_test[:80556] == new_test[:80556]
assert hashlib.sha256(new_test[:80556]).hexdigest() == "c1a68fe0b5ff88bdf604e4859a17da73f61f56b1fd934897f0e66a484d9ae861"

manifest_record = plan["inputs"][18]
manifest = json.loads(Path(manifest_record["path"]).read_text())
assert type(manifest) is dict
assert type(manifest["owned_existing"]) is list and type(manifest["protected"]) is list
test_path = scope["test_path"]
production = [record for record in manifest["owned_existing"] if record["path"] != test_path]
assert len(production) == 22 and all(record["relative_path"].startswith("src/") for record in production)
assert len(manifest["protected"]) == 211
production_checks = [check(record, True) for record in production]
protected_checks = [check(record, True) for record in manifest["protected"]]

parent_ledgers = {}
for role, record in (("author", plan["inputs"][19]), ("ROOT", plan["inputs"][20])):
    ledger = json.loads(Path(record["path"]).read_text())
    assert type(ledger) is dict and type(ledger["commands"]) is dict and len(ledger["commands"]) == 15
    usage = {}
    for name, command in ledger["commands"].items():
        assert type(command) is dict
        assert type(command["authorized"]) is int and command["authorized"] == 1
        assert type(command["used"]) is int and type(command["remaining"]) is int
        expected = (1, 0) if name in {"mypy_baseline", "t1_red"} else (0, 1)
        assert (command["used"], command["remaining"]) == expected
        assert type(command["state"]) is str and command["state"]
        usage[name] = {"used": command["used"], "remaining": command["remaining"], "state": command["state"]}
    assert {"mypy_baseline", "t1_red"} <= set(usage)
    assert sum(value["used"] for value in usage.values()) == 2
    assert sum(value["remaining"] for value in usage.values()) == 13
    parent_ledgers[role] = {"pin": record, "used": 2, "remaining": 13, "commands": usage}

guard = plan["check_contract"]["ledger_guard"]
author = json.loads(Path(outputs["author_ledger"]).read_text())
root_ledger = json.loads(Path(outputs["root_ledger"]).read_text())
assert type(author) is dict and author["schema_version"] == guard["author_schema_version"]
assert author["round"] == "R166" and type(author["commands"]) is dict
assert type(root_ledger) is dict and type(root_ledger["commands"]) is dict
for key, expected in guard["root_required_top_level"].items():
    assert type(root_ledger[key]) is type(expected) and root_ledger[key] == expected
assert list(author["commands"]) == list(root_ledger["commands"]) == ["legacy_control"]
for role, ledger, expected_state in (
    ("author", author, guard["author_slot"]["state"]),
    ("ROOT", root_ledger, guard["root_slot"]["state"]),
):
    expected_command = dict(control_plan["commands"]["legacy_control"])
    expected_command["state"] = expected_state
    actual_command = ledger["commands"]["legacy_control"]
    assert type(actual_command) is dict and actual_command == expected_command, role
    for key in ("authorized", "used", "remaining"):
        assert type(actual_command[key]) is int
    assert actual_command["authorized"] == 1 and actual_command["used"] == 0 and actual_command["remaining"] == 1
role_states = {"author": author["commands"]["legacy_control"]["state"], "ROOT": root_ledger["commands"]["legacy_control"]["state"]}

original_records = {record["path"]: record for record in control_plan["inputs"]}
for before in outputs["before_reports"]:
    actual = pin(before["snapshot"])
    original = original_records[before["source"]]
    assert actual["bytes"] == original["bytes"] and actual["sha256"] == original["sha256"]
mutable = {scope["test_path"], scope["runner_path"], *scope["metadata_reports"]}
original_immutable_checks = [check(record) for record in control_plan["inputs"] if record["path"] not in mutable]
assert not (ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py").exists()
assert not Path(control_plan["golden_contract"]["path"]).exists()
parent_directory = Path(original_records[plan["inputs"][19]["path"]]["path"]).parent
assert not (parent_directory / "implementation/t1_red/legacy-goldens.json").exists()
assert not Path(control_plan["commands"]["legacy_control"]["evidence_dir"]).exists()
assert not Path("/tmp/bigsmall-p6-r166-legacy-control").exists()
targets = [plan["outputs"]["change_report"], plan["outputs"]["limited_diff"], plan["outputs"]["verification"]]
assert len(set(targets)) == 3 and all(not Path(name).exists() for name in targets)

change = {
    "round": "R166", "producer_round": "R167",
    "status": "PREPARATION_SOURCE_DELTA_ONLY_PENDING_ROOT_CONTROL_GATE",
    "exact_test_literal_replacements": 1, "exact_parent_runner_path_replacements": 1,
    "before": {"test": pin(outputs["before_test"]), "parent_runner": pin(outputs["before_runner"])},
    "after": {"test": pin(scope["test_path"]), "parent_runner": pin(scope["runner_path"])},
    "A_prefix_unchanged": True, "A_prefix_bytes": 80556,
    "all_remaining_test_bytes_unchanged": True, "all_test_bodies_unchanged": True,
    "parent_runner_all_remaining_bytes_unchanged": True,
    "production_unchanged": len(production_checks), "protected_unchanged": len(protected_checks),
    "current_input_pins_checked": len(inputs),
    "original_R166_immutable_input_pins_checked": len(original_immutable_checks),
    "role_states": role_states, "parent_ledgers": parent_ledgers,
    "R166_control_used": 0, "R166_control_remaining": 1,
    "both_golden_paths_absent": True, "new_module_absent": True,
    "control_evidence_and_basetemp_absent": True, "control_executed": False,
    "original_failure": plan["inputs"][0],
    "original_metadata_action": {"round": "R166", "used": 1, "remaining": 0, "actual_exit": 1},
    "recovery_metadata_action": {"round": "R167", "used": 1, "remaining": 0},
}
with Path(targets[0]).open("x", encoding="utf-8") as handle:
    json.dump(change, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
diff = "".join(difflib.unified_diff(old_test.decode().splitlines(keepends=True), new_test.decode().splitlines(keepends=True), fromfile="before-test.py", tofile=scope["test_path"]))
diff += "".join(difflib.unified_diff(old_runner.decode().splitlines(keepends=True), new_runner.decode().splitlines(keepends=True), fromfile="before-runner.py", tofile=scope["runner_path"]))
with Path(targets[1]).open("x", encoding="utf-8") as handle:
    handle.write(diff)
artifact_names = [scope["test_path"], scope["runner_path"], scope["new_runner"], outputs["author_ledger"], outputs["root_ledger"], targets[0], targets[1]] + scope["metadata_reports"]
verification = {
    "round": "R166", "producer_round": "R167", "status": "PREPARATION_ONLY_NO_CONTROL_RUN",
    "original_metadata_action": change["original_metadata_action"],
    "recovery_metadata_action": change["recovery_metadata_action"],
    "original_failure": plan["inputs"][0], "role_states": role_states,
    "R158_used": 2, "R158_remaining": 13, "R166_control_used": 0, "R166_control_remaining": 1,
    "product_commands": 0, "retries": 0, "change_report": pin(targets[0]),
    "artifact_pins": [pin(name) for name in artifact_names],
}
with Path(targets[2]).open("x", encoding="utf-8") as handle:
    json.dump(verification, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(json.dumps({"receipt": pin(targets[2]), "inputs": len(inputs), "production": 22, "protected": 211, "role_states": role_states, "parent_used": 2, "parent_remaining": 13, "control_executed": False}, ensure_ascii=False, separators=(",", ":")))
