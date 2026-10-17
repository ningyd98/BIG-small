"""R196 one-shot source evidence; standard library only, no product imports."""
from pathlib import Path
import base64
import difflib
import hashlib
import json
import os
import signal
import sys

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round196-p6-t1-local-promotion-original-task-bindings-20261014"
PLAN_SHA = "c06e7433d113754a00438440e6c7777c2d4ba28236d228e886cc4dc1418a4338"
SHARED = ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py"
OLD_TEST = ROOT / "tests/test_operational_runtime_closure.py"
OLD_AUX = ROOT / "tests/test_local_temporal_projection_closure.py"
PINS158 = D.parent / "round158-p6-stage-b-local-temporal-publication-20261013/input-pins.json"


def timeout(signum, frame):
    raise TimeoutError("R196 metadata hard cap 120 seconds")


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


def archived(path):
    raw = Path(path).read_bytes()
    return {**pin(path), "base64": base64.b64encode(raw).decode()}


def write(path, value):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n").encode()
    with Path(path).open("xb") as stream:
        assert stream.write(raw) == len(raw)
    return pin(path)


def initial_inputs(plan, activation, phase):
    check(activation["before_manifest"])
    manifest = load(activation["before_manifest"]["path"])
    assert manifest["round"] == "R196" and manifest["initial_inputs"] == plan["inputs"]
    archives = {item["original"]["path"]: item for item in manifest["archives"]}
    assert len(archives) == len(manifest["archives"]) == 7
    current_metadata = {item["path"]: item for item in activation["controlled_metadata_after"]}
    assert set(current_metadata) == set(plan["input_roles"]["mutable_start_paths"])
    records = {item["path"]: item for item in plan["inputs"]}
    assert len(records) == len(plan["inputs"]) == 256
    for item in manifest["archives"]:
        assert item["original"] == records[item["original"]["path"]]
        check(item["archive"])
        assert (item["archive"]["bytes"], item["archive"]["sha256"]) == (
            item["original"]["bytes"], item["original"]["sha256"])
    for record in plan["inputs"]:
        path = record["path"]
        if path in current_metadata:
            assert path in archives
            check(current_metadata[path])
        elif path == str(SHARED) and phase == "green":
            assert path in archives
        else:
            check(record)
    return manifest, archives


def bounded_product(before, after):
    """Unique full function starts and one exact branch; no AST/substring FIELDS guard."""
    function_markers = (b"\ndef _join_audit_original(", b"\ndef _bootstrap_promotion_source(")
    segments = []
    masked = []
    for raw in (before, after):
        ranges = []
        for marker in function_markers:
            assert raw.count(marker) == 1
            start = raw.index(marker)
            end = raw.index(b"\n\ndef ", start + len(marker))
            signature_end = raw.index(b":\n", start) + 2
            ranges.append((start, end, raw[start:signature_end]))
        start_marker = b'    if tag == "visual.verification.route.local.v1":\n'
        end_marker = b'    if tag == "visual.verification.effect-completion.local.v1":\n'
        assert raw.count(start_marker) == raw.count(end_marker) == 1
        start, end = raw.index(start_marker), raw.index(end_marker)
        assert start < end
        ranges.append((start, end, start_marker))
        ranges.sort()
        assert all(left[1] <= right[0] for left, right in zip(ranges, ranges[1:]))
        parts = []
        cursor = 0
        for number, (start, end, signature) in enumerate(ranges):
            parts.extend((raw[cursor:start], b"\n<R196_REGION_" + str(number).encode() + b">\n"))
            cursor = end
        parts.append(raw[cursor:])
        masked.append(b"".join(parts))
        segments.append(ranges)
    assert masked[0] == masked[1]
    assert [item[2] for item in segments[0]] == [item[2] for item in segments[1]]
    assert before != after
    return [{"before_start": a[0], "before_end": a[1],
             "after_start": b[0], "after_end": b[1],
             "before_sha256": digest(before[a[0]:a[1]]),
             "after_sha256": digest(after[b[0]:b[1]])}
            for a, b in zip(segments[0], segments[1])]


