# R170 retained direct -c source. Execution requires the fresh ROOT text/SHA/argv gate.
# This file is source evidence only, not a launcher or additional execution layer.
from pathlib import Path
import json
import hashlib
import difflib

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUND = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round170-p6-detached-real-broker-receipt-closure-20261013")
PLAN_JSON_SHA256 = "96686f705bc8c7d462e95fd0c330f8dfd220e1371ccbc4ea8b3cd4e616f612a9"
PLAN_MD_SHA256 = "e4209290b953dacf0ee22f610bff2051da2acc5dc9d226be062eb0254153ca42"
ACTIVATION_SHA256 = "acd2f2b7badf5b77343ed3c28b6f7decafecdf75f84a292b4a85a903ad7d53b8"
CHANGES = json.loads("[{\"path\":\"src/cloud_edge_robot_arm/vision/local_temporal.py\",\"before\":\"def _reference(value: JSONValue) -> dict[str, JSONValue]:\",\"after\":\"def _lease_segment_receipt(value: JSONValue) -> dict[str, JSONValue]:\\n    \\\"\\\"\\\"Validate and preserve a detached raw broker receipt, without issuing one.\\\"\\\"\\\"\\n    receipt = _object(value, frozenset(\\n        \\\"domain event_id lower_ns upper_ns deadline_ns budget_ns end_exclusive\\\".split()\\n    ))\\n    _domain(receipt[\\\"domain\\\"])\\n    _text(receipt[\\\"event_id\\\"])\\n    lower = _integer(receipt[\\\"lower_ns\\\"])\\n    upper = _integer(receipt[\\\"upper_ns\\\"])\\n    budget = _integer(receipt[\\\"budget_ns\\\"], positive=True)\\n    deadline = _integer(receipt[\\\"deadline_ns\\\"], positive=True)\\n    if lower > upper or deadline != lower + budget or receipt[\\\"end_exclusive\\\"] is not True:\\n        raise ValueError(\\\"exact detached broker HARD_OPEN receipt required\\\")\\n    return receipt\\n\\n\\ndef _reference(value: JSONValue) -> dict[str, JSONValue]:\"},{\"path\":\"src/cloud_edge_robot_arm/vision/local_temporal.py\",\"before\":\"    acquisition = _bracket(identity[\\\"original_acquisition\\\"])\",\"after\":\"    acquisition = _lease_segment_receipt(identity[\\\"original_acquisition\\\"])\"},{\"path\":\"src/cloud_edge_robot_arm/vision/local_temporal.py\",\"before\":\"def _decision(value: JSONValue) -> dict[str, JSONValue]:\\n    decision = _object(value, DECISION_FIELDS)\\n    if decision[\\\"schema_version\\\"] != \\\"visual.local-two-authority-decision.v1\\\":\\n        raise ValueError(\\\"exact two-authority decision tag required\\\")\\n    for key in (\\\"operation_id\\\", \\\"lease_epoch\\\", \\\"job_id\\\", \\\"run_id\\\", \\\"worker_id\\\", \\\"lease_id\\\"):\\n        _text(decision[key])\\n    for key in (\\\"operation_sha256\\\", \\\"original_time_hash\\\", \\\"lease_row_digest\\\", \\\"source_identity\\\"):\\n        _sha(decision[key])\\n    for key in (\\\"lease_generation\\\", \\\"lease_row_revision\\\", \\\"attempt\\\"):\\n        _integer(decision[key], positive=True)\\n    domain = _domain(decision[\\\"app_domain\\\"])\\n    current = _bracket(decision[\\\"app_current\\\"])\\n    if current[\\\"domain\\\"] != domain:\\n        raise ValueError(\\\"current app event belongs to another domain\\\")\\n    refs = [_reference(raw) for raw in _array(decision[\\\"app_references\\\"])]\\n    if not refs or any(ref[\\\"domain\\\"] != domain for ref in refs):\\n        raise ValueError(\\\"same original D_app references required\\\")\\n    app = _object(decision[\\\"app_verdict\\\"], frozenset((\\\"status\\\", \\\"reasons\\\")))\\n    observation = _object(decision[\\\"lease_observation\\\"])\\n    if observation.get(\\\"schema\\\") != \\\"simulation.operational-lease-observation.v1\\\":\\n        raise ValueError(\\\"detached actual broker observation shape required\\\")\\n    lease_domain = _domain(observation[\\\"domain\\\"])\\n    if lease_domain == domain:\\n        raise ValueError(\\\"never merge D_app and D_lease\\\")\\n    if observation[\\\"generation\\\"] != decision[\\\"lease_generation\\\"] or any(observation[key] != decision[key] for key in (\\\"job_id\\\", \\\"worker_id\\\", \\\"lease_id\\\", \\\"attempt\\\", \\\"source_identity\\\")):\\n        raise ValueError(\\\"decision current lease/fence mismatch\\\")\\n    if _object(observation[\\\"current\\\"])[\\\"domain\\\"] != lease_domain:\\n        raise ValueError(\\\"broker current domain changed\\\")\\n    if _bracket(observation[\\\"original_acquisition\\\"])[\\\"domain\\\"] != lease_domain:\\n        raise ValueError(\\\"broker original acquisition domain changed\\\")\\n    if decision[\\\"disposition\\\"] not in {\\\"VALID\\\", \\\"REJECTED\\\", \\\"UNKNOWN\\\"}:\\n        raise ValueError(\\\"detached disposition required\\\")\\n    for raw in (decision[\\\"reasons\\\"], app[\\\"reasons\\\"], observation[\\\"reasons\\\"]):\\n        for reason in _array(raw):\\n            _text(reason)\\n    if decision[\\\"disposition\\\"] == \\\"VALID\\\":\\n        if app[\\\"status\\\"] != \\\"VALID\\\" or observation[\\\"status\\\"] != \\\"VALID\\\":\\n            raise ValueError(\\\"both independent recorded authorities must be valid\\\")\\n        if any(_integer(current[\\\"upper_ns\\\"]) >= _integer(ref[\\\"deadline_ns\\\"], positive=True) for ref in refs):\\n            raise ValueError(\\\"recorded app decision expired at original hard bound\\\")\\n    return decision\",\"after\":\"def _decision(value: JSONValue) -> dict[str, JSONValue]:\\n    decision = _object(value, DECISION_FIELDS)\\n    if decision[\\\"schema_version\\\"] != \\\"visual.local-two-authority-decision.v1\\\":\\n        raise ValueError(\\\"exact two-authority decision tag required\\\")\\n    for key in (\\\"operation_id\\\", \\\"lease_epoch\\\", \\\"job_id\\\", \\\"run_id\\\", \\\"worker_id\\\", \\\"lease_id\\\"):\\n        _text(decision[key])\\n    for key in (\\\"operation_sha256\\\", \\\"original_time_hash\\\", \\\"lease_row_digest\\\", \\\"source_identity\\\"):\\n        _sha(decision[key])\\n    for key in (\\\"lease_generation\\\", \\\"lease_row_revision\\\", \\\"attempt\\\"):\\n        _integer(decision[key], positive=True)\\n    domain = _domain(decision[\\\"app_domain\\\"])\\n    current = _bracket(decision[\\\"app_current\\\"])\\n    if current[\\\"domain\\\"] != domain:\\n        raise ValueError(\\\"current app event belongs to another domain\\\")\\n    refs = [_reference(raw) for raw in _array(decision[\\\"app_references\\\"])]\\n    if not refs or any(ref[\\\"domain\\\"] != domain for ref in refs):\\n        raise ValueError(\\\"same original D_app references required\\\")\\n    app = _object(decision[\\\"app_verdict\\\"], frozenset((\\\"status\\\", \\\"reasons\\\")))\\n    _text(app[\\\"status\\\"])\\n    observation = _object(decision[\\\"lease_observation\\\"], frozenset(\\n        \\\"status reasons domain original_acquisition segment current job_id lease_id worker_id attempt generation source_identity schema stage_label\\\".split()\\n    ))\\n    if observation[\\\"schema\\\"] != \\\"simulation.operational-lease-observation.v1\\\" or observation[\\\"stage_label\\\"] != \\\"LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO\\\":\\n        raise ValueError(\\\"exact unchanged broker observation schema/stage required\\\")\\n    _text(observation[\\\"status\\\"])\\n    lease_domain = _domain(observation[\\\"domain\\\"])\\n    if lease_domain == domain:\\n        raise ValueError(\\\"never merge D_app and D_lease\\\")\\n    if _integer(observation[\\\"generation\\\"], positive=True) != decision[\\\"lease_generation\\\"] or any(observation[key] != decision[key] for key in (\\\"job_id\\\", \\\"worker_id\\\", \\\"lease_id\\\", \\\"attempt\\\", \\\"source_identity\\\")):\\n        raise ValueError(\\\"decision current lease/fence mismatch\\\")\\n    acquisition = _lease_segment_receipt(observation[\\\"original_acquisition\\\"])\\n    segment = _lease_segment_receipt(observation[\\\"segment\\\"])\\n    lease_current = _bracket(observation[\\\"current\\\"], event=False)\\n    if any(item[\\\"domain\\\"] != lease_domain for item in (acquisition, segment, lease_current)):\\n        raise ValueError(\\\"broker acquisition/current segment/current bracket domain changed\\\")\\n    if acquisition[\\\"budget_ns\\\"] != segment[\\\"budget_ns\\\"]:\\n        raise ValueError(\\\"renewal cannot change the frozen broker TTL\\\")\\n    if decision[\\\"disposition\\\"] not in {\\\"VALID\\\", \\\"REJECTED\\\", \\\"UNKNOWN\\\"}:\\n        raise ValueError(\\\"detached disposition required\\\")\\n    for raw in (decision[\\\"reasons\\\"], app[\\\"reasons\\\"], observation[\\\"reasons\\\"]):\\n        for reason in _array(raw):\\n            _text(reason)\\n    if decision[\\\"disposition\\\"] == \\\"VALID\\\":\\n        if app[\\\"status\\\"] != \\\"VALID\\\" or observation[\\\"status\\\"] != \\\"VALID\\\":\\n            raise ValueError(\\\"both independent recorded authorities must be valid\\\")\\n        app_upper = _integer(current[\\\"upper_ns\\\"])\\n        for ref in refs:\\n            effective = _object(ref[\\\"effective_upper\\\"])\\n            endpoint = _integer(effective[\\\"value_ns\\\"])\\n            if app_upper >= _integer(ref[\\\"deadline_ns\\\"], positive=True) or app_upper > endpoint or (app_upper == endpoint and effective[\\\"inclusive\\\"] is not True):\\n                raise ValueError(\\\"recorded D_app decision crosses original HARD_OPEN/AGE_CLOSED bounds\\\")\\n        if _integer(lease_current[\\\"upper_ns\\\"]) >= _integer(segment[\\\"deadline_ns\\\"], positive=True):\\n            raise ValueError(\\\"recorded D_lease decision crosses current segment HARD_OPEN bound\\\")\\n    return decision\"},{\"path\":\"src/cloud_edge_robot_arm/vision/local_temporal.py\",\"before\":\"            if decision[\\\"lease_epoch\\\"] != identity[\\\"epoch\\\"]:\\n                raise ValueError(\\\"original lease epoch changed\\\")\",\"after\":\"            if decision[\\\"lease_epoch\\\"] != identity[\\\"epoch\\\"]:\\n                raise ValueError(\\\"original lease epoch changed\\\")\\n            if _object(decision[\\\"lease_observation\\\"])[\\\"original_acquisition\\\"] != identity[\\\"original_acquisition\\\"]:\\n                raise ValueError(\\\"renewal cannot replace the immutable raw original acquisition\\\")\"},{\"path\":\"tests/test_operational_runtime_closure.py\",\"before\":\"                \\\"original_acquisition\\\": {\\n                    \\\"domain\\\": lease_domain, \\\"event_identity\\\": lease_token.event_identity,\\n                    \\\"lower_ns\\\": acquisition.lower_ns, \\\"upper_ns\\\": acquisition.upper_ns,\\n                },\",\"after\":\"                # Caller-created SOURCE_ONLY descriptor in the unchanged raw broker shape.\\n                \\\"original_acquisition\\\": {\\n                    \\\"domain\\\": lease_domain, \\\"event_id\\\": lease_token.event_identity,\\n                    \\\"lower_ns\\\": acquisition.lower_ns, \\\"upper_ns\\\": acquisition.upper_ns,\\n                    \\\"budget_ns\\\": 1_000_000_000,\\n                    \\\"deadline_ns\\\": acquisition.lower_ns + 1_000_000_000,\\n                    \\\"end_exclusive\\\": True,\\n                },\"},{\"path\":\"tests/test_operational_runtime_closure.py\",\"before\":\"def _b_decision(original, app_current, generation=1):\\n    acquisition = original[\\\"lease_identity\\\"][\\\"original_acquisition\\\"]\\n    identity = original[\\\"lease_identity\\\"]\\n    lease_observation = {\\n        \\\"status\\\": \\\"UNKNOWN\\\", \\\"reasons\\\": [\\\"detached_codec_fixture_no_broker_authority\\\"],\\n        \\\"domain\\\": acquisition[\\\"domain\\\"], \\\"original_acquisition\\\": acquisition,\\n        \\\"segment\\\": {\\\"domain\\\": acquisition[\\\"domain\\\"], \\\"generation\\\": generation,\\n                    \\\"origin\\\": acquisition, \\\"deadline_ns\\\": 1_000_000_000},\\n        \\\"current\\\": {\\\"domain\\\": acquisition[\\\"domain\\\"], \\\"lower_ns\\\": 0, \\\"upper_ns\\\": 0},\\n        \\\"job_id\\\": identity[\\\"job_id\\\"], \\\"lease_id\\\": identity[\\\"lease_id\\\"],\\n        \\\"worker_id\\\": identity[\\\"worker_id\\\"], \\\"attempt\\\": identity[\\\"attempt\\\"],\\n        \\\"generation\\\": generation, \\\"source_identity\\\": identity[\\\"source_identity\\\"],\\n        \\\"schema\\\": \\\"simulation.operational-lease-observation.v1\\\",\\n        \\\"stage_label\\\": \\\"LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO\\\",\\n    }\\n    return {\\n        \\\"schema_version\\\": \\\"visual.local-two-authority-decision.v1\\\",\\n        \\\"operation_id\\\": \\\"r158-detached-operation\\\", \\\"operation_sha256\\\": \\\"a\\\" * 64,\\n        \\\"original_time_hash\\\": _b_sha(original), \\\"app_domain\\\": original[\\\"app_domain\\\"],\\n        \\\"app_current\\\": app_current, \\\"app_verdict\\\": {\\\"status\\\": \\\"UNKNOWN\\\", \\\"reasons\\\": [\\\"detached\\\"]},\\n        \\\"app_references\\\": [original[\\\"task_reference\\\"]], \\\"lease_observation\\\": lease_observation,\\n        \\\"lease_epoch\\\": identity[\\\"epoch\\\"], \\\"lease_generation\\\": generation,\\n        \\\"lease_row_revision\\\": generation, \\\"lease_row_digest\\\": \\\"b\\\" * 64,\\n        \\\"source_identity\\\": identity[\\\"source_identity\\\"],\\n        **{key: identity[key] for key in (\\\"job_id\\\", \\\"run_id\\\", \\\"worker_id\\\", \\\"lease_id\\\", \\\"attempt\\\")},\\n        \\\"disposition\\\": \\\"UNKNOWN\\\", \\\"reasons\\\": [\\\"detached_codec_fixture_no_private_scope\\\"],\\n    }\",\"after\":\"def _b_decision(original, app_current, generation=1):\\n    acquisition = original[\\\"lease_identity\\\"][\\\"original_acquisition\\\"]\\n    identity = original[\\\"lease_identity\\\"]\\n    # Caller-created UNKNOWN shape controls; these are not live broker receipts.\\n    segment = copy.deepcopy(acquisition)\\n    if generation > 1:\\n        shift = (generation - 1) * 1_000_000\\n        segment[\\\"event_id\\\"] = \\\"r158-caller-segment-\\\" + str(generation)\\n        segment[\\\"lower_ns\\\"] = acquisition[\\\"lower_ns\\\"] + shift\\n        segment[\\\"upper_ns\\\"] = acquisition[\\\"upper_ns\\\"] + shift\\n        segment[\\\"deadline_ns\\\"] = segment[\\\"lower_ns\\\"] + segment[\\\"budget_ns\\\"]\\n    exact_receipt_fields = {\\\"domain\\\", \\\"event_id\\\", \\\"lower_ns\\\", \\\"upper_ns\\\",\\n                            \\\"deadline_ns\\\", \\\"budget_ns\\\", \\\"end_exclusive\\\"}\\n    assert set(acquisition) == set(segment) == exact_receipt_fields\\n    assert segment[\\\"budget_ns\\\"] == acquisition[\\\"budget_ns\\\"]\\n    assert generation == 1 or segment != acquisition\\n    assert acquisition == original[\\\"lease_identity\\\"][\\\"original_acquisition\\\"]\\n    lease_observation = {\\n        \\\"status\\\": \\\"UNKNOWN\\\", \\\"reasons\\\": [\\\"detached_codec_fixture_no_broker_authority\\\"],\\n        \\\"domain\\\": acquisition[\\\"domain\\\"], \\\"original_acquisition\\\": acquisition,\\n        \\\"segment\\\": segment,\\n        \\\"current\\\": {\\\"domain\\\": acquisition[\\\"domain\\\"],\\n                    \\\"lower_ns\\\": segment[\\\"upper_ns\\\"], \\\"upper_ns\\\": segment[\\\"upper_ns\\\"]},\\n        \\\"job_id\\\": identity[\\\"job_id\\\"], \\\"lease_id\\\": identity[\\\"lease_id\\\"],\\n        \\\"worker_id\\\": identity[\\\"worker_id\\\"], \\\"attempt\\\": identity[\\\"attempt\\\"],\\n        \\\"generation\\\": generation, \\\"source_identity\\\": identity[\\\"source_identity\\\"],\\n        \\\"schema\\\": \\\"simulation.operational-lease-observation.v1\\\",\\n        \\\"stage_label\\\": \\\"LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO\\\",\\n    }\\n    return {\\n        \\\"schema_version\\\": \\\"visual.local-two-authority-decision.v1\\\",\\n        \\\"operation_id\\\": \\\"r158-detached-operation\\\", \\\"operation_sha256\\\": \\\"a\\\" * 64,\\n        \\\"original_time_hash\\\": _b_sha(original), \\\"app_domain\\\": original[\\\"app_domain\\\"],\\n        \\\"app_current\\\": app_current, \\\"app_verdict\\\": {\\\"status\\\": \\\"UNKNOWN\\\", \\\"reasons\\\": [\\\"detached\\\"]},\\n        \\\"app_references\\\": [original[\\\"task_reference\\\"]], \\\"lease_observation\\\": lease_observation,\\n        \\\"lease_epoch\\\": identity[\\\"epoch\\\"], \\\"lease_generation\\\": generation,\\n        \\\"lease_row_revision\\\": generation, \\\"lease_row_digest\\\": \\\"b\\\" * 64,\\n        \\\"source_identity\\\": identity[\\\"source_identity\\\"],\\n        **{key: identity[key] for key in (\\\"job_id\\\", \\\"run_id\\\", \\\"worker_id\\\", \\\"lease_id\\\", \\\"attempt\\\")},\\n        \\\"disposition\\\": \\\"UNKNOWN\\\", \\\"reasons\\\": [\\\"detached_codec_fixture_no_private_scope\\\"],\\n    }\"}]")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")

