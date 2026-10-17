
from pathlib import Path
import json
import hashlib
import base64
import difflib
import signal

def _r172_timeout(_signum, _frame):
    raise TimeoutError("R172 metadata action exceeded the authorized 120-second limit")

signal.signal(signal.SIGALRM, _r172_timeout)
signal.alarm(120)

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUND = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013"
TASK = ROUND / "implementation/t1"
D166 = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round166-p6-t1-legacy-supervision-claim-timing-20261013"
D170 = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round170-p6-detached-real-broker-receipt-closure-20261013"

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
        if name in ("mypy_baseline", "t1_red"):
            assert entry["used"] == 1 and entry["remaining"] == 0
            expected_state = "SPENT" if role == "author" else (
                "SPENT_ACTUAL_DIAGNOSTIC_CENSUS" if name == "mypy_baseline"
                else "SPENT_ACTUAL_UNEXPECTED_LEGACY_CONTROL_FAILURE"
            )
        else:
            assert entry["used"] == 0 and entry["remaining"] == 1
            expected_state = "HELD" if role == "author" else "HELD_PENDING_ROOT_GATE"
        assert entry["state"] == expected_state, ("role-specific state", role, name)
    assert sum(entry["used"] for entry in commands.values()) == 2
    assert sum(entry["remaining"] for entry in commands.values()) == 13
    return file_pin(path)

assert Path.cwd() == ROOT
D172 = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round172-p6-t1-freeze-metadata-assertion-20261014")
recovery_plan_bytes = (D172 / "plan.json").read_bytes()
assert sha(recovery_plan_bytes) == "fb565c6ca6a7dd4045b43e0baeee8abc67b2eaff7660b0e6f9d9e0268a6d5bff"
assert sha((D172 / "plan.md").read_bytes()) == "672c2f2a71b02a0b8a7c7b1d4e0e4f9d94ce0b5d839922af1732ef7d762330c9"
recovery_plan = json.loads(recovery_plan_bytes)
assert recovery_plan["budget"]["original_failed_freeze"] == {"used": 1, "remaining": 0, "retries": 0}
execution_bytes = (D172 / "execution-ledger.json").read_bytes()
execution = json.loads(execution_bytes)
assert execution["round"] == "R172"
assert execution["original_failed_freeze"] == {"used": 1, "remaining": 0, "retries": 0}
reserved = execution["new_metadata"]
assert reserved["authorized"] == reserved["used"] == reserved["max_attempts"] == 1
assert reserved["remaining"] == 0 and reserved["timeout_seconds"] == 120
assert reserved["state"] == "RESERVED_BY_ROOT"
source_path = canonical(recovery_plan["scope"]["corrected_metadata_source"])
assert reserved["source_path"] == source_path and reserved["cwd"] == str(ROOT)
assert reserved["argv"] == [str(ROOT / ".venv/bin/python"), source_path]
assert canonical(__file__) == source_path
assert sha(Path(source_path).read_bytes()) == reserved["source_sha256"]
assert execution["new_product_commands"] == 0
assert execution["R158_used"] == 2 and execution["R158_remaining"] == 13
assert execution["T1_GREEN_used"] == 0 and execution["T1_GREEN_remaining"] == 1
assert execution["no_retry"] is True
assert len(recovery_plan["inputs"]) == 43
input_paths = coordinates([record["path"] for record in recovery_plan["inputs"]])
input_receipts = [checked_pin(record) for record in recovery_plan["inputs"]]
target_records = recovery_plan["partial_write_assessment"]["independent_current_inventory"]
target_paths = coordinates([record["path"] for record in target_records])
assert len(target_paths) == 13
assert set(target_paths) == set(coordinates(recovery_plan["scope"]["report_outputs"]))
replace_records = [record for record in target_records if record["exists"]]
replace_paths = set(coordinates([record["path"] for record in replace_records]))
assert len(replace_records) == 3 and len(replace_paths) == 3
assert replace_paths == {
    str(TASK / "fixture-map.json"), str(TASK / "budget-report.json"),
    str(TASK / "step-report.json"),
}
for record in target_records:
    path = Path(canonical(record["path"]))
    assert path.exists() is record["exists"], ("exact target inventory", str(path))
    if record["exists"]:
        checked_pin(record)
