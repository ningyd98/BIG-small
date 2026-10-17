"""R192 one-shot source/provenance preparation; standard library only."""
from pathlib import Path
import base64
import difflib
import hashlib
import json
import os
import signal
import sys

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round192-p6-t1-original-green38-unexpected-outcome-20261014"
PLAN_SHA = "5f47ed17d70a2f14008aa6b277ec83f719836ede1b555252d6014e41fbb1a8aa"
SHARED = ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py"
P182 = D.parent / "round182-p6-t1-recursive-local-projection-closure-20261014"


def timeout(signum, frame):
    raise TimeoutError("R192 prepare hard limit 120 seconds")


signal.signal(signal.SIGALRM, timeout)
signal.alarm(120)


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
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n").encode()
    with Path(path).open("xb") as stream:
        assert stream.write(raw) == len(raw)
    return pin(path)


def initial_inputs(plan, activation):
    transitions = {item["before"]["original"]["path"]: item
                   for item in activation["parent_ledger_transitions"]}
    assert set(transitions) == set(plan["input_roles"]["authorized_mutable_parent_ledgers"])
    assert len(transitions) == 4 and len(plan["inputs"]) == 268
    historical = []
    for record in plan["inputs"]:
        path = record["path"]
        if path == str(SHARED):
            archive = activation["before_shared"]
            check(archive)
            assert (record["bytes"], record["sha256"]) == (archive["bytes"], archive["sha256"])
        elif path in transitions:
            item = transitions[path]
            assert item["before"]["original"] == record
            check(item["before"]["archive"])
            assert (item["before"]["archive"]["bytes"], item["before"]["archive"]["sha256"]) == (
                record["bytes"], record["sha256"])
            check(item["current_after"])
            assert item["current_after"]["path"] == path
            before = load(item["before"]["archive"]["path"])
            after = load(path)
            assert set(before["commands"]) == set(after["commands"])
            for key, slot in after["commands"].items():
                if key == "root_settlement":
                    assert (slot["state"], slot["used"], slot["remaining"], slot["executable"]) == (
                        "HELD_SUPERSEDED_R192", 0, 1, False)
                elif key == "green" and "round179-" in path and Path(path).name == "root-command-ledger.json":
                    assert slot["used"] == 1 and slot["remaining"] == 0
                    assert slot["state"].startswith("SPENT")
                else:
                    assert slot == before["commands"][key]
            historical.append(item)
        else:
            check(record)
    return historical


