"""R182 gated metadata freeze; stdlib only, never imports product modules."""
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
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014"
PLAN_SHA = "82100de3713beccb61ceeb0da87d40d3cbb6a4552890c6c72337d899fad96c5d"
TEST = ROOT / "tests/test_operational_runtime_closure.py"
BASELINE = D / "original-static-finding.json"
AUX = ROOT / "tests/test_local_temporal_projection_closure.py"
PARENT = D.parent / "round179-p6-t1-detached-causality-hash-audit-20261014"


def timeout(signum, frame):
    raise TimeoutError("R182 metadata hard limit 120 seconds")


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
    mutable.update(str(PARENT / name) for name in ("script-gate.json", "command-ledger.json",
                                                  "root-command-ledger.json", "root-activation.json"))
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


def fixed_inputs(plan, phase):
    for record in plan["inputs"]:
        if record["role"] == "activation_before_mutable":
            continue
        if phase == "green" and record["role"] == "source_before_authorized_edit":
            continue
        check(record)


def parent_roles():
    states = {}
    for name in ("command-ledger.json", "root-command-ledger.json"):
        commands = load(PARENT / name)["commands"]
        assert len(commands) == 6
        for key, slot in commands.items():
            assert slot["authorized"] == 1
            assert slot["used"] in (0, 1) and slot["remaining"] == 1 - slot["used"]
            if key in {"prepare_red", "red"}:
                assert slot["used"] == 1 and slot["remaining"] == 0
            elif slot["used"] == 0:
                expected = "HELD" if name == "command-ledger.json" else "HELD_PENDING_ROOT_GATE"
                assert slot["state"] == expected
            else:
                assert "SPENT" in slot["state"] or slot["state"] == "RESERVED_BY_ROOT"
        states[name] = {key: {field: slot[field] for field in
                            ("state", "authorized", "used", "remaining")} for key, slot in commands.items()}
    return states


def protected_shared(before, after):
    assert before.count(b"FIELDS:") == after.count(b"FIELDS:") == 1
    old = before.split(b"FIELDS:", 1)[1].split(b"\n\ndef _copy(", 1)[0]
    new = after.split(b"FIELDS:", 1)[1].split(b"\n\ndef _copy(", 1)[0]
    assert old == new
    for start, end in ((b"def _copy(", b"def _object("),
                       (b"def _canonical(", b"def _hash(")):
        assert before.count(start) == after.count(start) == 1
        assert before.split(start, 1)[1].split(end, 1)[0] == after.split(start, 1)[1].split(end, 1)[0]