archive_path = Path(canonical(recovery_plan["scope"]["immutable_before_archive"]))
assert not archive_path.exists()

plan = json.loads((ROUND / "plan.json").read_bytes())
manifest = json.loads((ROUND / "input-pins.json").read_bytes())
before_path = TASK / "before.json"
before_bytes = before_path.read_bytes()
before = json.loads(before_bytes)
raw_owned = list(plan["scope"]["owned_paths"])
raw_task_owned = list(plan["tasks"][0]["owned_paths"])
raw_new_owned = list(plan["scope"]["new_paths"])
owned = coordinates(raw_owned)
canonical_task_owned = coordinates(raw_task_owned)
new_owned = coordinates(raw_new_owned)
t1_owned = set(canonical_task_owned)
assert t1_owned <= set(owned)
assert t1_owned == set(coordinates(recovery_plan["observed_scope"]["canonical_task_paths"]))
assert len(new_owned) == 1 and set(new_owned) <= t1_owned
assert len(owned) == 24 and len(t1_owned) == 9 and len(before["sources"]) == 23
assert len(manifest["protected"]) == 211
before_paths = coordinates([record["path"] for record in before["sources"]])
original = {canonical(record["path"]): record for record in before["sources"]}
assert len(original) == 23 and set(original) <= set(owned)
assert set(owned) - set(original) == set(new_owned)
snapshots = []
source_index = []
diff_parts = []
unchanged_later = []
for path_string in owned:
    path = Path(path_string)
    current = path.read_bytes()
    old_record = original.get(path_string)
    if old_record is None:
        assert path_string in new_owned and path_string in t1_owned
        old = b""
    else:
        old = base64.b64decode(old_record["base64"], validate=True)
        assert len(old) == old_record["bytes"] and sha(old) == old_record["sha256"]
    if path_string not in t1_owned:
        assert current == old
        unchanged_later.append(path_string)
    snapshot = {"path": path_string, "relative_path": str(path.relative_to(ROOT)),
                "bytes": len(current), "sha256": sha(current),
                "before_bytes": None if old_record is None else len(old),
                "before_sha256": None if old_record is None else sha(old),
                "changed": current != old, "T1_owned": path_string in t1_owned,
                "raw_scope_path": raw_owned[owned.index(path_string)],
                "raw_before_path": None if old_record is None else old_record["path"],
                "base64": base64.b64encode(current).decode()}
    snapshots.append(snapshot)
    text = current.decode()
    definitions = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("def ") or stripped.startswith("class "):
            definitions.append({"line": number, "indent": len(line)-len(stripped),
                                "declaration": stripped})
    source_index.append({"path": path_string, "sha256": sha(current),
                         "lines": len(text.splitlines()), "text_declarations": definitions})
    if current != old:
        diff_parts.extend(difflib.unified_diff(old.decode().splitlines(keepends=True),
                         text.splitlines(keepends=True), fromfile=path_string + " (original R158 before)",
                         tofile=path_string + " (T1 candidate)", n=3))
assert len(unchanged_later) == 15
assert {record["path"] for record in snapshots if record["changed"]} == t1_owned

protected = []
coordinates([record["path"] for record in manifest["protected"]])
for record in manifest["protected"]:
    path = Path(canonical(record["path"]))
    current = path.read_bytes()
    assert len(current) == record["bytes"] and sha(current) == record["sha256"]
    protected.append({"path": str(path), "bytes": len(current), "sha256": sha(current)})