def consume(plan, command):
    gate = load(D / "script-gate.json")["commands"]["prepare"]
    assert gate["state"] == "APPROVED"
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert gate[key] == command[key]
    assert gate["launcher_argv"] == command["argv"]
    assert gate["script_pin"]["path"] == str(Path(__file__).absolute())
    check(gate["script_pin"])
    mutable = {str(D / name) for name in
               ("script-gate.json", "command-ledger.json", "root-command-ledger.json", "root-activation.json")}
    assert not any(record["path"] in mutable for record in gate["input_records"])
    for record in gate["input_records"]:
        check(record)
    root_raw = (D / "root-command-ledger.json").read_bytes()
    root_slot = json.loads(root_raw)["commands"]["prepare"]
    assert (root_slot["state"], root_slot["authorized"], root_slot["used"], root_slot["remaining"]) == (
        "RESERVED_BY_ROOT", 1, 1, 0)
    assert root_slot["reservation_id"] == gate["reservation_id"]
    assert root_slot["gate_pin"] == pin(D / "script-gate.json")
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert root_slot[key] == command[key]
    path = D / "command-ledger.json"
    before = path.read_bytes()
    author = json.loads(before)
    slot = author["commands"]["prepare"]
    assert (slot["state"], slot["authorized"], slot["used"], slot["remaining"]) == (
        "HELD_PENDING_ROOT_GATE", 1, 0, 1)
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert slot[key] == command[key]
    slot.update(state="SPENT_BEFORE_ACTION", used=1, remaining=0,
                attempts=1, retry=0, reservation_id=gate["reservation_id"])
    assert path.read_bytes() == before
    path.write_text(json.dumps(author, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return gate, {"bytes": len(before), "sha256": digest(before),
                  "base64": base64.b64encode(before).decode()}, {
                      "bytes": len(root_raw), "sha256": digest(root_raw),
                      "base64": base64.b64encode(root_raw).decode()}


def main():
    raw_plan = (D / "plan.json").read_bytes()
    assert digest(raw_plan) == PLAN_SHA
    plan = json.loads(raw_plan)
    command = next(item for item in plan["commands"] if item["id"] == "prepare")
    assert [sys.executable, str(Path(__file__).absolute())] == command["argv"]
    assert len(sys.argv) == 1 and Path.cwd() == ROOT
    assert dict(os.environ) == command["finite_env"] and command["timeout_seconds"] == 120
    activation = load(D / "root-activation.json")
    check(activation["before_metadata"])
    history = initial_inputs(plan, activation)
    before = Path(activation["before_shared"]["path"]).read_bytes()
    assert len(before) == 111096 and digest(before) == "63ec55b0e3d4b45fe68f2890ab4eb9e2714f52d572eeee70a6efbecaebd53cd8"
    anchor = b'        retry_task = retry_envelope.string("task_id")\n    else:\n'
    replacement = (b'        retry_task = retry_envelope.string("task_id")\n'
                   b'    elif "schema_version" in retry_raw:\n'
                   b'        raise ValueError("unsupported publication retry budget schema/tag")\n'
                   b'    else:\n')
    assert before.count(anchor) == 1
    after = SHARED.read_bytes()
    assert after == before.replace(anchor, replacement, 1)
    snapshot_path = P182 / "implementation/prepare_green/candidate-snapshot.json"
    baseline = load(snapshot_path)
    assert len(baseline["sources"]) == 25 and len(baseline["protected"]) == 211
    sources = []
    for record in baseline["sources"]:
        raw = base64.b64decode(record["base64"], validate=True)
        assert len(raw) == record["bytes"] and digest(raw) == record["sha256"]
        current = Path(record["path"]).read_bytes()
        assert current == (after if record["path"] == str(SHARED) else raw)
        sources.append({**pin(record["path"]), "base64": base64.b64encode(current).decode(),
                        "before_bytes": len(raw), "before_sha256": digest(raw)})
    for record in baseline["protected"]:
        check(record)
    tests = plan["tests"]
    assert tests["green_nodes"] == tests["old_green38_nodes"] + tests["old_green13_nodes"]
    assert len(tests["old_green38_nodes"]) == 38 and len(tests["old_green13_nodes"]) == 13
    assert len(tests["green_nodes"]) == len(set(tests["green_nodes"])) == 51
    green = next(item for item in plan["commands"] if item["id"] == "green51")
    assert [arg for arg in green["argv"] if "::" in arg] == tests["green_nodes"]
    assert plan["resources"]["helper_calls_by_node"] == {node: 1 for node in tests["green_nodes"]}
    gate, author_before, root_before = consume(plan, command)
    for item in history:
        assert item["current_after"] in gate["input_records"]
        assert item["before"]["archive"] in gate["input_records"]
    evidence = Path(command["evidence_dir"])
    evidence.mkdir(parents=True, exist_ok=False)
    outputs = [write(evidence / "invocation.json", {
        "round": "R192", "command": "prepare", "argv": command["argv"], "cwd": str(ROOT),
        "finite_env": command["finite_env"], "timeout_seconds": 120, "hard_cap": "SIGALRM",
        "attempt": 1, "retry": 0, "script_pin": pin(Path(__file__).absolute()),
        "reservation_id": gate["reservation_id"], "author_ledger_before": author_before,
        "root_ledger_before": root_before, "outer_capture": gate["transport"]})]
    outputs.append(write(evidence / "candidate-snapshot.json", {
        "round": "R192", "phase": "final", "sources": sources,
        "protected": baseline["protected"], "baseline": pin(snapshot_path)}))
    outputs.append(write(evidence / "scope-proof.json", {
        "round": "R192", "status": "SOURCE_ONLY", "owned_count": 25, "other24_unchanged": True,
        "protected_count": 211, "both_test_files_whole_preserved": True,
        "exact_presence_based_dispatch_insertion_only": True,
        "before_shared": activation["before_shared"], "after_shared": pin(SHARED),
        "parent_ledger_transitions": history, "initial_input_count": 268,
        "green_node_count": 51, "tests_executed": False, "product_commands": 0}))
    outputs.append(write(evidence / "fixture-map.json", {
        "round": "R192", "green_nodes": tests["green_nodes"],
        "helper_calls_by_node": plan["resources"]["helper_calls_by_node"],
        "allocation_denominator": "Actual R175 sidecars only, never a fixed per-node object count.",
        "worker_broker_OS_native_model_network_counts": None,
        "old_failed_GREEN38": "37PASS/1FAIL retained, never rewritten",
        "old_GREEN13": "13PASS on old63ec candidate only", "new_GREEN51_executed": False}))
    outputs.append(write(evidence / "change-report.json", {
        "round": "R192", "before": activation["before_shared"], "after": pin(SHARED),
        "source_pins": [{key: value for key, value in item.items() if key != "base64"} for item in sources],
        "scope": plan["scope"], "old_slots_reset": False, "product_commands": 0}))
    diff_path = evidence / "limited.diff"
    with diff_path.open("xb") as stream:
        stream.write("".join(difflib.unified_diff(before.decode().splitlines(True),
                     after.decode().splitlines(True), fromfile=str(SHARED) + ".R192-before",
                     tofile=str(SHARED))).encode())
    outputs.append(pin(diff_path))
    initial_inputs(plan, activation)
    for record in gate["input_records"] + baseline["protected"] + outputs:
        check(record)
    for item in sources:
        check(item)
    result = {"round": "R192", "command": "prepare", "exit_code": 0, "attempt": 1, "retry": 0,
              "test_execution": False, "product_commands": 0, "outputs": outputs,
              "T1_complete": False, "independent_outer_capture": gate["transport"]}
    result_pin = write(evidence / "result.json", result)
    signal.alarm(0)
    print(json.dumps({"command": "prepare", "result": result_pin, "outputs": len(outputs),
                      "product_commands": 0}))


if __name__ == "__main__":
    main()

