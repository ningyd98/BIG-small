from pathlib import Path
import base64
import hashlib
import json
import stat
D = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round276-p6-t2-first-session-invalidation-capture-20261017")
checks = []
def check(name, value):
    checks.append({"check": name, "passed": bool(value)})
def pin(p):
    p = Path(p)
    b = p.read_bytes()
    return {"path": str(p), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
def checked(row, physical=None):
    p = Path(physical or row["path"])
    b = p.read_bytes()
    check("identity " + str(p), stat.S_ISREG(p.lstat().st_mode) and len(b) == row["bytes"] and hashlib.sha256(b).hexdigest() == row["sha256"])
    return b
fixed = {
"plan.md": (4142, "ca679f3f6ae62be708bb9d6f5e55acc4a7dc9265a8c5f00c072e78c28d228874"),
"plan.json": (48080, "bf3f11ceb390c316021714feffb54775d47bd2dcd5dc6f0ae59f9f8169a1c2a8"),
"input-observation.json": (18102, "418b7a91a16ff867c811fbaabf6aa577a3782145b51c9a4e3b737d07c6322623"),
"planning-actual-tool-returns.json": (94174, "a18e6eb6da6d440ed006a60c0080fd55de2a4fd040f4dfca2c2e2a27fc5b84a2"),
"prerequisite-supplement.json": (5095, "9e1011333681dd85f92d302d995a28c0b28cfc8ee9fac259954fe97f66733374"),
"prerequisite-supplement.md": (718, "d100ebb71b0fcc377ba4f5b4208b399e2de361f7c3122cc2d9059ad9fea38ad0")}
for name, (size, sha) in fixed.items():
    checked({"path": str(D / name), "bytes": size, "sha256": sha})
P = json.loads((D / "plan.json").read_bytes())
O = json.loads((D / "input-observation.json").read_bytes())
S = json.loads((D / "prerequisite-supplement.json").read_bytes())
check("actual Astra identity", P["actual_model"] == O["actual_model"] == S["actual_model"] == "gpt-6-astra")
check("complete fifty inputs equality", P["inputs"] == O["inputs"] and len(P["inputs"]) == 50)
for row in P["inputs"] + S["inputs"]:
    checked(row)
check("supplement matches exact original plan", checked(S["plan"]) == (D / "plan.json").read_bytes() and S["no_budget_change"] is True)
acceptance = json.loads(checked(S["inputs"][0]))
check("R274 actual source acceptance", acceptance["status"] == "ROOT_SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED" and len(acceptance["checks"]) == 429 and all(x["passed"] for x in acceptance["checks"]))
idx = json.loads(checked(next(x for x in P["inputs"] if x["path"] == O["source_authority"]["path"])))
check("source and protected denominators", len(idx["sources"]) == 27 and len(idx["authority_before"]["protected"]) == 211)
old = acceptance["source_generation"]["before"]
new = acceptance["source_generation"]["after"]
for row in idx["sources"]:
    b = checked(row["physical"])
    check("full physical historical source", b == base64.b64decode(row["base64"], validate=True) and len(b) == row["bytes"] and hashlib.sha256(b).hexdigest() == row["sha256"])
    if row["path"] == old["path"]:
        check("only explicit R274 original generation", {k:row[k] for k in ("path", "bytes", "sha256")} == old and b == checked(acceptance["source_generation"]["physical_before"]))
        check("actual R274 after generation", checked(new) == checked(acceptance["source_generation"]["physical_after"]))
    else:
        check("current unchanged source and mode", checked(row) == b and Path(row["path"]).lstat().st_mode == row["mode"])
for row in idx["authority_before"]["protected"]:
    checked(row)
check("exact new commands", list(P["commands"]) == ["wait_memory", "wait_sqlite", "dual_first_invalidation"])
for key, command in P["commands"].items():
    check("finite once " + key, command["authorized"] == 1 and command["used"] == 0 and command["remaining"] == 1 and command["limits"]["attempts"] == 1 and command["limits"]["retries"] == 0)
    check("finite limits " + key, command["limits"]["child_seconds"] == 600 and command["limits"]["cleanup_total_seconds"] == 15 and command["limits"]["faulthandler_seconds"] == 540)
    check("trace only dual " + key, ("r276_session_evidence" in command["child_argv"]) == (key == "dual_first_invalidation"))
check("original source preparation only", all(not Path(p).exists() for p in P["scope"]["new_sources"]))
result = {"round": "R276", "status": "ROOT_INITIAL_PLAN_INPUT_REVIEW_PASSED" if all(x["passed"] for x in checks) else "ROOT_INITIAL_PLAN_INPUT_REVIEW_FAILED", "checks": checks, "plan": pin(D / "plan.json"), "supplement": pin(D / "prerequisite-supplement.json"), "current_test": new, "scope": "Initial input/physical source review only; new runner/plugin review, exact context mapping, source/input/argv gates and individual reservation still required.", "runtime_released": False, "T2_complete": False}
if not all(x["passed"] for x in checks):
    print(json.dumps({"status": result["status"], "failed": [x for x in checks if not x["passed"]]}, ensure_ascii=False))
    raise SystemExit(2)
out = D / "root-initial-plan-input-review.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "checks": len(checks), "report": pin(out)}, ensure_ascii=False))