test_path = ROOT / "tests/test_operational_runtime_closure.py"
test_bytes = test_path.read_bytes()
assert sha(test_bytes[:80556]) == "c1a68fe0b5ff88bdf604e4859a17da73f61f56b1fd934897f0e66a484d9ae861"
r170_receipt = json.loads((D170 / "implementation/metadata-verification.json").read_bytes())
test_r170_pin = next(record for record in r170_receipt["source_receipts"] if record["path"] == str(test_path))
assert sha(test_bytes) == test_r170_pin["after_sha256"]
frozen_before_test = (D170 / "implementation/before-test.py").read_bytes()
tests_start = b'@pytest.mark.parametrize("family", ["bootstrap", "supervision", "owner_grounding", "route_completion_budget"])'
assert frozen_before_test.count(tests_start) == test_bytes.count(tests_start) == 1
assert frozen_before_test[frozen_before_test.index(tests_start):] == test_bytes[test_bytes.index(tests_start):]

golden_path = D166 / "implementation/legacy_control/legacy-goldens.json"
golden_bytes = golden_path.read_bytes()
assert len(golden_bytes) == 121893 and sha(golden_bytes) == "10452e376a00b1672d540fc1332c6beeeaa42b6cff44f03f425531e26a5d0c38"
golden = json.loads(golden_bytes)
assert len(golden) == 16
provenance_path = D166 / "implementation/golden-provenance.json"
golden_provenance = json.loads(provenance_path.read_bytes())
original_absent_golden = ROUND / "implementation/t1_red/legacy-goldens.json"
assert not original_absent_golden.exists()
runner_path = ROUND / "implementation/run-budgeted-command.py"
runner = file_pin(runner_path)
assert runner["bytes"] == 9998 and runner["sha256"] == "a455c05a8794b72e2fb24b72d09a8234b31e86d917512ac21c73d417256bd944"
ledger_pins = [
    parent_ledger_guard(ROUND / "command-ledger.json", "author", plan["commands"]),
    parent_ledger_guard(ROUND / "root-command-ledger.json", "root", plan["commands"]),
]
evidence_pins = [file_pin(path) for path in (
    D166 / "implementation/legacy_control/result.json",
    D166 / "implementation/legacy_control/junit.xml",
    provenance_path,
    D170 / "implementation/actual-tool-return.json",
    D170 / "implementation/metadata-verification.json",
    D170 / "implementation/limited.diff",
)]
names = ["semantic", "final-freeze", "change-report", "fixture-map", "budget-report", "step-report"]
metadata_before = []
for name in names:
    for extension in ("json", "md"):
        path = TASK / (name + "." + extension)
        if path.exists():
            data = path.read_bytes()
            metadata_before.append({**file_pin(path), "base64": base64.b64encode(data).decode()})

assert len(metadata_before) == 3 and {record["path"] for record in metadata_before} == replace_paths
for record in metadata_before:
    checked_pin(record)
normalization_receipt = {"raw_scope_paths": raw_owned, "raw_task_paths": raw_task_owned,
    "canonical_scope_paths": owned, "canonical_task_paths": canonical_task_owned,
    "raw_new_paths": raw_new_owned, "canonical_new_paths": new_owned,
    "before_raw_paths": [record["path"] for record in before["sources"]],
    "before_canonical_paths": before_paths}
acceptance = {"T1_GREEN": False, "T1_complete": False, "B9_complete": False,
              "T12_complete": False, "native": False, "actual": False, "formal": False}
usage = {"R158_used": 2, "R158_remaining": 13, "R158_remaining_state": "HELD",
         "t1_green_used": 0, "t1_green_remaining": 1, "t1_green_state": "HELD",
         "R166_legacy_control_used": 1, "R166_legacy_control_remaining": 0,
         "R169_patch_used": 0, "R169_metadata_used": 0, "R169_state": "HELD_SUPERSEDED",
         "R170_metadata_used": 1, "R170_metadata_remaining": 0,
         "new_product_verifications_during_preparation": 0,
         "original_failed_freeze_used": 1, "original_failed_freeze_remaining": 0,
         "R172_metadata_used": 1, "R172_metadata_remaining": 0}