def main():
    assert len(sys.argv) == 2 and sys.argv[1] in {"red", "green"}
    phase = sys.argv[1]
    raw_plan = (D / "plan.json").read_bytes()
    assert digest(raw_plan) == PLAN_SHA
    plan = json.loads(raw_plan)
    command = next(item for item in plan["commands"] if item["id"] == "prepare_" + phase)
    assert Path.cwd() == ROOT and command["timeout_seconds"] == 120
    assert [sys.executable, str(Path(__file__).absolute()), phase] == command["argv"]
    assert dict(os.environ) == command["finite_env"], "exact finite environment required"
    gate, ledger_before = consume(command)
    fixed_inputs(plan, phase)
    roles = parent_roles()
    original = load(PARENT / "implementation/before/baseline-r175-snapshot.json")
    for key in ("original_23_before_preserved", "real_R166_golden", "golden_provenance", "runner"):
        check(original["checks"][key])
    for record in original["parent_ledger_pins"]:
        check(record)
        slots = load(record["path"])["commands"]
        assert len(slots) == 15
        assert sum(slot["used"] for slot in slots.values()) == 3
        assert sum(slot["remaining"] for slot in slots.values()) == 12
    baseline = load(BASELINE)
    records = baseline["before_R179_draft_sources"]
    protected = baseline["protected211"]
    assert len(records) == 24 and len(protected) == 211
    before = {}
    for record in records:
        raw = base64.b64decode(record["base64"], validate=True)
        assert len(raw) == record["bytes"] and digest(raw) == record["sha256"]
        assert record["path"] not in before
        before[record["path"]] = raw
    current = {path: Path(path).read_bytes() for path in before}
    shared = str(ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py")
    assert shared in before and str(TEST) in before and str(AUX) not in before
    for path, raw in current.items():
        if phase == "red" or path != shared:
            assert raw == before[path], "source outside shared repair changed"
    assert digest(current[str(TEST)]) == plan["scope"]["original_test_sha256"]
    assert current[str(TEST)][:80556] == before[str(TEST)][:80556]
    for record in protected:
        check(record)
    auxiliary = AUX.read_bytes()
    contract = load(D / "script-gate.json")["preparation_proof_contract"][phase]
    assert contract["owned_count"] == 25 and contract["protected_count"] == 211
    check(contract["auxiliary_pin"])
    assert contract["auxiliary_pin"]["path"] == str(AUX)
    assert contract["baseline_pin"] == pin(BASELINE)
    if phase == "green":
        red = load(D / "implementation/prepare_red/candidate-snapshot.json")
        assert len(red["sources"]) == 25 and red["phase"] == "red"
        archived_aux = next(item for item in red["sources"] if item["path"] == str(AUX))
        red_aux = base64.b64decode(archived_aux["base64"], validate=True)
        assert len(red_aux) == archived_aux["bytes"] and digest(red_aux) == archived_aux["sha256"]
        assert auxiliary == red_aux
        protected_shared(before[shared], current[shared])
    expected_names = {node.split("::", 1)[1].split("[", 1)[0]
                      for node in plan["tests"]["green_nodes"]}
    text = auxiliary.decode()
    assert all("def " + name + "(" in text for name in expected_names)
    assert "from tests import test_operational_runtime_closure as _frozen" in text
    assert len(plan["tests"]["red_nodes"]) == 8 and len(plan["tests"]["green_nodes"]) == 13
    with tokenize.open(AUX) as stream:
        token_count = sum(1 for _ in tokenize.generate_tokens(stream.readline))
    evidence = Path(command["evidence_dir"])
    evidence.mkdir(parents=True, exist_ok=False)
    outputs = [write(evidence / "invocation.json", {
        "argv": command["argv"], "cwd": str(ROOT), "finite_env": command["finite_env"],
        "timeout_seconds": 120, "hard_cap": "SIGALRM", "attempt": 1, "retry": 0,
        "script_pin": pin(Path(__file__).absolute()), "reservation_id": gate["reservation_id"],
        "author_ledger_before": ledger_before, "outer_capture": gate["transport"],
        "independent_streams_in_tool": None})]
    sources = []
    diffs = []
    for path, raw in {**current, str(AUX): auxiliary}.items():
        previous = before.get(path, b"")
        sources.append({**pin(path), "base64": base64.b64encode(raw).decode(),
                        "before_bytes": len(previous), "before_sha256": digest(previous),
                        "initially_absent": path == str(AUX)})
        diffs.extend(difflib.unified_diff(previous.decode().splitlines(True),
                     raw.decode().splitlines(True), fromfile=path + ".R182-before", tofile=path))
    proof = {"round": "R182", "phase": phase, "status": "SOURCE_ONLY_UNEXECUTED_TESTS",
             "owned_count": 25, "baseline_owned_count": 24, "other_owned_unchanged": 23,
             "protected_count": 211, "A80556_preserved": True,
             "original_test_whole_preserved": True, "verifier_whole_preserved": True,
             "auxiliary_equal_RED": phase == "green", "source_tokens_read": token_count,
             "declared_red_nodes": plan["tests"]["red_nodes"],
             "declared_green_nodes": plan["tests"]["green_nodes"],
             "parent_roles": roles, "tests_collected_or_run": False,
             "runtime_authority_claim": False, "inherited_R179_completion_path": shared}
    fixture = {"round": "R182", "phase": phase,
               "helper_calls_by_node": {node: 1 for node in plan["tests"][phase + "_nodes"]},
               "baseline_decode_observed": False, "expected_red": "8 DID NOT RAISE only",
               "Memory_lifecycle": "Unchanged R175 observer; recompute actual sidecar denominators.",
               "OC1": "Existing original-clock finally cleanup unchanged.",
               "worker_broker_OS_counts": None,
               "negative_projection": plan["tests"]["negative_projection"],
               "negative_joins": plan["tests"]["negative_joins"],
               "positive_cases": plan["tests"]["positive_cases"]}
    outputs.append(write(evidence / "candidate-snapshot.json",
        {"round": "R182", "phase": phase, "sources": sources, "protected": protected,
         "baseline": pin(BASELINE)}))
    outputs.append(write(evidence / "source-scope-proof.json", proof))
    outputs.append(write(evidence / "fixture-map.json", fixture))
    outputs.append(write(evidence / "change-report.json",
        {"round": "R182", "phase": phase, "sources": [
         {key: value for key, value in item.items() if key != "base64"} for item in sources],
         "allowed_product_delta": [shared] if phase == "green" else [],
         "inherited_R179_completion_separately_labeled_by_author": phase == "green"}))
    diff_path = evidence / "limited.diff"
    with diff_path.open("xb") as stream:
        stream.write("".join(diffs).encode())
    outputs.append(pin(diff_path))
    fixed_inputs(plan, phase)
    for record in gate["input_records"]:
        check(record)
    for path, raw in {**current, str(AUX): auxiliary}.items():
        assert Path(path).read_bytes() == raw
    for record in protected + outputs:
        check(record)
    result = {"round": "R182", "command": command["id"], "exit_code": 0,
              "attempt": 1, "retry": 0, "outputs": outputs, "status": "SOURCE_ONLY",
              "product_commands": 0, "test_execution": False, "T1_complete": False,
              "independent_outer_capture": gate["transport"]}
    result_pin = write(evidence / "result.json", result)
    signal.alarm(0)
    print(json.dumps({"command": command["id"], "result": result_pin,
                      "outputs": len(outputs), "product_commands": 0}))


if __name__ == "__main__":
    main()
