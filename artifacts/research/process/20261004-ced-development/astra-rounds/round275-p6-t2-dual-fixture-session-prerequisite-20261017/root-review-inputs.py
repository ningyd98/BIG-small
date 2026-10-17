from pathlib import Path
import base64
import hashlib
import json

D = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round275-p6-t2-dual-fixture-session-prerequisite-20261017")
D274 = D.parent / "round274-p6-t2-wait-fixture-clock-scope-20261017"
R = D.parents[4]
checks = []
def pin(path):
    p = Path(path)
    b = p.read_bytes()
    return {"path": str(p), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
def check(label, value):
    checks.append({"check": label, "passed": bool(value)})

fixed = {
    "plan.md": (2931, "7be888089e02e0caf8ee8646a24d0a2b020b375d4492bdf439b84deb167db5fa"),
    "plan.json": (15665, "983934ca5a5dc3dc2ffd05eafd91a4c02382ce80f45b0b546fd5c6c4ebb498a0"),
    "input-observation.json": (9515, "bbb261aaea6e79364091003c97b422d629279d100d6257798445e370d4f95c59"),
    "planning-actual-tool-returns.json": (68805, "83f4af89190af3f297ae575b9e46febcf87f10e2c485cc3904ec5615f441b2a3"),
    "definition-name-clarification.json": (1569, "15e03e20eb62fe03123cb1307ffb2ce4e2e988b7306f9be4e0325b01f9093764"),
}
for name, expected in fixed.items():
    v = pin(D / name)
    check("R275 artifact " + name, (v["bytes"], v["sha256"]) == expected)
plan = json.loads((D / "plan.json").read_bytes())
obs = json.loads((D / "input-observation.json").read_bytes())
clar = json.loads((D / "definition-name-clarification.json").read_bytes())
check("actual Astra identity", plan["actual_model"] == obs["actual_model"] == "gpt-6-astra")
check("plan observation complete input equality", plan["inputs"] == obs["inputs"] and len(plan["inputs"]) == 22)
check("clarification original hash and exact field", clar["original_plan_sha256"] == fixed["plan.json"][1] and clar["field"] == "R274_independence.requirements[2]" and clar["actual_name"] == "test_memory_sqlite_publication_wait_requires_current_d")
historical = plan["R274_independence"]["historical_test"]
historical_logical = historical["logical"]
check("exact historical mapping original", historical_logical == next(item for item in plan["inputs"] if item["path"] == historical_logical["path"]))
resolved = []
for expected in plan["inputs"]:
    physical = historical["physical"]["path"] if expected == historical_logical else expected["path"]
    actual = pin(physical)
    check("input " + expected["path"], actual["bytes"] == expected["bytes"] and actual["sha256"] == expected["sha256"])
    resolved.append({"expected": expected, "actual_physical": actual, "resolution": "exact R274 full historical before only" if expected == historical_logical else "same immutable physical path"})
manifest = json.loads((D274 / "before/manifest.json").read_bytes())
old = (D274 / "before/test_operational_runtime_closure.py").read_bytes()
check("full before base64 and mode", base64.b64decode(manifest["base64"], validate=True) == old and manifest["mode"] == (D274 / "before/test_operational_runtime_closure.py").stat().st_mode == 33204)
check("all new execution budgets zero", all(plan["budgets"][k] == 0 for k in ("new_runtime", "new_test", "new_static", "new_review", "new_git", "new_SQL")))
current = pin(historical_logical["path"])
result = {"round": "R275", "status": "ROOT_INPUT_REVIEW_PASSED" if all(c["passed"] for c in checks) else "ROOT_INPUT_REVIEW_FAILED", "checks": checks, "resolved_inputs": resolved, "live_test_observation_only": current, "live_after_acceptance": "Separate R274 exact five substitutions and native source proof required; this observation is not acceptance.", "scope": "stdlib physical metadata and bytes only; no product/test/static/SQL/Git", "T2_complete": False}
if not all(c["passed"] for c in checks):
    print(json.dumps({"status": result["status"], "failed": [c for c in checks if not c["passed"]]}, ensure_ascii=False))
    raise SystemExit(2)
out = D / "root-input-review.json"
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": result["status"], "checks": len(checks), "report": pin(out)}, ensure_ascii=False))
