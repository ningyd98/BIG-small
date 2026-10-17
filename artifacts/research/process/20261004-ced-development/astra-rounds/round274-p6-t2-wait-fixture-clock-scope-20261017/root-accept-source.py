from pathlib import Path
import base64
import difflib
import hashlib
import json
import stat

D = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round274-p6-t2-wait-fixture-clock-scope-20261017")
I = D / "implementation"
checks = []
def check(label, value):
    checks.append({"check": label, "passed": bool(value)})
def pin(path):
    p = Path(path)
    raw = p.read_bytes()
    return {"path": str(p), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
def checked(record, physical=None):
    p = Path(physical or record["path"])
    b = p.read_bytes()
    check("identity " + str(p), stat.S_ISREG(p.lstat().st_mode) and len(b) == record["bytes"] and hashlib.sha256(b).hexdigest() == record["sha256"])
    return b

fixed = {
    "plan.json": (16574, "d3e01660d4d95d430103201ab4afa6e3620422db02f9e257dea82dfbd8d249ad"),
    "root-source-correction-release.json": (11965, "919fcb276a7095a11e9e88ab005047a94d6e1a6aebd712865be1bc2fbcd1c578"),
    "implementation/source-preparation-before.json": (415754, "de25160c8e1927ac8b3b57c58d31a76bdf689557d0859d6c52d8993aeaaeab6a"),
    "implementation/proposed-test.native.patch": (2512, "5fdf2e992c347fa5af5cb636646d4f8ba7ec3aa34f27f5df73a699a2760df572"),
    "implementation/actual-test-native-tool-return.json": (12080, "4ee518fdb37a8d7232168fea122ed541478203d9a8b5bcbfa8eff066cd760c93"),
    "implementation/limited.diff": (2760, "c30fcd85819cd1c4b323f5c7d325db4707a0a1148851d33f53102a9250337b4c"),
    "implementation/change-report.json": (690878, "1425f78ff54bc2711a1cc3e9cb6c96a21d0aeb3bbb5ac61d31c39de637b09c9b"),
    "implementation/actual-source-preparation-tool-returns.json": (69783, "d38eba20aea55413f9010a2937611280d1f579921dc05d0d0d3007d8a6376ca2"),
}
for name, (size, sha) in fixed.items():
    checked({"path": str(D / name), "bytes": size, "sha256": sha})
P = json.loads((D / "plan.json").read_bytes())
M = json.loads(checked(P["before_manifest"]))
B = json.loads((I / "source-preparation-before.json").read_bytes())
N = json.loads((I / "actual-test-native-tool-return.json").read_bytes())
A = json.loads((I / "actual-source-preparation-tool-returns.json").read_bytes())
report = json.loads((I / "change-report.json").read_bytes())
before = checked(M["archive"])
check("full planning before base64", base64.b64decode(M["base64"], validate=True) == before)
check("planning before original identity", len(before) == M["original"]["bytes"] and hashlib.sha256(before).hexdigest() == M["original"]["sha256"])
check("author complete before", B["source_before"] == {k: M[k] for k in ("original", "archive", "base64", "mode")})
check("report complete original generation", report["source_generation"]["before"] == M)
check("original mode", Path(M["archive"]["path"]).lstat().st_mode == M["mode"] == 33204)
check("same fixed twenty inputs", B["inputs"] == P["inputs"] and len(P["inputs"]) == 20)
for row in P["inputs"]:
    physical = M["archive"]["path"] if row == M["original"] else row["path"]
    checked(row, physical)
for rec in report["input_records"]:
    old = rec["original"]
    check("input map belongs to plan", old in P["inputs"])
    if old == M["original"]:
        check("exact historical single source mapping", rec["observation"] == "AUTHORIZED_HISTORICAL_TEST_BEFORE" and rec["archive"] == M["archive"] and rec["current_after"] == report["source_generation"]["after"]["original"])
    else:
        check("immutable same physical input", rec["observation"] == "CURRENT_EXACT")
check("report input count", len(report["input_records"]) == 20)
after = before
check("exact five substitutions count", len(P["exact_source_change"]["changes"]) == 5)
for row in P["exact_source_change"]["changes"]:
    old, new = row["old"].encode(), row["new"].encode()
    check("unique approved old fragment", after.count(old) == 1 and before.count(old) == 1)
    after = after.replace(old, new, 1)
expected = P["exact_source_change"]["derived_expected_after"]
check("derived after identity", len(after) == expected["bytes"] == 254132 and hashlib.sha256(after).hexdigest() == expected["sha256"] == "ebf1e58187dc14fb607f8b6506284fd64532cbef1b41931740c216eba50367bb")
target = Path(M["original"]["path"])
for path in (target, I / "prepared-test-source.txt", I / "after-test.py"):
    check("exact complete after bytes " + str(path), path.read_bytes() == after)
    check("after mode " + str(path), path.lstat().st_mode == M["mode"])
check("old prefix retained", before[:168003] == after[:168003] and hashlib.sha256(after[:168003]).hexdigest() == "66b6c373123299b52f17a6946dd7a77a0d2962b31ce6391261a93f8b01f0612f")
AG = report["source_generation"]["after"]
check("full actual after generation base64", checked(AG["original"]) == checked(AG["archive"]) == base64.b64decode(AG["base64"], validate=True) == after and AG["mode"] == M["mode"])
diff = "".join(difflib.unified_diff(before.decode().splitlines(keepends=True), after.decode().splitlines(keepends=True), fromfile=str(target), tofile=str(I / "prepared-test-source.txt")))
check("complete diff reconstruction", (I / "limited.diff").read_bytes() == diff.encode())
hunks = "".join("@@\n" if line.startswith("@@ ") else line for line in diff.splitlines(keepends=True)[2:])
patch = "*** Begin Patch\n*** Update File: " + str(target) + "\n" + hunks + "*** End Patch"
check("native complete arguments reconstruct exact changes", N["arguments"] == (I / "proposed-test.native.patch").read_text() == patch)
check("honest native result fields", N["actual_tool_return"] == {} and all(N[k] is None for k in ("numeric_exit", "independent_stdout", "independent_stderr")))
check("aggregate exact native identity", A["native"] == {k:N[k] for k in ("arguments", "actual_tool_return", "numeric_exit", "independent_stdout", "independent_stderr")})
check("three actual finite source receipts", [(x["id"], x["actual_tool_return"]["chunk_id"], x["actual_tool_return"]["exit_code"]) for x in A["records"]] == [("contract_read", "a018aa", 0), ("candidate_preparation", "6d7d82", 0), ("after_evidence", "530507", 0)])
check("immediate preparation CAS receipt", N["source_preparation"] == {k:A["records"][1][k] for k in ("invocation", "actual_tool_return")})
idx = json.loads(checked(next(x for x in P["inputs"] if x["path"].endswith("/wait_memory_failure/before/source-index.json"))))
check("exact source and protected denominator", len(idx["sources"]) == 27 and len(idx["authority_before"]["protected"]) == 211)
for row in idx["sources"]:
    physical = checked(row["physical"])
    check("source full historical base64", physical == base64.b64decode(row["base64"], validate=True) and len(physical) == row["bytes"] and hashlib.sha256(physical).hexdigest() == row["sha256"])
    if row["path"] == str(target):
        check("only designated current source generation", physical == before and target.read_bytes() == after)
    else:
        check("other current source complete bytes and mode", checked(row) == physical and Path(row["path"]).lstat().st_mode == row["mode"])
for row in idx["authority_before"]["protected"]:
    checked(row)
check("no test path exemption from protected", not any(x["path"] == str(target) for x in idx["authority_before"]["protected"]))
check("no behavior budget or state promotion", report["runtime_executed"] is False and report["tests_executed"] is False and report["new_budget"] == 0 and report["roles_STATE_PHASE_changed"] is False and report["T2_complete"] is False and report["T12_complete"] is False and A["runtime_executed"] is False)
for key in ("plan", "release", "candidate", "native_receipt", "native_patch", "limited_diff", "source_preparation_before"):
    checked(report[key])
result = {"round": "R274", "status": "ROOT_SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED" if all(c["passed"] for c in checks) else "ROOT_SOURCE_FAILED", "checks": checks, "source_generation": {"before": M["original"], "physical_before": M["archive"], "full_before_manifest": P["before_manifest"], "after": AG["original"], "physical_after": AG["archive"]}, "native_reconstruction": "Exact complete diff and one native UpdateFile arguments reconstructed from five approved unique substitutions; original actual {} retained, numeric/streams null.", "runtime_authorized": 0, "T2_complete": False, "T12_complete": False}
if not all(c["passed"] for c in checks):
    print(json.dumps({"status": result["status"], "failed": [c for c in checks if not c["passed"]]}, ensure_ascii=False))
    raise SystemExit(2)
out = D / "root-independent-source-acceptance.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "checks": len(checks), "acceptance": pin(out)}, ensure_ascii=False))