source_pins = [{key:value for key,value in record.items() if key != "base64"} for record in snapshots]
composite = {"original_t1_red": {"failures": 7, "passes": 0,
              "expected_missing_contract_failures": 6, "unexpected_legacy_failure": 1,
              "legal_single_run_RED": False, "spent_preserved": True},
             "R166_legacy_control": {"passes": 1, "failures": 0, "errors": 0, "skips": 0,
              "ROOT_independently_accepted": True},
             "prerequisite_kind": "TWO_RUN_COMPOSITE_NOT_SINGLE_LEGAL_SEVEN_NODE_RED",
             "current_T1_candidate": "NOT_EXECUTED_NOT_GREEN"}
checks = {"owned_current_snapshot_count": 24, "T1_allowed_paths": sorted(t1_owned),
          "unchanged_later_owned_count": 15, "unchanged_later_owned": unchanged_later,
          "protected_count": 211, "protected_pins": protected,
          "original_23_before_preserved": file_pin(before_path),
          "A80556_sha256": sha(test_bytes[:80556]), "seven_T1_test_bodies_and_decorators_unchanged": True,
          "current_test_equals_accepted_R170_after_pin": True,
          "real_R166_golden": file_pin(golden_path), "golden_tag_count": 16,
          "golden_provenance": file_pin(provenance_path), "original_R158_golden_absent": True,
          "runner": runner, "ledger_pins": ledger_pins}
semantic = {"schema_version": "bigsmall.r158-t1-semantic-candidate.v1",
            "status": "SOURCE_CANDIDATE_PRE_GREEN_HELD", "preparation_date_context": "2026-10-14",
            "frozen_round_identity": "R158/20261013", "author_task": "/root/p6_stage_b_sol",
            "author_model_configuration": "gpt-6.1-sol", "sources": snapshots,
            "source_text_index": source_index, "previous_current_metadata_preserved": metadata_before,
            "checks": checks, "test_first_prerequisites": composite, "usage": usage,
            "normalization": normalization_receipt,
            "semantic_statements_status": "CANDIDATE_IMPLEMENTATION_CLAIMS_PENDING_ROOT_SOURCE_REVIEW_AND_ACTUAL_GREEN",
            "semantic_contracts": {
                "tags": plan["schemas"]["outer"]["payload_fields_by_tag"],
                "original": "fixed D_app origin/references/source/epoch/raw original broker acquisition",
                "decision": "renewable current seven-field segment and generation remain separate D_lease evidence",
                "no_authority": "detached codecs neither create registries nor grant effect or NEW_COMMIT permission",
                "domain": "explicit tag dispatch to distinct detached semantic carriers; legacy UTC instances are not fabricated",
                "budget": "new schema/task/state/revision digest; original reference and limits/counters preserved; decoder cannot initialize a live pool",
                "history": "new D history and retained old/external audit inputs distinguished; historical verification does not sample current wall time",
                "runtime": "T1 local budget routing remains fail-closed; real two-authority locked producers/consumers are T2/T3 obligations",
            }, "acceptance": acceptance, "proof_limit": "Bytes/text/hash preparation only; no AST/import/static/pytest or real broker publication executed."}
freeze = {"schema_version": "bigsmall.r158-t1-final-freeze.v1", "status": "PRE_GREEN_SOURCE_CANDIDATE",
          "source_pins": source_pins, "checks": checks, "test_first_prerequisites": composite,
          "usage": usage, "acceptance": acceptance}