def consume(plan, command, phase):
    gate_path = D / "script-gate.json"
    gate_raw = gate_path.read_bytes()
    gate = json.loads(gate_raw)["commands"][command["id"]]
    assert gate["state"] == "APPROVED"
    for key in ("argv", "cwd", "finite_env", "timeout_seconds", "child_finite_env"):
        assert gate[key] == command[key]
    assert gate["launcher_argv"] == command["argv"]
    assert gate["script_pin"]["path"] == str(Path(__file__).absolute())
    check(gate["script_pin"])
    mutable = {str(D / name) for name in (
        "script-gate.json", "command-ledger.json", "root-command-ledger.json", "root-activation.json")}
    assert not any(item["path"] in mutable for item in gate["input_records"])
    for item in gate["input_records"]:
        check(item)
    root_path, author_path = D / "root-command-ledger.json", D / "command-ledger.json"
    root_before, author_before = archived(root_path), archived(author_path)
    root, author = load(root_path), load(author_path)
    ids = {item["id"] for item in plan["commands"]}
    assert set(root["commands"]) == set(author["commands"]) == ids and len(ids) == 6
    assert root["schema_version"] == author["schema_version"] == "bigsmall.r196.command-ledger.v1"
    root_slot, slot = root["commands"][command["id"]], author["commands"][command["id"]]
    assert (root_slot["state"], root_slot["authorized"], root_slot["used"], root_slot["remaining"]) == (
        "RESERVED_BY_ROOT", 1, 1, 0)
    assert root_slot["reservation_id"] == gate["reservation_id"]
    assert root_slot["gate_pin"] == pin(gate_path)
    assert (slot["state"], slot["authorized"], slot["used"], slot["remaining"]) == (
        "HELD_PENDING_ROOT_GATE", 1, 0, 1)
    for item in (slot, root_slot):
        for key in ("argv", "cwd", "finite_env", "timeout_seconds", "child_finite_env"):
            assert item[key] == command[key]
    evidence = Path(command["evidence_dir"])
    evidence.mkdir(parents=True, exist_ok=False)
    scripts = [pin(path) for path in plan["scope"]["author_scripts"] + [plan["scope"]["root_script"]]]
    assert all(item in gate["input_records"] for item in scripts)
    invocation = write(evidence / "invocation.json", {
        "round": "R196", "command": command["id"], "phase": phase,
        "argv": command["argv"], "cwd": str(ROOT), "finite_env": command["finite_env"],
        "timeout_seconds": 120, "hard_cap": "SIGALRM", "attempt": 1, "retry": 0,
        "reservation_id": gate["reservation_id"], "script_pins": scripts,
        "author_ledger_before": author_before, "root_ledger_before": root_before,
        "gate_before": {**pin(gate_path), "base64": base64.b64encode(gate_raw).decode()},
        "activation_before": archived(D / "root-activation.json"), "outer_capture": gate["transport"]})
    # Full before generations are durable before the single author-slot mutation.
    assert pin(author_path) == {key: author_before[key] for key in ("path", "bytes", "sha256")}
    slot.update(used=1, remaining=0, state="SPENT_BEFORE_ACTION", attempts=1, retry=0,
                reservation_id=gate["reservation_id"])
    author_path.write_text(json.dumps(author, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return gate, evidence, invocation


def main():
    assert len(sys.argv) == 2 and sys.argv[1] in {"red", "green"}
    phase = sys.argv[1]
    raw_plan = (D / "plan.json").read_bytes()
    assert digest(raw_plan) == PLAN_SHA
    plan = json.loads(raw_plan)
    command = next(item for item in plan["commands"] if item["id"] == "prepare_" + phase)
    assert [sys.executable, str(Path(__file__).absolute()), phase] == command["argv"]
    assert Path.cwd() == ROOT and dict(os.environ) == command["finite_env"]
    assert command["timeout_seconds"] == 120 and command["child_finite_env"] is None
    activation = load(D / "root-activation.json")
    manifest, archives = initial_inputs(plan, activation, phase)
    before = Path(archives[str(SHARED)]["archive"]["path"]).read_bytes()
    after = SHARED.read_bytes()
    assert len(before) == 111212 and digest(before) == "f01520073140a08b0e15b947a00c840f486d45bd7dcc434bf44a894b6aae591c"
    regions = [] if phase == "red" else bounded_product(before, after)
    if phase == "red":
        assert before == after
    origin_pins = load(PINS158)
    paths = [item["path"] for item in origin_pins["owned_existing"] + origin_pins["owned_new"]]
    paths += [str(OLD_AUX), plan["scope"]["new_test"]]
    assert len(paths) == len(set(paths)) == 26
    records = {item["path"]: item for item in plan["inputs"]}
    protected = [records[path] for path in plan["input_roles"]["protected_paths"]]
    assert len(protected) == len({item["path"] for item in protected}) == 211
    sources = [archived(path) for path in paths]
    for item in sources:
        if item["path"] not in (str(SHARED), plan["scope"]["new_test"]):
            check(records[item["path"]])
    if phase == "green":
        red = load(D / "implementation/prepare_red/candidate-snapshot.json")
        assert len(red["sources"]) == 26 and red["protected"] == protected
        for item in red["sources"]:
            raw = base64.b64decode(item["base64"], validate=True)
            assert (len(raw), digest(raw)) == (item["bytes"], item["sha256"])
            if item["path"] != str(SHARED):
                assert Path(item["path"]).read_bytes() == raw
        invocation = load(D / "implementation/prepare_red/invocation.json")
        for item in invocation["script_pins"]:
            check(item)
    tests = plan["tests"]
    assert len(tests["red_nodes"]) == tests["red_count"] == 8
    assert len(tests["green_nodes"]) == len(set(tests["green_nodes"])) == tests["green_count"] == 63
    assert len(tests["existing_green_nodes"]) == tests["existing_green_count"] == 51
    assert tests["new_count"] == 12 and tests["green_nodes"][:51] == tests["existing_green_nodes"]
    gate, evidence, invocation = consume(plan, command, phase)
    outputs = [invocation]
    outputs.append(write(evidence / "candidate-snapshot.json", {
        "round": "R196", "phase": phase, "sources": sources, "protected": protected,
        "baseline": activation["before_manifest"], "initial_shared": archives[str(SHARED)]["archive"]}))
    outputs.append(write(evidence / "scope-proof.json", {
        "round": "R196", "status": "SOURCE_ONLY", "phase": phase, "owned_count": 26,
        "prior_owned_count": 25, "other24_unchanged": True, "protected_count": 211,
        "both_old_test_files_whole_preserved": True, "new_test_pin": pin(plan["scope"]["new_test"]),
        "before_shared": archives[str(SHARED)]["archive"], "after_shared": pin(SHARED),
        "permitted_product_regions": regions, "initial_input_count": 256,
        "controlled_metadata_after": activation["controlled_metadata_after"],
        "test_execution": False, "product_commands": 0}))
    outputs.append(write(evidence / "fixture-map.json", {
        "round": "R196", "red_nodes": tests["red_nodes"], "green_nodes": tests["green_nodes"],
        "new_helper_calls": plan["resources"]["new_helper_calls"],
        "old_helper_calls": plan["resources"]["old_helper_calls"],
        "case_directory": "red8/cases or green63/cases; old cases retained in temp_index",
        "allocation_denominator": "Actual real R175 object/init/close sidecars only",
        "unobserved_worker_broker_OS_native_model_network_counts": None,
        "old_GREEN51": "Historical f015 candidate only", "tests_executed": False}))
    outputs.append(write(evidence / "change-report.json", {
        "round": "R196", "phase": phase, "before": archives[str(SHARED)]["archive"],
        "after": pin(SHARED), "scope": plan["scope"],
        "source_pins": [{k: v for k, v in item.items() if k != "base64"} for item in sources],
        "metadata_generations": "Exact full invocation before archives, never current-pin exceptions",
        "old_slots_reset": False, "product_commands": 0}))
    path = evidence / "limited.diff"
    with path.open("xb") as stream:
        stream.write("".join(difflib.unified_diff(before.decode().splitlines(True),
                     after.decode().splitlines(True), fromfile=str(SHARED) + ".R196-before",
                     tofile=str(SHARED))).encode())
    outputs.append(pin(path))
    initial_inputs(plan, activation, phase)
    for item in gate["input_records"] + sources + protected + outputs:
        check(item)
    result = {"round": "R196", "command": command["id"], "exit_code": 0,
              "attempt": 1, "retry": 0, "test_execution": False, "product_commands": 0,
              "outputs": outputs, "input_records": gate["input_records"],
              "candidate": pin(evidence / "candidate-snapshot.json"), "T1_complete": False,
              "independent_outer_capture": gate["transport"]}
    result_pin = write(evidence / "result.json", result)
    signal.alarm(0)
    print(json.dumps({"command": command["id"], "result": result_pin, "outputs": len(outputs),
                      "product_commands": 0}))


if __name__ == "__main__":
    main()

