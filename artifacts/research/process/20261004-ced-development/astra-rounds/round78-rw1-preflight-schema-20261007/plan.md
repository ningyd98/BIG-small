# Astra Round78 — ROOT 的 R76 输入核对 schema 恢复

仅元数据计划；OC2 Sol 独立实施继续。原失败来自 ROOT 工具 chunk `a59993` 的转录，未重跑：`d.get("inputs", [])` 生成空列表，在 stdin:9 的断言失败、exit1。核对数为 0，未写审批，不能称为哈希不匹配。

实际 R76 使用 `input_pins`：list、35 条，每条键为 `path/sha256/bytes/review_expected_sha256/matches_review`。后两键可为 null，是历史来源字段；当前核对必须使用 sha256 与 bytes。R76 `plan_md_sha256` 与实际 MD 一致：`f0b24debf24b17db8f255360b14617807be22a443cc772cf7f58ffa393ef4e0e`。

## 限定执行

1. ROOT review R78 and original R76; check these three exact plan/instruction SHA. Do not claim semantic approval from hashes alone.
2. Save recovery_python verbatim into fresh R78 implementation script path outside the execution directory (e.g. R78/recover-root-preflight.py); execute once with PYTHONDONTWRITEBYTECODE=1 .venv/bin/python <script>. Capture original stdout/stderr/exit/wall separately. No sandbox_permissions.
3. Directly index input_pins; validate exact schema and 35 unique rows before reads. Use sha256/bytes as actual expectations; nullable matches_review is historical provenance, not a pass predicate. Read only these 35 explicit paths once, no glob/recursive/raw expansion.
4. Write input-check with exclusive creation, then authorization exclusively only if 35/35 match and MD linkage holds. Preserve failure entry without replacing original error. Original R76 product/test budgets remain unchanged; this metadata round adds zero tests/static/actual allowances.
5. Read back new receipt/authorization and report metadata preflight recovered only; any schema drift/missing/hash failure/collision stops affected R76 dispatch for next Astra. No retry, deleting partial output or changing pins to make checks pass.

只准一次修正后 35 路径核对；不改 R76 原计划/产品/测试/原证据，不递归扫描。R76 目录只新增独占的 root-authorization.json，绝不覆盖原文件。通过仅表示元数据前置恢复，R76 软件修复、原次数、actual 门和正式验收仍独立。

## 计划输入

| 路径 | SHA256 |
|---|---|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round76-rw1-lifecycle-evidence-20261007/plan.md` | `f0b24debf24b17db8f255360b14617807be22a443cc772cf7f58ffa393ef4e0e` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round76-rw1-lifecycle-evidence-20261007/plan.json` | `83120632a674f8aa91ccb45b5d5d3c3fbf36323b0e9516ef84f07c236db433c4` |

## 可执行恢复脚本

ROOT 阅读本计划后，将下文保存为本 R78 目录中新的 `recover-root-preflight.py`；使用 `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python <该路径>` 一次执行。该脚本在规划阶段未执行。

```python
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
```
