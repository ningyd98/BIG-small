"""R179 gated metadata freeze; stdlib only, never imports product modules."""
from pathlib import Path
import base64
import difflib
import hashlib
import json
import os
import signal
import sys
import tokenize

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round179-p6-t1-detached-causality-hash-audit-20261014"
PLAN_SHA = "dc0cae1b743d6244469625e3f9a4fd14200efbb3e3669c422f1639f59b4be05e"
TEST = ROOT / "tests/test_operational_runtime_closure.py"
BASELINE = D / "implementation/before/baseline-r175-snapshot.json"


def timeout(signum, frame):
    raise TimeoutError("R179 metadata hard limit 120 seconds")


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


def write(path, value):
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                          allow_nan=False) + "\n").encode()
    with Path(path).open("xb") as stream:
        stream.write(encoded)
    return pin(path)


def load(path):
    return json.loads(Path(path).read_bytes())


def consume(command):
    gate = load(D / "script-gate.json")["commands"][command["id"]]
    assert gate["state"] == "APPROVED"
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert gate[key] == command[key]
    assert gate["launcher_argv"] == [sys.executable, str(Path(__file__).absolute()), sys.argv[1]]
    check(gate["script_pin"])
    assert gate["script_pin"]["path"] == str(Path(__file__).absolute())
    mutable = {str(D / name) for name in ("script-gate.json", "command-ledger.json",
                                        "root-command-ledger.json", "root-activation.json")}
    assert all(record["path"] not in mutable for record in gate["input_records"])
    for record in gate["input_records"]:
        check(record)
    root_slot = load(D / "root-command-ledger.json")["commands"][command["id"]]
    assert (root_slot["authorized"], root_slot["used"], root_slot["remaining"],
            root_slot["state"]) == (1, 1, 0, "RESERVED_BY_ROOT")
    assert root_slot["reservation_id"] == gate["reservation_id"]
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert root_slot[key] == command[key]
    path = D / "command-ledger.json"
    author = load(path)
    slot = author["commands"][command["id"]]
    assert (slot["authorized"], slot["used"], slot["remaining"], slot["state"]) == (1, 0, 1, "HELD")
    for key in ("argv", "cwd", "finite_env", "timeout_seconds"):
        assert slot[key] == command[key]
    before = path.read_bytes()
    slot.update(used=1, remaining=0, state="SPENT_BEFORE_ACTION",
                reservation_id=gate["reservation_id"], attempts=1, retries=0)
    assert path.read_bytes() == before
    path.write_text(json.dumps(author, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return gate, {"bytes": len(before), "sha256": digest(before),
                  "base64": base64.b64encode(before).decode()}


def pair_scope(before, after, start, end):
    assert before.count(start) == after.count(start) == 1
    assert before.count(end) == after.count(end) == 1
    bp, tail = before.split(start, 1)
    _, bs = tail.split(end, 1)
    ap, tail = after.split(start, 1)
    _, ass = tail.split(end, 1)
    assert bp == ap and bs == ass
    return {"prefix_sha256": digest(bp), "suffix_sha256": digest(bs)}


def main():
    assert len(sys.argv) == 2 and sys.argv[1] in {"red", "green"}
    phase = sys.argv[1]
    plan_bytes = (D / "plan.json").read_bytes()
    assert digest(plan_bytes) == PLAN_SHA
    plan = json.loads(plan_bytes)
    command = next(item for item in plan["commands"] if item["id"] == "prepare_" + phase)
    assert Path.cwd() == ROOT and command["timeout_seconds"] == 120
    assert [sys.executable, str(Path(__file__).absolute()), phase] == command["argv"]
    assert all(os.environ.get(key) == value for key, value in command["finite_env"].items())
    gate, ledger_before = consume(command)
    evidence = Path(command["evidence_dir"])
    evidence.mkdir(parents=True, exist_ok=False)
    outputs = [write(evidence / "invocation.json", {
        "argv": command["argv"], "cwd": str(ROOT), "finite_env": command["finite_env"],
        "timeout_seconds": 120, "hard_cap": "SIGALRM", "attempt": 1, "retry": 0,
        "script_pin": pin(Path(__file__).absolute()), "reservation_id": gate["reservation_id"],
        "author_ledger_before": ledger_before,
        "outer_capture": gate["transport"], "independent_streams_in_tool": None,
    })]
    observation = load(D / "input-observation.json")
    baseline = load(BASELINE)
    assert len(baseline["sources"]) == 24 and len(baseline["protected"]) == 211
    before = {}
    for item in baseline["sources"]:
        raw = base64.b64decode(item["base64"], validate=True)
        assert len(raw) == item["bytes"] and digest(raw) == item["sha256"]
        before[item["path"]] = raw
    assert len(before) == 24
    current = {path: Path(path).read_bytes() for path in before}
    for record in baseline["protected"]:
        check(record)
    for record in observation["metadata_inputs"]:
        check(record)
    allowed = set(plan["scope"]["owned_paths"])
    assert len(allowed) == 3 and str(TEST) in allowed
    for path, raw in current.items():
        if path not in allowed or phase == "red" and path != str(TEST):
            assert raw == before[path], "unallowed source delta"
    assert len([path for path in current if path not in allowed]) == 21
    original_test = before[str(TEST)]
    assert digest(original_test[:80556]) == observation["A_prefix"]["sha256"]
    assert current[str(TEST)][:80556] == original_test[:80556]
    marker = b"\n\n# R179 caller-created detached audit regressions;"
    assert current[str(TEST)].count(marker) == 1
    old_part, appended = current[str(TEST)].split(marker)
    if phase == "red":
        assert current[str(TEST)][:len(original_test)] == original_test
        assert old_part == original_test
    else:
        prefix_proof = pair_scope(original_test, old_part,
            b"def _b_local_cases(", b"def _b_decode_domain(")
        red = load(D / "implementation/prepare_red/candidate-snapshot.json")
        red_test = next(item for item in red["sources"] if item["path"] == str(TEST))
        red_raw = base64.b64decode(red_test["base64"], validate=True)
        assert current[str(TEST)].split(marker)[1] == red_raw.split(marker)[1]
        verifier = str(ROOT / "src/cloud_edge_robot_arm/repositories/event_autonomy/visual_verification.py")
        local_class = b"class LocalVisualVerificationRouteInput("
        bp, bl = before[verifier].split(local_class, 1)
        ap, al = current[verifier].split(local_class, 1)
        assert bp == ap
        pair_scope(bl, al, b"    def source_key(", b"    def online(")
        shared = str(ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py")
        constants_start, constants_end = b"FIELDS:", b"\n\ndef _copy("
        constants_before = before[shared].split(constants_start, 1)[1].split(constants_end, 1)[0]
        constants_after = current[shared].split(constants_start, 1)[1].split(constants_end, 1)[0]
        assert constants_before == constants_after
        for start, end in ((b"def _copy(", b"def _object("),
                           (b"def _canonical(", b"def _hash(")):
            old = before[shared].split(start, 1)[1].split(end, 1)[0]
            new = current[shared].split(start, 1)[1].split(end, 1)[0]
            assert old == new
    lines = current[str(TEST)].splitlines(keepends=True)
    for item in observation["protected_test_regions"].values():
        raw = b"".join(lines[item["start_line"] - 1:item["end_line"]])
        # Green bookkeeping may shift later source lines; old prefix/suffix proof
        # remains authoritative for every existing definition outside that helper.
        if phase == "red" or item["end_line"] <= 2456:
            assert len(raw) == item["bytes"] and digest(raw) == item["sha256"]
    for role in baseline["parent_ledger_pins"]:
        check(role)
        commands = load(role["path"])["commands"]
        assert len(commands) == 15
        assert sum(item["used"] for item in commands.values()) == 3
        assert sum(item["remaining"] for item in commands.values()) == 12
    for key in ("original_23_before_preserved", "real_R166_golden", "golden_provenance", "runner"):
        check(baseline["checks"][key])
    sources = []
    diffs = []
    for path, raw in current.items():
        sources.append({**pin(path), "base64": base64.b64encode(raw).decode(),
                        "before_bytes": len(before[path]), "before_sha256": digest(before[path])})
        diffs.extend(difflib.unified_diff(before[path].decode().splitlines(True),
                     raw.decode().splitlines(True), fromfile=path + ".R175", tofile=path))
    declared_names = {node.split("::", 1)[1].split("[", 1)[0]
                      for node in plan["tests"]["green_nodes"]}
    source_text = current[str(TEST)].decode()
    assert all("def " + name + "(" in source_text for name in declared_names)
    # tokenize checks source regions/data without importing, compiling or collecting.
    with tokenize.open(TEST) as stream:
        token_count = sum(1 for _ in tokenize.generate_tokens(stream.readline))
    proof = {"round": "R179", "phase": phase, "status": "SOURCE_ONLY_UNEXECUTED_TESTS",
             "owned_count": 24, "other_owned_unchanged": 21, "protected_count": 211,
             "old_test_prefix_preserved": phase == "red", "A80556_preserved": True,
             "old_test_regions": observation["protected_test_regions"],
             "source_tokens_read": token_count, "declared_red_nodes": plan["tests"]["red_nodes"],
             "declared_green_nodes": plan["tests"]["green_nodes"],
             "tests_collected_or_run": False, "runtime_authority_claim": False}
    fixture = {"round": "R179", "phase": phase, "new_nodes": plan["tests"]["new_nodes"],
               "red_seed_contract": plan["tests"]["red_rules"],
               "baseline_decode_observed": False, "new_helper_calls_per_node_max": 1,
               "Memory_lifecycle": "Unchanged R175 actual observer; count emitted sidecars.",
               "OC1": "Existing _b_detached_original finally closes its two original clocks.",
               "worker_broker_OS_counts": None, "resource_contract": plan["resource_contract"],
               "history_positive": ["definition-zero -> reserve capture -> complete capture",
                                    "definition-zero -> reserve wait -> complete wait"]}
    outputs.append(write(evidence / "candidate-snapshot.json",
                         {"round": "R179", "phase": phase, "sources": sources,
                          "protected": baseline["protected"], "baseline": pin(BASELINE)}))
    outputs.append(write(evidence / "source-scope-proof.json", proof))
    outputs.append(write(evidence / "fixture-map.json", fixture))
    outputs.append(write(evidence / "change-report.json",
                         {"round": "R179", "phase": phase, "sources": [
                             {key: value for key, value in item.items() if key != "base64"}
                             for item in sources], "scope": plan["scope"]}))
    diff_path = evidence / "limited.diff"
    with diff_path.open("xb") as stream:
        stream.write("".join(diffs).encode())
    outputs.append(pin(diff_path))
    for record in gate["input_records"]:
        check(record)
    for path, raw in current.items():
        assert Path(path).read_bytes() == raw
    for record in baseline["protected"]:
        check(record)
    for record in outputs:
        check(record)
    result = {"round": "R179", "command": command["id"], "exit_code": 0,
              "attempt": 1, "retry": 0, "outputs": outputs, "status": "SOURCE_ONLY",
              "product_commands": 0, "test_execution": False, "T1_complete": False,
              "independent_outer_capture": gate["transport"]}
    result_pin = write(evidence / "result.json", result)
    signal.alarm(0)
    print(json.dumps({"command": command["id"], "result": result_pin,
                      "outputs": len(outputs), "product_commands": 0}))


if __name__ == "__main__":
    main()
