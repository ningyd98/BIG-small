from pathlib import Path
import json
import hashlib
import base64
import difflib
import signal

def _timeout(_signum, _frame):
    raise TimeoutError("R174 preparation metadata exceeded the authorized 120-second limit")

signal.signal(signal.SIGALRM, _timeout)
signal.alarm(120)

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
PROCESS = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds"
D158 = PROCESS / "round158-p6-stage-b-local-temporal-publication-20261013"
D166 = PROCESS / "round166-p6-t1-legacy-supervision-claim-timing-20261013"
D174 = PROCESS / "round174-p6-t1-legacy-condition-json-normalization-20261014"
TASK = D158 / "implementation/t1"
PLAN_SHA = "7ed5507ab0105106caaf434711d0c90893a0b783995471ba7535997ee31e655e"
MD_SHA = "7311015236f959f498ef4483cf024929dbde283d2eb9ddbcdfaae8d77610037a"
CANDIDATE_TEST_PIN = {"path":str(ROOT/"tests/test_operational_runtime_closure.py"),
    "bytes":125299,"sha256":"42a5a079bbd41b3d52adf683ce4e5c07d8678333adf367d7833dee496d4825d6"}
CHANGES = [
  {
    "before": "    \"\"\"Semantic sources come from actual legacy codecs, never empty schema placeholders.\"\"\"\n",
    "after": "    \"\"\"Semantic sources come from actual legacy codecs, never empty schema placeholders.\"\"\"\n    import json\n\n"
  },
  {
    "before": "        raw = source.model_dump(mode=\"json\") if old_tag == \"recovery.retry-budget.v1\" else source.to_payload()\n",
    "after": "        legacy_raw_payload = source.model_dump(mode=\"json\") if old_tag == \"recovery.retry-budget.v1\" else source.to_payload()\n        raw = json.loads(json.dumps(\n            legacy_raw_payload, allow_nan=False, sort_keys=True,\n            separators=(\",\", \":\"), ensure_ascii=False,\n        ))\n"
  },
  {
    "before": "            assert source.to_payload() == legacy_budget_payload\n",
    "after": "            assert source.to_payload() == legacy_raw_payload\n            assert json.loads(json.dumps(\n                source.to_payload(), allow_nan=False, sort_keys=True,\n                separators=(\",\", \":\"), ensure_ascii=False,\n            )) == legacy_budget_payload\n"
  }
]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()

