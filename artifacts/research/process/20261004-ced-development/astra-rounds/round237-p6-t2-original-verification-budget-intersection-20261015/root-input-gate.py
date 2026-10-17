from pathlib import Path
import base64
import copy
import hashlib
import json

R = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
D = R / "artifacts/research/process/20261004-ced-development/astra-rounds/round237-p6-t2-original-verification-budget-intersection-20261015"
checks = []
records = []

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()

def identity(record):
    return {key: record[key] for key in ("path", "bytes", "sha256")}

def pin(path):
    path = Path(path)
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

def check(value, label):
    checks.append({"check": label, "pass": bool(value)})
    if not value:
        raise ValueError(label)

def fixed(record):
    path = Path(record["path"])
    check(not path.is_symlink() and pin(path) == identity(record), "identity " + str(path))
    records.append(identity(record))

def save(path, value):
    raw = encoded(value)
    with path.open("xb") as stream:
        check(stream.write(raw) == len(raw), "fullwrite " + str(path))
    check(path.read_bytes() == raw, "readback " + str(path))

for name, length, sha in (
    ("plan.json", 26101, "aedf64900ea6a9e3d67c1a7af45edb7c950dfe1acda3f698fe48641c3e1ff08f"),
    ("plan.md", 3574, "fd59baa018799a1c89f74241a23ca4d5b2fae479c11f3a7793d5243c34816a6d"),
    ("input-observation.json", 230364, "c8f5cbdc7961de4c0351265fe64b7aebb69c60e9e7ea5096707d05fcdd7a059d"),
    ("metadata-schema-supplement.json", 5742, "5e2bd7351ab3164a2855a21803310077064513c627b70489f638933e0ece4e22"),
    ("metadata-schema-supplement.md", 1346, "4b520714d43fce5f12be50d411f3a61d12bb00b14c42854f47f4dc04b17f3666"),
):
    fixed({"path": str(D / name), "bytes": length, "sha256": sha})
plan = json.loads((D / "plan.json").read_bytes())
observation = json.loads((D / "input-observation.json").read_bytes())
supplement = json.loads((D / "metadata-schema-supplement.json").read_bytes())
check(plan["actual_model"] == observation["actual_model"] == supplement["actual_model"] == "gpt-6-astra", "actual Astra plans")
check("case_pins" not in observation, "no invented alias")
check([len(observation[key]) for key in ("inputs", "current_sources", "protected", "retained_databases", "trace_pins")] == [24, 27, 211, 18, 3], "finite observed sets")
check(len(observation["checks"]) == 313 and observation["all_match"] is True and all(item["match"] is True for item in observation["checks"]), "recorded observation checks")
check(all(isinstance(item, str) for item in observation["source_reads"]), "observed source read strings")
for record in supplement["inputs"] + observation["inputs"] + observation["current_sources"] + observation["protected"] + observation["trace_pins"]:
    fixed(record)
for database in observation["retained_databases"]:
    fixed(database["pin"])
    check(len(database["sidecars"]) == 3, "three retained sidecars")
    for sidecar in database["sidecars"]:
        path = Path(sidecar["path"])
        check(sidecar["exists"] is False and not path.exists() and not path.is_symlink(), "absent historical sidecar " + str(path))
baseline_path = R / "artifacts/research/process/20261004-ced-development/astra-rounds/round235-p6-t2-bootstrap-json-and-startup-prerequisites-20261015/implementation/baseline/source-index.json"
baseline = json.loads(baseline_path.read_bytes())
check(len(baseline["sources"]) == 27, "current physical baseline 27")
current = {record["path"]: identity(record) for record in observation["current_sources"]}
check({record["path"] for record in baseline["sources"]} == set(current), "baseline source path set")
for record in baseline["sources"]:
    path = Path(record["path"])
    archive = baseline_path.parent / "sources" / path.relative_to(R)
    raw = base64.b64decode(record["base64"], validate=True)
    check(identity(record) == current[str(path)] and raw == path.read_bytes() == archive.read_bytes(), "full before bytes/base64/archive " + str(path))
    records.append(pin(archive))
check([command["id"] for command in plan["commands"]] == ["baseline", "ruff", "red"], "three exact original slots")
for command in plan["commands"]:
    check((command["total"], command["used"], command["remaining"], command["state"]) == (1, 0, 1, "HELD"), "unspent original slot " + command["id"])