def absolute(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path

def pin(record):
    path = absolute(record["path"])
    data = path.read_bytes()
    assert len(data) == record["bytes"], ("pinned byte length", str(path))
    assert sha(data) == record["sha256"], ("pinned SHA256", str(path))
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}

assert Path.cwd() == ROOT
plan_bytes = (ROUND / "plan.json").read_bytes()
md_bytes = (ROUND / "plan.md").read_bytes()
assert sha(plan_bytes) == PLAN_JSON_SHA256
assert sha(md_bytes) == PLAN_MD_SHA256
plan = json.loads(plan_bytes)
outputs = plan["outputs"]
activation_bytes = Path(outputs["activation"]).read_bytes()
assert sha(activation_bytes) == ACTIVATION_SHA256
assert plan["R169_disposition"]["status"] == "HELD_SUPERSEDED"
assert plan["R169_disposition"]["patch_used"] == plan["R169_disposition"]["metadata_used"] == 0
assert plan["R169_disposition"]["execute"] is False
assert plan["budget"]["R158"]["used"] == 2
assert plan["budget"]["R158"]["remaining"] == 13
assert plan["budget"]["R158"]["t1_green_used"] == 0
assert plan["budget"]["R158"]["t1_green_remaining"] == 1
owned = set(plan["scope"]["owned"])
assert owned == {str(ROOT / "src/cloud_edge_robot_arm/vision/local_temporal.py"), str(ROOT / "tests/test_operational_runtime_closure.py")}
assert len(plan["inputs"]) == 22
records = {record["path"]: record for record in plan["inputs"]}
unchanged_inputs = [pin(record) for record in plan["inputs"] if record["path"] not in owned]

