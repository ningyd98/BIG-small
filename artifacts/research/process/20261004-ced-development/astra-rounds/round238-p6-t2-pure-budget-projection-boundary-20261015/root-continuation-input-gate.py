from pathlib import Path
import base64
import hashlib
import json

R = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
A = R / "artifacts/research/process/20261004-ced-development/astra-rounds"
D = A / "round238-p6-t2-pure-budget-projection-boundary-20261015"
P = A / "round237-p6-t2-original-verification-budget-intersection-20261015"
checks = []
records = []
def enc(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
def ident(record):
    return {key: record[key] for key in ("path", "bytes", "sha256")}
def pin(path):
    path = Path(path); raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
def ck(value, label):
    checks.append({"check": label, "pass": bool(value)})
    if not value:
        raise ValueError(label)
def fixed(record):
    path = Path(record["path"])
    ck(not path.is_symlink() and pin(path) == ident(record), "fixed " + str(path))
    records.append(ident(record))
def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        ck(stream.write(raw) == len(raw), "fullwrite " + str(path))
    ck(path.read_bytes() == raw, "readback " + str(path))
def save(path, value):
    put(path, enc(value))

for name, size, sha in (
    ("plan.md", 2913, "31340433698fb28f1f2207ca5e838809a2d14ceea25043ceb7ee73142fad2ec0"),
    ("plan.json", 15484, "ccf4fe0a79963cad9b99e6ce6946c6c02536809b5dcc7dd46e8bd546d8491e30"),
    ("input-observation.json", 66822, "573db4369f01da40f6d84caba6d8fe6fd52f03dfe4e6476764c5f5a63bac169c"),
):
    fixed({"path": str(D / name), "bytes": size, "sha256": sha})
plan = json.loads((D / "plan.json").read_bytes())
obs = json.loads((D / "input-observation.json").read_bytes())
base = json.loads((P / "plan.json").read_bytes())
original_obs = json.loads((P / "input-observation.json").read_bytes())
original_gate = json.loads((P / "input-check.json").read_bytes())
ck(plan["actual_model"] == obs["actual_model"] == "gpt-6-astra", "actual Astra")
ck(len(obs["inputs"]) == 12 and len(obs["current_source_and_protected_checks"]) == 238, "finite actual sets")
ck(obs["all_match"] is True and all(item["match"] is True for item in obs["current_source_and_protected_checks"]), "all recorded238 match")
for record in obs["inputs"] + obs["current_source_and_protected_checks"] + original_gate["input_records"]:
    fixed(record)
for view in obs["roles_as_of"]:
    fixed(view["pin"])
    actual = json.loads(Path(view["pin"]["path"]).read_bytes())
    ck(set(actual["commands"]) == set(view["commands"]) == {"baseline", "ruff", "red"}, "same three slot keys")
    for name, expected in view["commands"].items():
        command = actual["commands"][name]
        ck({key: command[key] for key in expected} == expected == {"total": 1, "used": 0, "remaining": 1, "state": "HELD"}, "unspent original " + name)
for path, absent in obs["author_scripts_absence"].items():
    ck(absent is True and not Path(path).exists() and not Path(path).is_symlink(), "absent author source " + path)
for database in original_obs["retained_databases"]:
    fixed(database["pin"])
    for item in database["sidecars"]:
        ck(item["exists"] is False and not Path(item["path"]).exists() and not Path(item["path"]).is_symlink(), "old absent sidecar " + item["path"])
names = ("source-gate.json", "script-gate.json", "root-activation.json", "root-command-ledger.json", "command-ledger.json")
before = {}
for name in names:
    path = P / name
    before[name] = {"raw": path.read_bytes(), "pin": pin(path), "mode": path.stat().st_mode & 0o7777}
for name in ("input-check.json", "source-continuation-gate.json", "root-activation.json"):
    ck(not (D / name).exists() and not (D / name).is_symlink(), "new output " + name)
ck(not (D / "before/metadata").exists(), "new complete before directory")
archives = []
for name, item in before.items():
    path = D / "before/metadata" / name
    put(path, item["raw"])
    archives.append({"original": item["pin"], "archive": pin(path), "mode": item["mode"], "base64": base64.b64encode(item["raw"]).decode()})
save(D / "before/metadata/index.json", {"schema_version": "bigsmall.r238.current-control-before.v1", "records": archives})
records = list({(item["path"], item["bytes"], item["sha256"]): item for item in records}.values())
save(D / "input-check.json", {
    "schema_version": "bigsmall.r238.root-input-check.v1", "status": "SOURCE_PREPARATION_ONLY",
    "checks": checks.copy(), "all_pass": all(item["pass"] for item in checks), "input_records_as_of_before": records,
    "mutable_control_resolution": pin(D / "before/metadata/index.json"), "full_plan_read_chunk": "2919ed",
    "full_direct_inputs_and_roles_read_chunk": "fed09e", "execution_released": False, "T2_complete": False,
})
save(D / "source-continuation-gate.json", {
    "schema_version": "bigsmall.r238.source-continuation-gate.v1", "status": "SOURCE_PREPARATION_ONLY",
    "base_contract": pin(P / "plan.json"), "continuation_plan": pin(D / "plan.json"),
    "input_check": pin(D / "input-check.json"), "complete_current_before": pin(D / "before/metadata/index.json"),
    "replacement_boundary": plan["supersedes_only"], "product_contract": plan["contract"],
    "original_three_slots_only": True, "new_slots": 0, "product_execution_released": False, "T2_complete": False,
})
continuation = {"plan": pin(D / "plan.json"), "input_check": pin(D / "input-check.json"), "source_continuation_gate": pin(D / "source-continuation-gate.json"), "source_preparation_only": True}
changes = []
for name in ("source-gate.json", "script-gate.json", "root-activation.json"):
    old = before[name]
    updated = json.loads(old["raw"])
    ck("continuation" not in updated, "new sole continuation key " + name)
    updated["continuation"] = continuation
    raw = enc(updated)
    path = P / name
    ck(path.read_bytes() == old["raw"], "immediate CAS " + name)
    ck(path.write_bytes(raw) == len(raw) and path.read_bytes() == raw, "exact continuation write " + name)
    changes.append({"before": old["pin"], "after": pin(path), "added_key_only": "continuation"})
for name in ("root-command-ledger.json", "command-ledger.json"):
    ck((P / name).read_bytes() == before[name]["raw"], "all six original role views untouched " + name)
save(D / "root-activation.json", {
    "schema_version": "bigsmall.r238.root-activation.v1", "status": "SOURCE_PREPARATION_ONLY",
    "plan": pin(D / "plan.json"), "input_check": pin(D / "input-check.json"),
    "source_continuation_gate": pin(D / "source-continuation-gate.json"), "changes": changes,
    "sole_author": "/root/p6_stage_b_sol", "original_roles_untouched": True, "new_slots": 0,
    "execution_released": False, "T2_complete": False,
})
print(json.dumps({"round": "R238", "status": "SOURCE_PREPARATION_ONLY", "checks": len(checks), "all_pass": all(item["pass"] for item in checks), "fixed_inputs": len(records), "controls": [pin(D / name) for name in ("input-check.json", "source-continuation-gate.json", "root-activation.json")], "updated_R237_gates": changes, "slots_used": 0, "original_slots_remaining": 3, "new_slots": 0, "execution_released": False}, ensure_ascii=False))