diff_bytes = "".join(diff_parts).encode()
change = {"schema_version": "bigsmall.r158-t1-change-report.v1", "status": "PRE_GREEN_CANDIDATE",
          "changed_paths": [record["path"] for record in source_pins if record["changed"]],
          "source_pins": source_pins, "complete_candidate_diff": {
              "path": str(TASK / "limited.diff"), "bytes": len(diff_bytes), "sha256": sha(diff_bytes)},
          "original_before": file_pin(before_path), "allowed_scope": sorted(t1_owned),
          "test_helper_change_provenance": ["R163 current repo getters/original budget hash", "R166 supervision period one literal", "R170 two raw receipt helpers"],
          "R170_recovery_boundary": "accepted text-scope recovery only; not T1 GREEN or actual registered broker run",
          "acceptance": acceptance}
fixture = {"schema_version": "bigsmall.r158-t1-fixture-map.v1", "status": "PRE_GREEN_ROOT_GATE_PENDING",
           "test_first_prerequisites": composite, "checks": checks, "evidence_pins": evidence_pins,
           "full_real_golden_provenance_record": golden_provenance,
           "controls": {"BIGSMALL_R158_COMMAND": "t1_green",
                        "BIGSMALL_R158_LEGACY_GOLDENS": str(golden_path)},
           "legacy_fixture": "actual protected legacy fixture/domain/repository APIs; accepted original bytes remain immutable",
           "detached_fixture": "SOURCE_ONLY UNKNOWN caller-created D_app descriptors and true seven-field broker receipt shape; no actual heartbeat claim",
           "resources": "T1 helpers retain actual clock/repository finally cleanup; no new resource-producing test/helper change in product preparation",
           "usage": usage, "acceptance": acceptance}
budget = {"schema_version": "bigsmall.r158-t1-budget-report.v1", "status": "PRE_GREEN_HELD",
          "usage": usage, "baseline": {"numeric_exit": 1, "errors": 72, "files_with_errors": 3,
              "checked_files": 22, "diagnostic_census_only": True,
              "mypy_pass_claim": False, "modified_or_new_definition_errors_waived": False},
          "caps": plan["fixture"]["caps"],
          "resource_boundary": {"preparation_external_model_calls": 0, "preparation_network_calls": 0,
             "preparation_GPU_native_calls": 0, "preparation_SQL_or_product_probe": 0,
             "preparation_product_lifecycles": 0, "future_green_actual_resources": None},
          "test_first_prerequisites": composite, "acceptance": acceptance}
step = {"schema_version": "bigsmall.r158-t1-step-report.v1", "status": "CANDIDATE_FROZEN_PENDING_ROOT_GREEN_GATE",
        "preparation_date_context": "2026-10-14", "source_pins": source_pins,
        "checks": checks, "test_first_prerequisites": composite, "usage": usage,
        "R170_boundary": "Accepted source-text/raw-shape repair only. Original T1 unused GREEN remains HELD.",
        "completed_preparation_claims_pending_ROOT_source_review": ["strict shared detached types and all 15 semantic tags",
           "seven domain files explicit local branches/detached carriers/accessors",
           "reference/hash/identity/epoch/raw-acquisition/current-segment joins",
           "immutable budget/source policy and archival history validation",
           "24-owned source snapshot/complete original candidate diff/current metadata preservation"],
        "pending": ["ROOT fresh complete source/fixture/runner gate", "one original seven-node T1 GREEN",
                    "fresh independent T1 review", "T2 and T3 implementation/verification"],
        "actual_tool_evidence": None, "acceptance": acceptance}
documents = {"semantic": semantic, "final-freeze": freeze, "change-report": change,
             "fixture-map": fixture, "budget-report": budget, "step-report": step}

