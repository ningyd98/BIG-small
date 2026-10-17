"""ROOT R191 one-shot byte/source proof. Standard library only."""
from pathlib import Path
import base64
import hashlib
import json
import os
import signal
import sys
import traceback

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round191-p6-t1-root-source-proof-record-shape-20261014")
R182 = D.parent / "round182-p6-t1-recursive-local-projection-closure-20261014"
R179 = D.parent / "round179-p6-t1-detached-causality-hash-audit-20261014"
E = D / "implementation"
PIN_KEYS = ("path", "bytes", "sha256")
SLOT = "r191-corrected-source-scope-gate-once"
PLAN_SHA = "58ba353f764818a0c6def8073f310fad4e188a58d18f00821ef2de5037a27451"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def pin(path):
    path = Path(path)
    assert path.is_absolute() and not path.is_symlink()
    assert all(not parent.is_symlink() for parent in path.parents)
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=sha(raw))

def load(path):
    return json.loads(Path(path).read_bytes())

def check(record):
    assert pin(record["path"]) == {key: record[key] for key in PIN_KEYS}, record["path"]

def unarchive(record):
    raw = base64.b64decode(record["base64"], validate=True)
    assert len(raw) == record["bytes"] and sha(raw) == record["sha256"]
    return raw

def write(path, value):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with Path(path).open("xb") as stream:
        stream.write(raw)
    return pin(path)

def alarm(signum, frame):
    raise TimeoutError("R191 source-only hard cap120seconds")

def body_between(raw, start, end):
    assert raw.count(start) == raw.count(end) == 1
    left, right = raw.index(start), raw.index(end)
    assert left < right
    return raw[left + len(start):right]

