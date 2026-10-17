import hashlib
import json
import signal
from pathlib import Path

signal.alarm(120)
ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round198-p6-t1-review-report-from-existing-records-20261014"


def read(path):
    return Path(path).read_bytes()


def pin(path):
    data = read(path)
    return {"path": str(path), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def json_read(path):
    return json.loads(read(path))


plan_path = D / "plan.json"
assert pin(plan_path)["sha256"] == "9fe4095a47dd387c731650396242b1e73f70fb71f1a8887b791908bd1b9e0a5d"
plan = json_read(plan_path)
verified_inputs = []
for expected in plan["inputs"]:
    actual = pin(expected["path"])
    assert actual == expected, actual
    verified_inputs.append(actual)

original = json_read(plan["inputs"][0]["path"])
assert original["missing"] == []
existing = original["existing"]
expected_keys = {"continuationIssues", "continuationLedger",
                 "continuationPaths", "continuationWriteFailure"}
expected_keys.update("continuationRead" + str(i) for i in range(1, 9))
assert set(existing) == expected_keys
issues = existing["continuationIssues"]
assert [issue["id"] for issue in issues] == ["C1", "C2", "C3"]
assert all(issue["severity"] == "Important" for issue in issues)
raw_read_receipts = []
for i in range(1, 9):
    receipt = existing["continuationRead" + str(i)]
    assert receipt["exit_code"] == 0
    assert isinstance(receipt["output"], str)
    assert "Warning: truncated output" not in receipt["output"]
    raw_read_receipts.append({"batch": i, "chunk_id": receipt["chunk_id"],
                              "exit_code": receipt["exit_code"]})

md_path, report_path, ledger_path = map(Path, plan["allowed_report_paths"])
report = json_read(report_path)
expected_report = dict(plan["report_json_contract"])
expected_report["issues"] = issues
assert report == expected_report
ledger = json_read(ledger_path)
assert ledger == existing["continuationLedger"]
assert ledger["cumulative"] == {"authorized": 17, "used": 17, "remaining": 0}
assert len(ledger["reads"]) == 8
assert ledger["product_commands"] == ledger["source_edits"] == 0
md = read(md_path).decode("utf-8")
assert md.strip()
assert all(marker in md for marker in ["C1", "C2", "C3", "Needs fixes", "51", "204"])
activation = json_read(D / "root-activation.json")
assert activation["R197_slot"]["effective_state"] == "HELD_SUPERSEDED_BY_R198_NONEXECUTABLE"
assert activation["R197_slot"]["used"] == 0
assert activation["R197_slot"]["remaining"] == 1
assert activation["R198_verification"]["authorized"] == 1
assert activation["R198_verification"]["used"] == 1
assert activation["R198_verification"]["remaining"] == 0
assert activation["R198_verification"]["state"] == "RESERVED_SINGLE_ACTUAL_LAUNCH_NO_RETRY"
assert activation["review"]["used"] == 17
assert activation["review"]["remaining"] == 0
assert activation["T1_complete"] is activation["T12_complete"] is False
report_pins = [pin(path) for path in [md_path, report_path, ledger_path]]
result = {
    "round": "R198",
    "status": "VERIFIED_NEWLY_COMPOSED_EXISTING_REVIEW_RECORDS",
    "frozen_inputs": verified_inputs,
    "report_pins": report_pins,
    "issues_deep_equal": True,
    "ledger_deep_equal": True,
    "raw_read_receipts": raw_read_receipts,
    "review": {"authorized": 17, "used": 17, "remaining": 0, "reset": False},
    "R197_slot": {"used": 0, "remaining": 1, "executable": False},
    "metadata_verification": {"attempt": 1, "retry": 0, "authorized": 1},
    "product_commands": 0,
    "new_source_review_reads": 0,
    "new_tests": 0,
    "source_and_STATE_PHASE_unchanged": True,
    "markdown_semantic_review": "ROOT fulltext gate; machine checks only nonempty UTF8 and basic markers",
    "T1_complete": False, "T12_complete": False, "native": False, "formal": False,
}
with (D / "implementation/verification-result.json").open("x", encoding="utf-8") as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
summary = {
    "round": "R198", "status": result["status"], "report_pins": report_pins,
    "frozen_inputs_verified": len(verified_inputs),
    "issues_deep_equal": True, "ledger_deep_equal": True,
    "actual_read_receipts": 8, "review_used": 17, "review_remaining": 0,
    "T1_complete": False, "T12_complete": False,
}
output = json.dumps(summary, ensure_ascii=False)
assert len(output.encode("utf-8")) <= 5000
print(output)
signal.alarm(0)