def file_pin(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def canonical(raw):
    assert isinstance(raw, str) and raw.strip(), ("nonempty path", raw)
    relative = Path(raw)
    assert ".." not in relative.parts, ("parent traversal forbidden", raw)
    path = relative if relative.is_absolute() else ROOT / relative
    assert path.is_relative_to(ROOT), ("outside fixed repository root", raw)
    assert not path.is_symlink(), ("symlink forbidden", raw)
    for parent in path.parents:
        assert not parent.is_symlink(), ("symlink parent forbidden", raw)
        if parent == ROOT:
            break
    return str(path)

def coordinates(raw_paths):
    result = [canonical(raw) for raw in raw_paths]
    assert len(result) == len(set(result)), ("duplicate canonical paths", raw_paths)
    return result

def checked_pin(record):
    path = Path(canonical(record["path"]))
    receipt = file_pin(path)
    assert receipt["bytes"] == record["bytes"], ("pinned bytes", str(path))
    assert receipt["sha256"] == record["sha256"], ("pinned SHA256", str(path))
    return receipt

def parent_ledger_guard(path, role, command_ids):
    document = json.loads(path.read_bytes())
    if role == "author":
        assert document["schema_version"] == "bigsmall.r158-author-command-ledger.v1"
    commands = document["commands"]
    assert type(commands) is dict and len(commands) == 15 and set(commands) == set(command_ids)
    for name, entry in commands.items():
        for key in ("authorized", "used", "remaining"):
            assert type(entry[key]) is int
        assert entry["authorized"] == 1
        assert entry["cwd"] == str(ROOT)
        assert type(entry["argv"]) is list
        if name in ("mypy_baseline", "t1_red", "t1_green"):
            assert entry["used"] == 1 and entry["remaining"] == 0
            expected_state = "SPENT" if role == "author" else (
                "SPENT_ACTUAL_DIAGNOSTIC_CENSUS" if name == "mypy_baseline"
                else "SPENT_ACTUAL_UNEXPECTED_LEGACY_CONTROL_FAILURE" if name == "t1_red"
                else "SPENT_ACTUAL_UNEXPECTED_T1_GREEN_FAILURE"
            )
        else:
            assert entry["used"] == 0 and entry["remaining"] == 1
            expected_state = "HELD" if role == "author" else "HELD_PENDING_ROOT_GATE"
        assert entry["state"] == expected_state, ("role-specific state", role, name)
    assert sum(entry["used"] for entry in commands.values()) == 3
    assert sum(entry["remaining"] for entry in commands.values()) == 12
    return file_pin(path)


def local_ledger_guard(document, role, plan, selected, selected_used):
    schema = "bigsmall.r174-command-ledger.v1" if role == "author" else "bigsmall.r174-root-command-ledger.v1"
    assert document["schema_version"] == schema and document["round"] == "R174"
    assert document["role"] == role and document["no_retry"] is True
    assert document["plan_sha256"] == PLAN_SHA
    commands = document["commands"]
    assert set(commands) == {"preparation_metadata","recovery7","ROOT_settlement_metadata"}
    for name, entry in commands.items():
        contract = plan["command_budget"][name]
        assert entry["authorized"] == entry["max_attempts"] == 1
        assert entry["timeout_seconds"] == contract["timeout_seconds"]
        assert entry["argv"] == contract.get("argv")
        assert entry["outer_runner_argv"] == contract.get("outer_runner_argv")
        assert entry["cwd"] == str(ROOT)
        if name == selected and selected_used:
            assert entry["used"] == 1 and entry["remaining"] == 0
            expected = "SPENT" if role == "author" else "RESERVED_BY_ROOT"
            assert entry["state"] == expected
        else:
            assert entry["used"] == 0 and entry["remaining"] == 1
            assert entry["state"] == ("HELD" if role == "author" else "HELD_PENDING_ROOT_GATE")

assert Path.cwd() == ROOT
plan_bytes = (D174/"plan.json").read_bytes()
md_bytes = (D174/"plan.md").read_bytes()
assert sha(plan_bytes) == PLAN_SHA and sha(md_bytes) == MD_SHA
plan = json.loads(plan_bytes)
contract = plan["command_budget"]["preparation_metadata"]
assert contract["timeout_seconds"] == 120
assert canonical(__file__) == canonical(contract["argv"][1])
gate_bytes = (D174/"script-gate.json").read_bytes()
gate_document = json.loads(gate_bytes)
assert gate_document["schema_version"] == "bigsmall.r174-script-gate.v1"
gate = gate_document["commands"]["preparation_metadata"]
assert gate["state"] == "APPROVED"
assert gate["argv"] == contract["argv"] and gate["cwd"] == str(ROOT)
assert gate["timeout_seconds"] == 120
assert gate["candidate_test_pin"] == CANDIDATE_TEST_PIN
checked_pin(gate["source_pin"])
assert canonical(gate["source_pin"]["path"]) == canonical(__file__)
checked_pin(gate["runner_pin"])
assert canonical(gate["runner_pin"]["path"]) == canonical(plan["preparation"]["new_scripts"][1])
root_ledger_path = D174/"root-command-ledger.json"
author_ledger_path = D174/"command-ledger.json"
root_ledger_bytes = root_ledger_path.read_bytes()
author_ledger_bytes = author_ledger_path.read_bytes()
root_ledger = json.loads(root_ledger_bytes)
author_ledger = json.loads(author_ledger_bytes)
local_ledger_guard(root_ledger,"root",plan,"preparation_metadata",True)
local_ledger_guard(author_ledger,"author",plan,"preparation_metadata",False)
assert isinstance(root_ledger["commands"]["preparation_metadata"]["reservation_id"],str)
entry = author_ledger["commands"]["preparation_metadata"]
entry.update({"used":1,"remaining":0,"state":"SPENT",
    "reservation_id":root_ledger["commands"]["preparation_metadata"]["reservation_id"],
    "attempts":1,"retries":0})
spent_author_bytes = encode(author_ledger)
# Consume the independent author allowance before all preparation work; uncertainty stays spent.
assert author_ledger_path.read_bytes() == author_ledger_bytes
author_ledger_path.write_bytes(spent_author_bytes)
assert author_ledger_path.read_bytes() == spent_author_bytes

assert len(plan["inputs"]) == 55
coordinates([item["path"] for item in plan["inputs"]])
test_path = Path(plan["scope"]["test_file"])
report_records = plan["preparation"]["previous_reports"]
assert len(report_records) == 13
report_paths = coordinates([item["path"] for item in report_records])
allowed_initial_delta = {str(test_path)}
static_records = [item for item in plan["inputs"] if canonical(item["path"]) not in allowed_initial_delta]
assert len(static_records) == 54
for item in static_records:
    checked_pin(item)
checked_pin(CANDIDATE_TEST_PIN)
pre_report_bytes = {canonical(item["path"]):Path(canonical(item["path"])).read_bytes() for item in report_records}
old_semantic = json.loads(pre_report_bytes[str(TASK/"semantic.json")])
old_sources = {}
for item in old_semantic["sources"]:
    raw = base64.b64decode(item["base64"],validate=True)
    assert len(raw) == item["bytes"] and sha(raw) == item["sha256"]
    old_sources[canonical(item["path"])] = raw
assert len(old_sources) == 24 and str(test_path) in old_sources
test_before = old_sources[str(test_path)]
test_before_pin = next(item for item in plan["inputs"] if item["path"] == str(test_path))
assert len(test_before) == test_before_pin["bytes"] and sha(test_before) == test_before_pin["sha256"]
test_after = test_path.read_bytes()
start, end = plan["pre_metadata_proof"]["exact_helper_bounds"]
before_text, after_text = test_before.decode(), test_after.decode()
assert before_text.count(start) == after_text.count(start) == 1
assert before_text.count(end) == after_text.count(end) == 1
ba, bb = before_text.index(start), before_text.index(end)
aa, ab = after_text.index(start), after_text.index(end)
assert before_text[:ba] == after_text[:aa] and before_text[bb:] == after_text[ab:]
expected_helper = before_text[ba:bb]
for change in CHANGES:
    assert expected_helper.count(change["before"]) == 1
    expected_helper = expected_helper.replace(change["before"],change["after"],1)
assert after_text[aa:ab] == expected_helper
for path_string, raw in old_sources.items():
    if path_string != str(test_path):
        assert Path(path_string).read_bytes() == raw
assert sha(test_after[:80556]) == "c1a68fe0b5ff88bdf604e4859a17da73f61f56b1fd934897f0e66a484d9ae861"
assert test_after[:80556] == test_before[:80556]
test_tail = b'@pytest.mark.parametrize("family", ["bootstrap", "supervision", "owner_grounding", "route_completion_budget"])'
assert test_before.count(test_tail) == test_after.count(test_tail) == 1
assert test_before[test_before.index(test_tail):] == test_after[test_after.index(test_tail):]
parent_plan = json.loads((D158/"plan.json").read_bytes())
manifest = json.loads((D158/"input-pins.json").read_bytes())
before_path = TASK/"before.json"
before_bytes = before_path.read_bytes()
before = json.loads(before_bytes)
owned = coordinates(parent_plan["scope"]["owned_paths"])
t1_owned = set(coordinates(parent_plan["tasks"][0]["owned_paths"]))
new_owned = set(coordinates(parent_plan["scope"]["new_paths"]))
original = {canonical(item["path"]):item for item in before["sources"]}
assert len(owned) == 24 and len(original) == 23 and len(t1_owned) == 9
assert len(new_owned) == 1 and set(owned)-set(original) == new_owned
assert set(owned) == set(old_sources)
snapshots, source_index, full_diff, later = [], [], [], []
for path_string in owned:
    raw = Path(path_string).read_bytes()
    record = original.get(path_string)
    old = b"" if record is None else base64.b64decode(record["base64"],validate=True)
    if record is not None:
        assert len(old) == record["bytes"] and sha(old) == record["sha256"]
    else:
        assert path_string in new_owned
    if path_string not in t1_owned:
        assert raw == old
        later.append(path_string)
    snapshots.append({"path":path_string,"relative_path":str(Path(path_string).relative_to(ROOT)),
        "bytes":len(raw),"sha256":sha(raw),"changed":raw != old,"T1_owned":path_string in t1_owned,
        "before_bytes":None if record is None else len(old),
        "before_sha256":None if record is None else sha(old),
        "base64":base64.b64encode(raw).decode()})
    lines = raw.decode().splitlines()
    source_index.append({"path":path_string,"sha256":sha(raw),"lines":len(lines),
        "text_declarations":[{"line":number,"indent":len(line)-len(line.lstrip()),"declaration":line.lstrip()}
            for number,line in enumerate(lines,1) if line.lstrip().startswith(("def ","class "))]})
    if raw != old:
        full_diff.extend(difflib.unified_diff(old.decode().splitlines(keepends=True),raw.decode().splitlines(keepends=True),
            fromfile=path_string+" (original R158 before)",tofile=path_string+" (after R174 helper)",n=3))
assert len(later) == 15
assert {item["path"] for item in snapshots if item["changed"]} == t1_owned
source_pins = [{key:value for key,value in item.items() if key != "base64"} for item in snapshots]
assert len(manifest["protected"]) == 211
coordinates([item["path"] for item in manifest["protected"]])
protected = [checked_pin(item) for item in manifest["protected"]]
ledger_pins = [parent_ledger_guard(D158/"command-ledger.json","author",parent_plan["commands"]),
    parent_ledger_guard(D158/"root-command-ledger.json","root",parent_plan["commands"])]
golden = checked_pin(plan["pre_metadata_proof"]["golden"])
assert len(json.loads(Path(golden["path"]).read_bytes())) == 16
for item in plan["inputs"]:
    if item["path"].endswith("/golden-provenance.json"):
        checked_pin(item)
assert not (D158/"implementation/t1_red/legacy-goldens.json").exists()
implementation = D174/"implementation"
outputs = plan["preparation"]["exclusive_preparation_outputs"]
written_paths = [path for path in outputs if not path.endswith("preparation-actual-tool-return.json")]
assert len(written_paths) == 6 and all(not Path(path).exists() for path in written_paths)
helper_diff = "".join(difflib.unified_diff(before_text.splitlines(keepends=True),after_text.splitlines(keepends=True),
    fromfile=str(test_path)+" (before R174)",tofile=str(test_path)+" (R174 helper)",n=3)).encode()
full_diff_bytes = "".join(full_diff).encode()
usage = dict(old_semantic["usage"])
usage.update({"R158_used":3,"R158_remaining":12,"R158_remaining_state":"HELD",
    "t1_green_used":1,"t1_green_remaining":0,"t1_green_state":"SPENT",
    "R174_preparation_metadata_used":1,"R174_preparation_metadata_remaining":0,
    "R174_recovery7_used":0,"R174_recovery7_remaining":1,"R174_recovery7_state":"HELD",
    "R174_ROOT_settlement_metadata_used":0,"R174_ROOT_settlement_metadata_remaining":1})
original_green = {"tests":7,"passes":5,"failures":2,"errors":0,"skips":0,
    "product_exit":1,"runner_tool_exit":2,"used":1,"remaining":0,"overall_pass":False,
    "raw_preserved":plan["original_failure"]["six_raw"]}
coverage = {"targeted_R173_accessor_execution":False,"R174_recovery7_executed":False,
    "limit":"Fixture JSON-boundary text proof only; no local-history targeted execution."}
checks = dict(old_semantic["checks"])
checks.update({"ledger_pins":ledger_pins,"owned_current_snapshot_count":24,
    "protected_pins":protected,"protected_count":211,"unchanged_later_owned_count":15,
    "unchanged_later_owned":later,"original_23_before_preserved":file_pin(before_path),
    "A80556_sha256":sha(test_after[:80556]),"seven_T1_test_bodies_and_decorators_unchanged":True,
    "current_test_equals_accepted_R170_after_pin":False,
    "current_test_is_R174_approved_helper_only_delta":True,"current_test":CANDIDATE_TEST_PIN})
scope = {"schema_version":"bigsmall.r174-scope-proof.v1","candidate_only":True,
    "test_before":test_before_pin,"test_after":CANDIDATE_TEST_PIN,"helper_bounds":[start,end],
    "exact_replacements":CHANGES,"test_outside_helper_byte_identical":True,
    "production_23_byte_identical_to_settled_snapshot":True,"seven_bodies_unchanged":True,
    "A80556_unchanged":True,"checks":checks,"usage":usage,"original_green":original_green,"coverage":coverage}
snapshot = {"schema_version":"bigsmall.r174-candidate-snapshot.v1","sources":snapshots,
    "source_text_index":source_index,"source_pins":source_pins,"protected":protected,
    "parent_ledger_pins":ledger_pins,"runner_pin":gate["runner_pin"],
    "old_runner_pin":checked_pin(next(item for item in plan["inputs"] if item["path"] == plan["preparation"]["parent_script_immutable"])),
    "checks":checks,"usage":usage,"original_green":original_green,"coverage":coverage}
archive = {"schema_version":"bigsmall.r174-before-t1-reports.v1","records":[
    {**item,"base64":base64.b64encode(pre_report_bytes[item["path"]]).decode()} for item in report_records]}
documents = {name:json.loads(pre_report_bytes[str(TASK/(name+".json"))]) for name in
    ["semantic","final-freeze","change-report","fixture-map","budget-report","step-report"]}
r174_fact = {"status":"PREPARATION_ONLY_RECOVERY_HELD","original_green":original_green,
    "coverage":coverage,"scope_proof":str(implementation/"scope-proof.json"),
    "source_snapshot":str(implementation/"candidate-snapshot.json"),
    "old_reports_archive":str(implementation/"before-t1-reports.json"),"usage":usage}
for document in documents.values():
    document["usage"] = usage
    document["R174"] = r174_fact
    if "checks" in document:
        document["checks"] = checks
    if "source_pins" in document:
        document["source_pins"] = source_pins
    document["status"] = "R174_CANDIDATE_PREPARATION_ORIGINAL_GREEN_FAILED_RECOVERY_HELD"
    if "test_first_prerequisites" in document:
        document["test_first_prerequisites"]["original_T1_GREEN"] = original_green
        document["test_first_prerequisites"]["current_T1_candidate"] = "R174_RECOVERY_HELD_NOT_EXECUTED"
documents["semantic"]["sources"] = snapshots
documents["semantic"]["source_text_index"] = source_index
documents["semantic"]["previous_current_metadata_preserved"] = {"archive":str(implementation/"before-t1-reports.json"),"records":report_records}
documents["change-report"]["complete_candidate_diff"] = {"path":str(TASK/"limited.diff"),
    "bytes":len(full_diff_bytes),"sha256":sha(full_diff_bytes)}
documents["step-report"]["pending"] = ["ROOT preparation settlement","one independent R174 recovery7 gate and run",
    "ROOT independent settlement metadata","unused original fresh T1 review","T2 and T3"]
refreshed = {}
for name, document in documents.items():
    refreshed[str(TASK/(name+".json"))] = encode(document)
    refreshed[str(TASK/(name+".md"))] = (
        "# R158 T1 "+name+" after R174 preparation\n\n"
        "Original T1 GREEN is spent 1/0 with actual 5 PASS, 2 FAIL, 0 ERROR, 0 SKIP. "
        "Parent budget is 3 spent / 12 HELD. Old raw and all thirteen pre-refresh reports remain preserved.\n\n"
        "Only the legacy source JSON boundary inside _b_local_cases changed. All 23 production sources, "
        "211 protected files, A80556, seven test bodies, real 16-tag golden/provenance and old runner remain unchanged.\n\n"
        "Independent R174 recovery7 is HELD 0/1. This preparation is bytes/text/hash evidence only. "
        "R173 history accessor targeted execution remains false; no T1/B9/T12/native/actual/formal acceptance.\n").encode()
refreshed[str(TASK/"limited.diff")] = full_diff_bytes
assert set(refreshed) == set(report_paths)
payloads = {str(implementation/"before-test.py"):test_before,
    str(implementation/"before-t1-reports.json"):encode(archive),
    str(implementation/"limited.diff"):helper_diff,
    str(implementation/"scope-proof.json"):encode(scope),
    str(implementation/"candidate-snapshot.json"):encode(snapshot)}
immutable_records = [item for item in static_records if item["path"] not in report_paths]
assert len(immutable_records) == 41

def recheck():
    for item in immutable_records:
        checked_pin(item)
    for item in protected:
        checked_pin(item)
    for item in source_pins:
        checked_pin(item)
    assert before_path.read_bytes() == before_bytes
    assert (D174/"plan.json").read_bytes() == plan_bytes
    assert (D174/"plan.md").read_bytes() == md_bytes
    assert (D174/"script-gate.json").read_bytes() == gate_bytes
    assert root_ledger_path.read_bytes() == root_ledger_bytes
    assert author_ledger_path.read_bytes() == spent_author_bytes
    checked_pin(gate["source_pin"])
    checked_pin(gate["runner_pin"])
    assert not (D158/"implementation/t1_red/legacy-goldens.json").exists()

recheck()
for item in report_records:
    checked_pin(item)
assert all(not Path(path).exists() for path in written_paths)
implementation.mkdir(parents=True,exist_ok=True)
for path in (str(implementation/"before-test.py"),str(implementation/"before-t1-reports.json")):
    with Path(path).open("xb") as stream:
        stream.write(payloads[path])
    assert Path(path).read_bytes() == payloads[path]
for path, raw in payloads.items():
    if path not in (str(implementation/"before-test.py"),str(implementation/"before-t1-reports.json")):
        with Path(path).open("xb") as stream:
            stream.write(raw)
        assert Path(path).read_bytes() == raw
for path, raw in refreshed.items():
    assert Path(path).read_bytes() == pre_report_bytes[path]
    Path(path).write_bytes(raw)
    assert Path(path).read_bytes() == raw
for path, raw in payloads.items():
    assert Path(path).read_bytes() == raw
for path, raw in refreshed.items():
    assert Path(path).read_bytes() == raw
recheck()
artifact_pins = [file_pin(Path(path)) for path in list(payloads)+list(refreshed)]
summary = {"schema_version":"bigsmall.r174-preparation-result.v1","status":"METADATA_PREPARATION_ONLY",
    "artifact_pins":artifact_pins,"test_before":test_before_pin,"test_after":CANDIDATE_TEST_PIN,
    "counts":{"plan_inputs":55,"pre_refresh_fixed_inputs":54,"post_refresh_fixed_inputs":41,
        "owned":24,"production_unchanged":23,"original_before":23,"later_unchanged":15,
        "protected":211,"reports_archived":13,"reports_refreshed":13,"test_nodes":7,"golden_tags":16},
    "usage":usage,"original_green":original_green,"coverage":coverage,"acceptance":old_semantic["acceptance"]}
result_path = implementation/"preparation-result.json"
result_bytes = encode(summary)
with result_path.open("xb") as stream:
    stream.write(result_bytes)
assert result_path.read_bytes() == result_bytes
for path, raw in payloads.items():
    assert Path(path).read_bytes() == raw
for path, raw in refreshed.items():
    assert Path(path).read_bytes() == raw
recheck()
summary["preparation_result_pin"] = file_pin(result_path)
print(json.dumps(summary,sort_keys=True))