def validate(act, plan):
    for record in act["fixed_inputs"]:
        check(record)
    report = load(R182 / "implementation/product-repair-change-report.json")
    shared = str(ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py")
    before, after = unarchive(report["source_before"]), unarchive(report["source_after"])
    assert (len(before), sha(before)) == (104539, "8090c6d7a7e3911ecbd9cc13678f950980dc35834174dc762ca3d507e6aa866b")
    assert (len(after), sha(after)) == (111096, "63ec55b0e3d4b45fe68f2890ab4eb9e2714f52d572eeee70a6efbecaebd53cd8")
    assert report["source_after"]["path"] == shared and Path(shared).read_bytes() == after
    assert report["status"] == "SOURCE_READY_UNEXECUTED_CANDIDATE"
    snapshot = load(R182 / "implementation/prepare_red/candidate-snapshot.json")
    assert len(snapshot["sources"]) == len(report["owned25_current_pins"]) == 25
    assert len(snapshot["protected"]) == len(report["protected211"]) == 211
    assert snapshot["protected"] == report["protected211"]
    assert {r["path"] for r in snapshot["sources"]} == {r["path"] for r in report["owned25_current_pins"]}
    for record in snapshot["sources"]:
        raw = unarchive(record)
        assert raw == before if record["path"] == shared else Path(record["path"]).read_bytes() == raw
    for record in report["owned25_current_pins"] + report["protected211"]:
        check(record)
    check(report["before_snapshot"])
    check(report["limited_diff"])
    regions = []
    for start, end in ((b"\nFIELDS:", b"\n\ndef _copy("),
                       (b"def _copy(", b"def _object("),
                       (b"def _canonical(", b"def _hash(")):
        old, new = body_between(before, start, end), body_between(after, start, end)
        assert old == new
        regions.append(dict(start=start.decode(), end=end.decode(), bytes=len(old), sha256=sha(old)))
    historical = {}
    current_scripts = {}
    for edit in plan["bounded_edits"]:
        original = edit["implementation_before_archive"]["original"]
        archive_path = Path(edit["implementation_before_archive"]["archive_path"])
        archived = archive_path.read_bytes()
        assert (len(archived), sha(archived)) == (original["bytes"], original["sha256"])
        historical[original["path"]] = {key: original[key] for key in PIN_KEYS}
        current_scripts[original["path"]] = Path(original["path"]).read_bytes()
        check(act["current_script_pins"][original["path"]])
    assert len(historical) == len(current_scripts) == 2
    prepare_path = str(R182 / "implementation/prepare-evidence.py")
    root_path = str(R182 / "implementation/root-settlement.py")
    prepare_before = (E / "before-prepare-evidence.py").read_bytes()
    prepare_after = current_scripts[prepare_path]
    start = b"def protected_shared(before, after):\n"
    end = b"    for start, end in (("
    assert prepare_before.count(start) == prepare_after.count(start) == 1
    assert prepare_before.count(end) == prepare_after.count(end) == 1
    assert prepare_before.split(start, 1)[0] == prepare_after.split(start, 1)[0]
    assert prepare_before.split(end, 1)[1] == prepare_after.split(end, 1)[1]
    assert body_between(prepare_after, start, end).decode() == act["approved_prepare_block"]
    root_before = (E / "before-root-settlement.py").read_bytes()
    root_after = current_scripts[root_path]
    old = act["approved_root_map_before"].encode()
    new = act["approved_root_map_after"].encode()
    assert root_before.count(old) == 1 and root_after == root_before.replace(old, new, 1)
    red = load(R182 / "implementation/red/result.json")
    gate = load(R182 / "script-gate.json")
    assert red["input_records"] == gate["commands"]["red"]["input_records"]
    assert len(red["input_records"]) == 292
    for logical, original in historical.items():
        assert [record for record in red["input_records"] if record["path"] == logical] == [original]
    remaining_current = 0
    for record in red["input_records"]:
        if record["path"] == shared:
            assert (record["bytes"], record["sha256"]) == (len(before), sha(before))
        elif record["path"] in historical:
            assert record == historical[record["path"]]
        else:
            check(record)
            remaining_current += 1
    assert remaining_current == 289
    original_plan = load(R182 / "plan.json")
    original_fixed = 0
    for record in original_plan["inputs"]:
        if record["role"] not in ("activation_before_mutable", "source_before_authorized_edit"):
            check(record)
            original_fixed += 1
    fixed_scripts = [(R182 / "implementation/run-command.py", 14806, "6dc5ecae7d14fa8d5119b999064f604ca5f0fe5f4c0e6eed6963f28f84de054e"),
                     (R179 / "implementation/prepare-evidence.py", 12691, "8ea8a72f39cce758ab43cf9a6d6e33327191395e420b156d34ce96a08d3aa97f"),
                     (R179 / "implementation/run-command.py", 14179, "049d873e6328f89641d20d9577de448818d6ff9ff9161054abebaeb27f4bc84e"),
                     (R179 / "implementation/root-settlement.py", 16271, "542f408da66cc5dabf061a994d3877d73dd90c227f2e4d0c48e07eaf3dbfca94")]
    for path, length, digest in fixed_scripts:
        record = pin(path)
        assert (record["bytes"], record["sha256"]) == (length, digest)
    roles = {}
    for directory in (R182, R179):
        for name in ("command-ledger.json", "root-command-ledger.json"):
            ledger = load(directory / name)
            assert len(ledger["commands"]) == 6
            for key, slot in ledger["commands"].items():
                assert (slot["used"], slot["remaining"]) == ((1, 0) if key in ("prepare_red", "red") else (0, 1))
            roles[str(directory / name)] = pin(directory / name)
    assert all(not Path(path).exists() for path in act["unexecuted_evidence_directories"])
    for record in act["fixed_inputs"]:
        check(record)
    for record in report["owned25_current_pins"] + report["protected211"]:
        check(record)
    return dict(source_files=25, other_sources_unchanged=24, protected_files=211,
                protected_regions=regions, unchanged_scripts=4,
                historical_script_pins=historical,
                current_script_pins=act["current_script_pins"],
                old_RED_fixed_current_records=remaining_current,
                original_plan_current_fixed=original_fixed,
                original_role_pins=roles, no_execution_evidence_created=True,
                original_f6a27c_failure_preserved=True)

def main():
    signal.signal(signal.SIGALRM, alarm)
    signal.alarm(120)
    assert Path.cwd() == ROOT and len(sys.argv) == 1
    assert sha((D / "plan.json").read_bytes()) == PLAN_SHA
    plan = load(D / "plan.json")
    command = plan["archive_and_execution"]["new_metadata_slot"]
    assert [sys.executable, str(Path(__file__).absolute())] == command["argv"]
    assert dict(os.environ) == command["finite_env"]
    act = load(D / "root-activation.json")
    check(act["source_gate_pin"])
    ledger_path = D / "command-ledger.json"
    ledger_before = ledger_path.read_bytes()
    ledger = json.loads(ledger_before)
    slot = ledger["commands"][SLOT]
    assert (slot["authorized"], slot["used"], slot["remaining"], slot["state"]) == (1, 1, 0, "RESERVED_BY_ROOT")
    slot["state"] = "SPENT_BEFORE_ACTION"
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    write(E / "invocation.json", dict(argv=command["argv"], cwd=str(ROOT), finite_env=command["finite_env"],
          timeout_seconds=120, hard_cap="SIGALRM", attempt=1, retry=0, script_pin=pin(Path(__file__).absolute()),
          ROOT_activation_archive=dict(base64=base64.b64encode((D / "root-activation.json").read_bytes()).decode(),
                                       **pin(D / "root-activation.json")),
          ROOT_ledger_before=dict(base64=base64.b64encode(ledger_before).decode(), bytes=len(ledger_before), sha256=sha(ledger_before))))
    failures = []
    observations = None
    try:
        observations = validate(act, plan)
    except BaseException as error:
        failures.append(dict(type=type(error).__name__, message=str(error), traceback="".join(traceback.format_exception(error))))
    result = dict(round="R191", command=SLOT, exit_code=1 if failures else 0, attempt=1, retry=0,
                  status="ROOT_ACCEPTED_CORRECTED_SOURCE_SCOPE_ONLY" if not failures else "SOURCE_SCOPE_GATE_FAILED",
                  observations=observations, failures=failures, input_records=act["fixed_inputs"],
                  product_commands=0, test_execution=False, T1_complete=False, T12_complete=False,
                  native_actual=False, formal_research_accepted=False)
    saved = write(E / "proof.json", result)
    signal.alarm(0)
    print(json.dumps(dict(round="R191", status=result["status"], exit_code=result["exit_code"], proof=saved)))
    return result["exit_code"]

if __name__ == "__main__":
    raise SystemExit(main())
