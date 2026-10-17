from pathlib import Path
import base64
import hashlib
import json
import stat

ROOT = Path("/home/ningyd/文档/ChatGPT/BIGsmall")
ROUND = ROOT / "artifacts/research/process/20261004-ced-development/astra-rounds/round289-p6-t2-accepted-runner-validation-continuation-20261017"
FIXED = [
    ("plan.md", 4862, "bb59a11e465ac729e0e1cad6840e7d60e8789fdc174b87e6fa34d472ce71a4a7"),
    ("plan.json", 48642, "4bc64ed58a737cb9f6bbe7386a9937a189b3e1522258e8a85c051bbd8f5fe5fb"),
    ("input-observation.json", 371055, "82c31139a709e11ca78fefaae3bc8df9cda1612a0584e2c391a527b9b1501cf3"),
    ("before/manifest.json", 936330, "4f4e67c3f768db3fda551a9daa9292755e20d29fccf822b032afaa2fdae6749f"),
]
checks = []

def check(label, passed):
    checks.append({"check": label, "passed": bool(passed)})
    if not passed:
        raise AssertionError(label)

def pin(path):
    path = Path(path)
    mode = path.lstat().st_mode
    check("regular " + str(path), stat.S_ISREG(mode) and not path.is_symlink())
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def identity(row):
    return {key: row[key] for key in ("path", "bytes", "sha256")}

def verify(row):
    check("identity " + row["path"], pin(row["path"]) == identity(row))

for name, size, digest in FIXED:
    verify({"path": str(ROUND / name), "bytes": size, "sha256": digest})
plan = json.loads((ROUND / "plan.json").read_bytes())
observation = json.loads((ROUND / "input-observation.json").read_bytes())
before = json.loads((ROUND / "before/manifest.json").read_bytes())
check("actual Astra round", plan["round"] == "R289" and plan["actual_model"] == "gpt-6-astra")
check("32 explicit inputs", len(plan["inputs"]) == 32)
check("observation same inputs", observation["inputs"] == plan["inputs"])
for row in plan["inputs"]:
    verify(row)
check("1059 actual planning checks", len(observation["checks"]) == observation["checks_passed"] == 1059)
check("all planning checks true", all(item["passed"] is True for item in observation["checks"]))
check("seven complete before records", len(before["records"]) == 7)
for row in before["records"]:
    verify(row["original"])
    verify(row["archive"])
    actual = Path(row["original"]["path"]).read_bytes()
    check("full before bytes " + row["original"]["path"], actual == Path(row["archive"]["path"]).read_bytes() == base64.b64decode(row["base64"], validate=True))
    check("full before mode " + row["original"]["path"], Path(row["original"]["path"]).lstat().st_mode == Path(row["archive"]["path"]).lstat().st_mode == row["mode"])
check("27 current source identities", len(observation["current_sources"]) == 27)
for row in observation["current_sources"]:
    verify(row)
    verify(row["physical"])
    check("current full physical " + row["path"], Path(row["path"]).read_bytes() == Path(row["physical"]["path"]).read_bytes())
    check("current mode " + row["path"], Path(row["path"]).lstat().st_mode == row["mode"])
check("no original R285 result", observation["original_result_absent"] is True and not Path(plan["inputs"][17]["path"]).parent.parent.joinpath("result.json").exists())
check("direct process facts remain null", observation["original_child_process_fields"] == {"direct_child_exit": None, "direct_process_group_cleanup": None})
check("no promotion", plan["scope"]["new_runtime_slots"] == 3 and plan["scope"]["new_static_slots"] == plan["scope"]["new_review_slots"] == plan["scope"]["new_Git_slots"] == 0)
check("fresh source paths", all(not Path(value).exists() for value in plan["scope"]["new_sources"]))
check("fresh roles", all(not Path(plan["runner_contract"]["roles"][role]).exists() for role in ("ROOT", "AUTHOR")))
record = {
    "round": "R289",
    "status": "PLAN_AND_CURRENT_INPUTS_ACCEPTED_FOR_SOURCE_PREPARATION_ONLY",
    "plan": pin(ROUND / "plan.json"),
    "observation": pin(ROUND / "input-observation.json"),
    "before_manifest": pin(ROUND / "before/manifest.json"),
    "checks": checks,
    "new_runtime": 0,
    "runtime_release": False,
    "source_gate_still_required": True,
}
output = ROUND / "root-source-preparation-applicability.json"
with output.open("x", encoding="utf-8") as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps({"round": "R289", "status": record["status"], "checks_passed": len(checks), "receipt": pin(output)}, ensure_ascii=False))