protected_path = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round158-p6-stage-b-local-temporal-publication-20261013/input-pins.json"
protected_manifest = json.loads(protected_path.read_bytes())
protected = protected_manifest["protected"]
assert len(protected) == 211
protected_receipts = [pin(record) for record in protected]

assert plan["scope"]["test_regions"] == ["_b_detached_original", "_b_decision"]
before_paths = {
    "src/cloud_edge_robot_arm/vision/local_temporal.py": Path(outputs["before_shared"]),
    "tests/test_operational_runtime_closure.py": Path(outputs["before_test"]),
}
source_receipts = []
diffs = []
before_test = None
after_test = None
for relative, before_path in before_paths.items():
    original_path = ROOT / relative
    before = before_path.read_bytes()
    after = original_path.read_bytes()
    initial_pin = records[str(original_path)]
    assert len(before) == initial_pin["bytes"]
    assert sha(before) == initial_pin["sha256"]
    expected = before.decode("utf-8")
    selected = [change for change in CHANGES if change["path"] == relative]
    for change in selected:
        assert expected.count(change["before"]) == 1, ("unique approved replacement", relative)
        expected = expected.replace(change["before"], change["after"], 1)
    assert after == expected.encode("utf-8"), ("only complete approved text replacements", relative)
    source_receipts.append({
        "path": str(original_path), "before_path": str(before_path),
        "before_bytes": len(before), "before_sha256": sha(before),
        "after_bytes": len(after), "after_sha256": sha(after),
        "approved_replacements": len(selected),
    })
    diffs.extend(difflib.unified_diff(
        before.decode("utf-8").splitlines(keepends=True),
        after.decode("utf-8").splitlines(keepends=True),
        fromfile=str(before_path), tofile=str(original_path), n=3,
    ))
    if relative == "tests/test_operational_runtime_closure.py":
        before_test, after_test = before, after

