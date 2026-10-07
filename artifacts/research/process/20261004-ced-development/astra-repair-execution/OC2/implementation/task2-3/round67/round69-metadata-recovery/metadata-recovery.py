import json
from pathlib import Path

A = Path("artifacts/research/process/20261004-ced-development")
plan67 = json.loads((A / "astra-rounds/round67-oc2-green-partials/plan.json").read_text())
plan69 = json.loads((A / "astra-rounds/round69-oc2-preflight-metadata/plan.json").read_text())
rows = plan67["observed_missing_files"]
expected = plan69["missing_row_contract"]["rows"]
if type(rows) is not list or len(rows) != 11:
    raise ValueError("exact eleven missing path rows required")
paths = []
for row in rows:
    if type(row) is not dict or set(row) != {"path", "observed"}:
        raise ValueError("exact missing row schema required")
    if type(row["path"]) is not str or not row["path"] or row["observed"] != "ABSENT_DO_NOT_FILL":
        raise ValueError("exact original missing path metadata required")
    paths.append(row["path"])
if len(set(paths)) != 11 or rows != expected:
    raise ValueError("registered missing path identities differ")
observations = []
for row in rows:
    target = Path(row["path"])
    try:
        target.lstat()
    except FileNotFoundError:
        observations.append({"path": row["path"], "expected": row["observed"], "actual": "ABSENT_LSTAT_NO_ENTRY"})
    else:
        raise ValueError("original missing path now has directory entry: " + row["path"])
dest = Path(plan69["scope"]["recovery_new_exclusive_root"])
result = {"status": "MISSING_PATH_PASS_COMPLETE", "runs": 1, "count": 11, "observations": observations, "original151_pin_result": "REUSED_NOT_RERUN"}
with (dest / "missing-path-check.json").open("x") as handle:
    handle.write(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
