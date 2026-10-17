from pathlib import Path
import hashlib
import json
import re
from datetime import datetime, timezone

base = Path("artifacts/research/process/20261004-ced-development/astra-rounds")
r76 = base / "round76-rw1-lifecycle-evidence-20261007"
r78 = base / "round78-rw1-preflight-schema-20261007"
plan_raw = (r76 / "plan.json").read_bytes()
if hashlib.sha256(plan_raw).hexdigest() != "83120632a674f8aa91ccb45b5d5d3c3fbf36323b0e9516ef84f07c236db433c4":
    raise RuntimeError("R76 plan.json drift: stop for Astra")
d = json.loads(plan_raw)
if d["schema_version"] != "bigsmall.astra.repair-plan.v1" or d["round"] != r76.name:
    raise RuntimeError("unexpected R76 schema/round: stop for Astra")
rows = d["input_pins"]
if type(rows) is not list or len(rows) != 35:
    raise RuntimeError("R76 input_pins must be exactly 35 rows")
required = {"path", "sha256", "bytes", "review_expected_sha256", "matches_review"}
paths = []
for row in rows:
    if type(row) is not dict or set(row) != required:
        raise RuntimeError("R76 entry schema differs")
    if type(row["path"]) is not str or not row["path"]:
        raise RuntimeError("R76 path invalid")
    if type(row["sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None:
        raise RuntimeError("R76 sha256 invalid")
    if type(row["bytes"]) is not int or row["bytes"] < 0:
        raise RuntimeError("R76 byte count invalid")
    paths.append(row["path"])
if len(set(paths)) != 35:
    raise RuntimeError("duplicate R76 input paths")
md_raw = (r76 / "plan.md").read_bytes()
md_sha = hashlib.sha256(md_raw).hexdigest()
if md_sha != d["plan_md_sha256"] or md_sha != "f0b24debf24b17db8f255360b14617807be22a443cc772cf7f58ffa393ef4e0e":
    raise RuntimeError("R76 plan.md hash mismatch")
auth_path = r76 / "root-authorization.json"
if auth_path.exists() or auth_path.is_symlink():
    raise RuntimeError("authorization output collision; do not overwrite")
execution = r78 / "implementation"
execution.mkdir(exist_ok=False)
checks = []
for row in rows:
    p = Path(row["path"])
    try:
        if p.is_symlink() or not p.is_file():
            raise ValueError("pin must name an existing regular non-symlink file")
        raw = p.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        checks.append({"path": row["path"], "expected_sha256": row["sha256"],
                       "actual_sha256": sha, "expected_bytes": row["bytes"],
                       "actual_bytes": len(raw),
                       "matches": sha == row["sha256"] and len(raw) == row["bytes"]})
    except (OSError, ValueError) as error:
        checks.append({"path": row["path"], "matches": False,
                       "error_type": type(error).__name__, "error": str(error)})
result = {"round": r78.name, "checked_at_utc": datetime.now(timezone.utc).isoformat(),
          "input_count": len(checks), "checks": checks,
          "all_match": len(checks) == 35 and all(c["matches"] for c in checks),
          "plan_md_sha256": md_sha, "plan_json_sha256": hashlib.sha256(plan_raw).hexdigest(),
          "product_tests": 0, "actual": 0}
with (execution / "input-check.json").open("x", encoding="utf-8") as handle:
    handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
if not result["all_match"]:
    raise RuntimeError("R76 pin mismatch/missing input recorded; no authorization, next Astra")
# Metadata approval only; ROOT must have reviewed R76/R78 before this one execution.
authorization = {**result, "status": "ROOT_REVIEWED_INPUTS_MATCH_DISPATCH_READY",
                 "recovery_plan": str(r78 / "plan.json"),
                 "implementation_plan": str(r76 / "plan.json"),
                 "requested_implementer_model": "gpt-6.1-sol",
                 "scope": "original R76 only; test allowances unchanged",
                 "actual_authorized": False, "formal_accepted": False}
with auth_path.open("x", encoding="utf-8") as handle:
    handle.write(json.dumps(authorization, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"inputs": 35, "all_match": True, "authorization": str(auth_path)}))