new_names = ("input-check.json", "source-gate.json", "root-command-ledger.json", "command-ledger.json", "script-gate.json", "root-activation.json", "metadata-schema-supplement-step-report.json")
new_paths = [D / name for name in new_names]
new_paths += [Path(name) for name in plan["scope"]["new_author_scripts"]]
new_paths += [D / "implementation" / name for name in ("baseline", "ruff", "red")]
new_paths += [D / "implementation" / (name + "-outer-" + stream + ".txt") for name in ("baseline", "ruff", "red") for stream in ("stdout", "stderr")]
new_paths.append(Path("/tmp/bigsmall-p6-r237-red"))
for path in new_paths:
    check(not path.exists() and not path.is_symlink(), "exclusive absent " + str(path))
records = list({(record["path"], record["bytes"], record["sha256"]): record for record in records}.values())
input_check = {
    "schema_version": "bigsmall.r237.root-input-check.v1", "status": "SOURCE_PREPARATION_ONLY",
    "checks": checks.copy(), "all_pass": all(item["pass"] for item in checks),
    "input_records": records, "full_plan_read_chunk": "3d6103", "full_observation_semantics_read_chunk": "fee5a9",
    "metadata_supplement_full_read_chunk": "d7984a", "failed_display_remains_failed": True,
    "source_count": 27, "protected_count": 211, "retained_database_count": 18, "absent_sidecar_count": 54,
    "product_execution_released": False, "T2_complete": False,
}
save(D / "input-check.json", input_check)
source_gate = {
    "schema_version": "bigsmall.r237.source-gate.v1", "status": "SOURCE_PREPARATION_ONLY",
    "input_check": pin(D / "input-check.json"), "input_records": records, "product_before": plan["inputs"]["current_product"],
    "product_files": plan["scope"]["product_files"], "source_preparation_authorized": True,
    "execution_released": False, "T2_complete": False,
}
save(D / "source-gate.json", source_gate)
root = {"schema_version": "bigsmall.r237.root-command-ledger.v1", "role": "ROOT", "commands": {item["id"]: copy.deepcopy(item) for item in plan["commands"]}, "no_retry": True, "old_budget_resets": 0}
author = {"schema_version": "bigsmall.r237.command-ledger.v1", "role": "sole_source_author", "author": "/root/p6_stage_b_sol", "model": "gpt-6.1-sol", "commands": {item["id"]: copy.deepcopy(item) for item in plan["commands"]}, "no_retry": True, "old_budget_resets": 0}
save(D / "root-command-ledger.json", root)
save(D / "command-ledger.json", author)
save(D / "script-gate.json", {"schema_version": "bigsmall.r237.script-gate.v1", "commands": {}, "execution_released": False})
activation = {
    "schema_version": "bigsmall.r237.root-activation.v1", "status": "SOURCE_PREPARATION_ONLY",
    "plan": pin(D / "plan.json"), "input_check": pin(D / "input-check.json"), "source_gate": pin(D / "source-gate.json"),
    "sole_author": "/root/p6_stage_b_sol", "product_scope": plan["scope"], "execution_released": False,
    "raw_policy_and_original_references_unchanged": True, "T2_complete": False,
}
save(D / "root-activation.json", activation)
save(D / "metadata-schema-supplement-step-report.json", {
    "schema_version": "bigsmall.r237.metadata-schema-step.v1", "status": "CORRECT_OBSERVED_SCHEMA_GATE_PASSED",
    "failed_display": supplement["inputs"][0], "failed_actual": supplement["actual_failure"],
    "supplement": pin(D / "metadata-schema-supplement.json"), "input_check": pin(D / "input-check.json"),
    "fixed_inputs": len(records), "checks": len(checks), "all_pass": all(item["pass"] for item in checks),
    "slots_added": 0, "product_execution_released": False, "T2_complete": False,
})
print(json.dumps({"round": "R237", "status": "SOURCE_PREPARATION_ONLY", "checks": len(checks), "all_pass": all(item["pass"] for item in checks), "fixed_inputs": len(records), "controls": [pin(D / name) for name in new_names], "slots_used": 0, "slots_remaining": 3, "execution_released": False}, ensure_ascii=False))
