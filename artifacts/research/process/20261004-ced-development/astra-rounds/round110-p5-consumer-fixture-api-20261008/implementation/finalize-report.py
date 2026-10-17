from pathlib import Path
from datetime import datetime, UTC
import difflib
import hashlib
import json
import xml.etree.ElementTree as ET

BASE = Path("artifacts/research/process/20261004-ced-development/astra-rounds")
ROUND = BASE / "round110-p5-consumer-fixture-api-20261008"
IMP = ROUND / "implementation"
PLAN = json.loads((ROUND / "plan.json").read_text())
PRE = json.loads((IMP / "pre-GREEN-freeze.json").read_text())
OLD = BASE / "round107-p5-boundary-fixture-recovery-20261008/implementation"
OLD_FREEZE = json.loads((OLD / "source-freeze.json").read_text())
OLD_SOURCES = {x["path"]: x for x in OLD_FREEZE["sources"]}
REUSE = json.loads((IMP / "reuse-applicability.json").read_text())
NOW = datetime.now(UTC).isoformat()
NAME = "tests/test_operational_windows.py"

def rec(p):
    p = Path(p)
    data = p.read_bytes()
    return {"path": str(p), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def write(name, obj):
    with (IMP / name).open("x") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")

commands = {name: json.loads((IMP / name / "command-result.json").read_text()) for name in ["formatter", "delta_proof", "ruff", "format_check", "green"]}
cases = []
for c in ET.parse(IMP / "green/junit.xml").getroot().iter("testcase"):
    status = "PASS"
    detail = None
    for tag, label in [("failure", "FAIL"), ("error", "ERROR"), ("skipped", "SKIP")]:
        e = c.find(tag)
        if e is not None:
            status = label
            detail = {"message": e.get("message"), "type": e.get("type")}
            break
    cases.append({"nodeid": NAME + "::" + c.get("name"), "classname": c.get("classname"), "status": status, "time_s": c.get("time"), "diagnostic": detail})
counts = {s: sum(c["status"] == s for c in cases) for s in ["PASS", "FAIL", "ERROR", "SKIP"]}
unique = len({c["nodeid"] for c in cases})
passes = [c["nodeid"] for c in cases if c["status"] == "PASS"]
old_passes = REUSE["reused_30_nodeids"]
combined = old_passes + passes
case_set_ok = set(c["nodeid"] for c in cases) == set(REUSE["new_2_required_nodeids"])
verified = counts == {"PASS": 2, "FAIL": 0, "ERROR": 0, "SKIP": 0} and unique == 2 and case_set_ok and len(set(combined)) == 32 and all(x["exit_code"] == 0 for x in commands.values())
status = "AUTHOR_VERIFIED_PENDING_INDEPENDENT_REVIEW" if verified else "NEEDS_ASTRA_AFTER_GREEN_FAILURE"
rows = []
for previous in PRE["items"]:
    path = previous["path"]
    item = rec(path)
    item["matches_pre_GREEN"] = item["sha256"] == previous["sha256"]
    if path == NAME:
        snapshot = IMP / "format-after" / path
    elif path in OLD_SOURCES:
        snapshot = Path(OLD_SOURCES[path]["snapshot"])
    else:
        snapshot = Path(path)
    item.update(snapshot=str(snapshot), snapshot_matches_current=rec(snapshot)["sha256"] == item["sha256"])
    rows.append(item)
stable = all(x["matches_pre_GREEN"] and x["snapshot_matches_current"] for x in rows)
if not stable:
    status = "NEEDS_ASTRA_SOURCE_DRIFT"
write("source-freeze.json", {"status": status, "at_utc": NOW, "items": rows, "count": len(rows), "all_unchanged_since_pre_GREEN": stable, "post_terminal_product_writes": 0, "active_commands": []})
local = "".join(difflib.unified_diff((IMP / "source-before" / NAME).read_text().splitlines(keepends=True), Path(NAME).read_text().splitlines(keepends=True), fromfile="R110-before/" + NAME, tofile="current/" + NAME))
with (IMP / "r110-test-only.diff").open("x") as f:
    f.write(local)
full = []
new = {"src/cloud_edge_robot_arm/vision/operational_windows.py", NAME}
for old in OLD_FREEZE["sources"]:
    path = old["path"]
    before = [] if path in new else (BASE / "round102-p5-preflight-plan-shape-20261008/implementation/source-before" / path).read_text().splitlines(keepends=True)
    full += difflib.unified_diff(before, Path(path).read_text().splitlines(keepends=True), fromfile="P5-before/" + path, tofile="current/" + path)
for fixture in OLD_FREEZE["fixtures"]:
    if not fixture["path"].endswith(".gz"):
        full += difflib.unified_diff([], Path(fixture["path"]).read_text().splitlines(keepends=True), fromfile="/dev/null", tofile="current/" + fixture["path"])
with (IMP / "full-P5-owned.diff").open("x") as f:
    f.write("".join(full))
write("junit-summary.json", {"raw": rec(IMP / "green/junit.xml"), "new_cases": cases, "new_unique": unique, "counts": counts, "expected_nodeids_match": case_set_ok, "old_30_not_rerun": old_passes, "denominator": "New2 plus applicable prior30; no new32 or new92 run"})
write("combined-P5-coverage.json", {"status": status, "new2": passes, "prior30": old_passes, "combined_pass_unique": len(set(combined)), "P5_pass_nodeids": sorted(set(combined)), "proof": rec(IMP / "reuse-applicability.json"), "new_JUnit": rec(IMP / "green/junit.xml"), "old_JUnit": {"path": REUSE["old_raw_JUnit"], "sha256": REUSE["old_JUnit_sha256"]}, "old_OC1": REUSE["OC1_prior_60"], "OC1_rerun": 0, "claim": "32 P5 unique covered across R110 new2 and R107 prior30 only if all passed; OC1 prior60 separately reused"})
write("command-index.json", {"commands": commands, "active_commands": [], "old_commands_not_repeated": True})
write("budget.json", {"at_utc": NOW, "status": status, "commands": {k: {"authorized": 1, "used": 1, "remaining": 0, "exit_code": v["exit_code"]} for k, v in commands.items()}, "active_commands": [], "RED": 0, "import_sort": 0, "full32": 0, "OC1_rerun": 0, "extra_repro_collect_compile_mypy": 0, "actual": 0, "network": 0, "Git": 0, "subagents": 0, "prior_exhausted_budget": rec(OLD / "budget.json")})
cpu = Path("/tmp/bigsmall-p5-r110-green")
raw = []
for p in sorted(cpu.rglob("*")):
    if p.is_symlink():
        raw.append({"path": str(p), "type": "symlink", "target": str(p.readlink())})
    elif p.is_file():
        raw.append(rec(p))
write("new-CPU-reference-manifest.json", {"root": str(cpu), "preserved_in_place": True, "files": raw, "file_count": sum("sha256" in x for x in raw), "historical_CPU": "Referenced, not copied or re-enumerated", "complete_remote_raw_package": False})
legacy = [x for x in PLAN["inputs"] if "round102" in x["path"]]
write("explicit-paths.json", {"final_owned_source_and_fixture_paths": [x["path"] for x in rows], "required_legacy_codec_test_dependency_paths": legacy, "binary_fixture": next(x for x in rows if x["path"].endswith(".gz")), "evidence_root": str(IMP), "Git_owner": "ROOT", "CPU_raw_not_for_Git": str(cpu)})
report = {
    "status": status, "at_utc": NOW, "author": "original GPT-6.1-sol implementation author", "independent_review": "NOT_PERFORMED_BY_AUTHOR",
    "test_change": "Only fields import/standard init-field legacy comprehension and three real datetime.now(UTC) kwargs on original marker calls; no product, fixture or helper edits",
    "new_two": {"unique": unique, **counts, "nodes": cases},
    "prior_thirty": {"nodeids": old_passes, "applicability": rec(IMP / "reuse-applicability.json"), "rerun": 0},
    "P5_combined_unique_PASS": len(set(combined)), "OC1_prior_sixty": REUSE["OC1_prior_60"], "OC1_rerun": 0,
    "claim_rule": "New2 plus applicable old30; never newly run32 or92",
    "five_commands": {k: {"exit_code": v["exit_code"], "start_utc": v["start_utc"], "end_utc": v["end_utc"]} for k, v in commands.items()},
    "source_and_fixture_static": stable, "scope_delta_proof": rec(IMP / "delta-proof-result.json"),
    "historical_evidence": "All original failures including R10732=30PASS2FAIL retained; prior raw/snapshots/pins not recopied or altered.",
    "review_inputs": {"local_diff": str(IMP / "r110-test-only.diff"), "full_P5_diff": str(IMP / "full-P5-owned.diff"), "freeze": str(IMP / "source-freeze.json"), "explicit_paths": str(IMP / "explicit-paths.json")},
    "remaining_gates": ["Different-author full P5 review and ROOT acceptance", "ROOT explicit-path Git delivery including both legacy codec dependencies", "P6 lease/transactions/dispatch and actual/formal are separate and not completed here"],
    "boundaries": ["marker saved CPU pixels NOT_ADMITTED, not new actual/live admission", "prior supervision one-node CPU UTC fixture does not prove real wall delay", "public/replay detached descriptions do not carry live authority"],
    "action": "13 final items static; await ROOT independent review if passing, or actual Astra if any failure."
}
write("step-report.json", report)
with (IMP / "step-report.md").open("x") as f:
    f.write("# R110 P5 作者验证报告\n\n状态：" + status + "。作者未进行不同作者独审。\n\n")
    f.write(f"本轮仅两个精确节点：{unique} unique，{counts['PASS']} PASS / {counts['FAIL']} FAIL / {counts['ERROR']} ERROR / {counts['SKIP']} SKIP。原 R107 30 PASS 按明确 nodeids 与完整 AST 回退证明引用复用，组合 P5 PASS unique 为 {len(set(combined))}。原 OC1 60 PASS 单独引用；不称本轮新跑32或92。\n\n")
    f.write("只改测试：三处 marker 消费者补真实 now=datetime.now(UTC)，legacy args 使用标准 fields、field.init、排除 operational_windows。九产品/三fixture、所有 helpers/其余节点/六其他类别、原assert/decorator/参数均保持。formatter→delta proof→Ruff→formatcheck→two-node GREEN各1；无 I-sort/全32/OC1/旧CPU/旧proof重跑。\n\n")
    f.write("13项最终freeze与pre-GREEN一致：" + str(stable) + "。source-before/semantic-after/format-after、局部与完整P5差异、命令真实argv/UTC/exit/原输出/JUnit、复用nodeids/预算/有限pins与新CPU引用manifest均保存。两legacy codec原件以SHA/路径列明为测试交付依赖，ROOT负责Git；完整CPU原件只保留本地，不冒充远端全raw包。\n\n")
    f.write("软件UTC夹具不证明实际wall延迟，marker诊断旧像素仍NOT_ADMITTED。P6事务/租约/dispatch、actual/formal各自未完成。本轮通过最多AUTHOR_VERIFIED，完整P5仍需不同作者审查与ROOT验收。\n\n全部源/fixture保持静止，等待ROOT。\n")
(IMP / "progress.md").write_text("# R110 当前终态\n\n" + status + f"；新2结果 {counts}，旧30按nodeids/proof复用，组合P5 {len(set(combined))} unique PASS；OC1旧60单独复用。五新额度已耗尽、active=[]、13项静止。详见step-report.md/json，等待ROOT不同作者全P5审查或实际Astra。\n")
files = [
    "input-check.json", "delta-proof.py", "delta-proof-result.json", "reuse-applicability.json",
    "source-freeze.json", "pre-GREEN-freeze.json", "junit-summary.json", "combined-P5-coverage.json",
    "command-index.json", "budget.json", "step-report.md", "step-report.json", "explicit-paths.json",
    "r110-test-only.diff", "full-P5-owned.diff", "new-CPU-reference-manifest.json", "progress.md",
]
pins = [rec(IMP / name) for name in files]
for name in commands:
    pins += [rec(IMP / name / file) for file in ["command-start.json", "command-result.json", "stdout.txt", "stderr.txt"]]
pins += [rec(IMP / "green/junit.xml"), rec(ROUND / "plan.md"), rec(ROUND / "plan.json"), rec(ROUND / "root-activation.json")]
history = [rec(OLD / x) for x in ["source-freeze.json", "budget.json", "step-report.json", "finite-evidence-pins.json", "green/junit.xml"]]
history += [rec(x["path"]) for x in legacy] + [rec(REUSE["OC1_prior_60"]["original_JUnit"])]
write("finite-evidence-pins.json", {"at_utc": NOW, "current": pins, "historical_references_only": history, "final13": rows})
for name in ["step-report.json", "source-freeze.json", "budget.json", "finite-evidence-pins.json", "combined-P5-coverage.json", "r110-test-only.diff", "full-P5-owned.diff", "junit-summary.json", "explicit-paths.json"]:
    print(json.dumps(rec(IMP / name), ensure_ascii=False))
print(json.dumps({"status": status, "new2": counts, "old30": len(old_passes), "combined_P5_unique_PASS": len(set(combined)), "final13_static": stable, "CPU_files": len(raw)}))