assert before_test is not None and after_test is not None
left = b"def _b_detached_original("
right = b"def _b_transaction("
assert before_test.count(left) == after_test.count(left) == 1
assert before_test.count(right) == after_test.count(right) == 1
before_left, before_right = before_test.index(left), before_test.index(right)
after_left, after_right = after_test.index(left), after_test.index(right)
assert before_left < before_right and after_left < after_right
assert before_test[:before_left] == after_test[:after_left]
assert before_test[before_right:] == after_test[after_right:]
assert after_test[:80556] == before_test[:80556]
assert sha(after_test[:80556]) == "c1a68fe0b5ff88bdf604e4859a17da73f61f56b1fd934897f0e66a484d9ae861"

disposition_bytes = Path(outputs["R169_disposition"]).read_bytes()
current_disposition = json.loads(disposition_bytes)
# Preserve ROOT's complete disposition without guessing its metadata schema.
output_paths = [Path(outputs[name]) for name in ("change_report", "limited_diff", "metadata_receipt")]
assert len(set(output_paths)) == 3
assert all(not path.exists() for path in output_paths)
limited_diff = "".join(diffs).encode("utf-8")
report = {
    "schema_version": "bigsmall.r170-change-report.v1", "producer_round": "R170",
    "status": "TEXT_SCOPE_VERIFIED_ONLY", "sources": source_receipts,
    "scope": plan["scope"], "approved_changes": CHANGES,
    "outside_two_adjacent_test_helpers_byte_identical": True,
    "all_seven_test_bodies_and_decorators_byte_identical": True,
    "A80556_sha256": sha(after_test[:80556]),
    "R169_disposition": "HELD_SUPERSEDED",
    "R169_ROOT_disposition_record": current_disposition,
    "R169_ROOT_disposition_sha256": sha(disposition_bytes),
    "R158_usage_proof": {"used": 2, "remaining": 13, "basis": "both complete unchanged parent ledger pins and ROOT activation"},
    "R170_metadata_actual_execution_count": 1, "R170_metadata_remaining": 0,
    "retries": 0, "T1_GREEN_executed": False, "real_broker_execution": False,
    "fixture_provenance": "SOURCE_ONLY_CALLER_CREATED_UNKNOWN",
    "software_only": True, "actual": False, "formal": False,
}
report_bytes = encode(report)
receipt = {
    "schema_version": "bigsmall.r170-metadata-verification.v1", "producer_round": "R170",
    "plan_json_sha256": sha(plan_bytes), "plan_md_sha256": sha(md_bytes),
    "ROOT_activation_sha256": sha(activation_bytes),
    "unchanged_input_receipts": unchanged_inputs,
    "protected_input_count": len(protected_receipts), "protected_input_receipts": protected_receipts,
    "before_sources_preserved": True, "source_receipts": source_receipts,
    "limited_diff": {"path": str(output_paths[1]), "bytes": len(limited_diff), "sha256": sha(limited_diff)},
    "change_report": {"path": str(output_paths[0]), "bytes": len(report_bytes), "sha256": sha(report_bytes)},
    "all_other_shared_bytes_unchanged": True, "all_test_bytes_outside_two_helpers_unchanged": True,
    "seven_domain_drafts_producers_helpers_runner_goldens_and_parent_ledgers_pinned": True,
    "usage": {"R158_used": 2, "R158_remaining": 13, "R169_patch_used": 0, "R169_metadata_used": 0, "R170_metadata_used": 1, "R170_metadata_remaining": 0, "new_pytest": 0, "new_static": 0, "retries": 0},
    "independent_tool_streams": None, "actual_tool_return": None,
    "runtime_acceptance": {"T1_GREEN": False, "B9_complete": False, "native": False, "actual": False, "formal": False},
}
receipt_bytes = encode(receipt)
for path, data in zip(output_paths, (report_bytes, limited_diff, receipt_bytes)):
    with path.open("xb") as stream:
        stream.write(data)
results = [{"path": str(path), "bytes": len(data), "sha256": sha(data)}
           for path, data in zip(output_paths, (report_bytes, limited_diff, receipt_bytes))]
print(json.dumps({"status": "R170_TEXT_SCOPE_VERIFIED_ONLY", "outputs": results, "R170_metadata_used": 1, "R170_metadata_remaining": 0, "R158_used": 2, "R158_remaining": 13, "new_pytest": 0, "new_static": 0}, sort_keys=True))