# Build all thirteen target bytes in memory before the first output write.
report_bytes = {}
for name, document in documents.items():
    path = TASK / (name + ".json")
    report_bytes[str(path)] = encode(document)
    md_path = TASK / (name + ".md")
    md = ("# R158 T1 " + name + "\n\n"
          "Status: source candidate only; T1 GREEN remains HELD.\n\n"
          "Original six expected missing-contract failures plus the separately accepted R166 legacy control "
          "are a two-run prerequisite, not a legal single seven-node RED. R170 proves only limited text scope.\n\n"
          "24 owned current source snapshots, 15 unchanged later owned paths, 211 protected inputs, "
          "the original 23 before sources, A80556 and all seven T1 test bodies are preserved. "
          "The actual R166 golden is 121893 bytes with SHA256 10452e376a00b1672d540fc1332c6beeeaa42b6cff44f03f425531e26a5d0c38.\n\n"
          "R158 usage: 2 spent / 13 HELD; original T1 GREEN 0 used / 1 HELD. "
          "No product verification was executed during this preparation.\n\n"
          "Source semantic statements are candidate claims pending ROOT source review and actual GREEN. "
          "Original failed freeze action remains spent 1/0; R172 is one independent metadata action.\n\n"
          "The corresponding JSON contains the complete pins, scope and factual limits.\n").encode()
    report_bytes[str(md_path)] = md
report_bytes[str(TASK / "limited.diff")] = diff_bytes
assert len(report_bytes) == 13 and set(report_bytes) == set(target_paths)
immutable_records = [record for record in recovery_plan["inputs"] if canonical(record["path"]) not in replace_paths]

def immutable_recheck():
    assert sha((D172 / "plan.json").read_bytes()) == "fb565c6ca6a7dd4045b43e0baeee8abc67b2eaff7660b0e6f9d9e0268a6d5bff"
    assert sha((D172 / "plan.md").read_bytes()) == "672c2f2a71b02a0b8a7c7b1d4e0e4f9d94ce0b5d839922af1732ef7d762330c9"
    for record in immutable_records:
        checked_pin(record)
    for record in protected:
        checked_pin(record)
    for record in source_pins:
        checked_pin(record)
    assert sha(Path(source_path).read_bytes()) == reserved["source_sha256"]
    assert (D172 / "execution-ledger.json").read_bytes() == execution_bytes
    assert not original_absent_golden.exists()

# Every source/policy/test/golden/role guard has completed before writing.
immutable_recheck()
for record in replace_records:
    checked_pin(record)
for record in target_records:
    assert Path(canonical(record["path"])).exists() is record["exists"]
assert not archive_path.exists()
archive = {"schema_version": "bigsmall.r172-before-reports.v1", "round": "R172",
           "original_failed_action_preserved": {"used": 1, "remaining": 0, "retries": 0},
           "records": metadata_before, "target_inventory": target_records,
           "normalization": normalization_receipt}
archive_bytes = encode(archive)
with archive_path.open("xb") as stream:
    stream.write(archive_bytes)
assert archive_path.read_bytes() == archive_bytes

artifact_pins = []
for path_string, data in report_bytes.items():
    path = Path(canonical(path_string))
    if path_string in replace_paths:
        original_report = next(record for record in metadata_before if record["path"] == path_string)
        checked_pin(original_report)
        path.write_bytes(data)
    else:
        with path.open("xb") as stream:
            stream.write(data)
    assert path.read_bytes() == data, ("output readback", path_string)
    artifact_pins.append(file_pin(path))

assert archive_path.read_bytes() == archive_bytes
for record in metadata_before:
    preserved = base64.b64decode(record["base64"], validate=True)
    assert len(preserved) == record["bytes"] and sha(preserved) == record["sha256"]
for path_string, data in report_bytes.items():
    assert Path(path_string).read_bytes() == data
immutable_recheck()
archive_pin = file_pin(archive_path)
print(json.dumps({"status": "R172_CANDIDATE_PREPARATION_RECOVERED_ONLY",
                  "artifact_pins": artifact_pins, "before_reports": archive_pin,
                  "counts": {"input_pins":43,"owned":24,"T1_owned_changes":9,
                  "unchanged_later_owned":15,"before":23,"protected":211,
                  "A_prefix":80556,"T1_nodes":7,"real_golden_tags":16,
                  "replaced_reports":3,"exclusive_reports":10},
                  "usage":usage,"acceptance":acceptance},sort_keys=True))
