from pathlib import Path
from datetime import datetime, UTC
import difflib
import hashlib
import json
import xml.etree.ElementTree as ET

BASE = Path("artifacts/research/process/20261004-ced-development/astra-rounds")
ROUND = BASE / "round111-p5-independent-source-drift-20261008"
IMP = ROUND / "implementation"
OLD = BASE / "round110-p5-consumer-fixture-api-20261008/implementation"
PLAN = json.loads((ROUND / "plan.json").read_text())
PRE = json.loads((IMP / "pre-GREEN-freeze.json").read_text())
REUSE = json.loads((IMP / "reuse-applicability.json").read_text())
OLD_FREEZE = {x["path"]: x for x in json.loads((OLD / "source-freeze.json").read_text())["items"]}
NAME = "tests/test_operational_windows.py"
NODE = NAME + "::test_source_and_budget_changes_invalidate_window"
NOW = datetime.now(UTC).isoformat()

def rec(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def write(name, data):
    with (IMP / name).open("x") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

commands = {name: json.loads((IMP / name / "command-result.json").read_text()) for name in ["formatter", "delta_proof", "ruff", "format_check", "green"]}
cases = []
for c in ET.parse(IMP / "green/junit.xml").getroot().iter("testcase"):
    status, diagnostic = "PASS", None
    for tag, label in [("failure", "FAIL"), ("error", "ERROR"), ("skipped", "SKIP")]:
        error = c.find(tag)
        if error is not None:
            status, diagnostic = label, {"message": error.get("message"), "type": error.get("type")}
            break
    cases.append({"nodeid": NAME + "::" + c.get("name"), "status": status, "time_s": c.get("time"), "diagnostic": diagnostic})
counts = {s: sum(c["status"] == s for c in cases) for s in ["PASS", "FAIL", "ERROR", "SKIP"]}
unique = len({x["nodeid"] for x in cases})
raw_root = Path("/tmp/bigsmall-p5-r111-green")
pair_paths = list(raw_root.rglob("case-pair.json"))
pair = json.loads(pair_paths[0].read_text()) if len(pair_paths) == 1 else None
lifecycles = pair["cases"] if pair is not None else []
pair_complete = (
    pair is not None and pair.get("independent_lifecycles") == 2 and
    len(lifecycles) == 2 and [x["mutation"] for x in lifecycles] == ["budget", "source"] and
    len({x["owner_object_id"] for x in lifecycles}) == 2 and
    len({x["startup_nonce"] for x in lifecycles}) == 2 and
    len({x["repository"] for x in lifecycles}) == 2 and
    all(x["baseline"] == "VALID" and x["rejected"] == "UNKNOWN" and x["restored_source_sha256"] == x["registered_source_sha256"] for x in lifecycles)
)
passed = counts == {"PASS": 1, "FAIL": 0, "ERROR": 0, "SKIP": 0} and unique == 1 and cases[0]["nodeid"] == NODE and all(x["exit_code"] == 0 for x in commands.values()) and pair_complete
status = "AUTHOR_VERIFIED_PENDING_C1_INDEPENDENT_CLOSURE" if passed else "NEEDS_ASTRA_AFTER_GREEN_FAILURE"
rows = []
for previous in PRE["items"]:
    name = previous["path"]
    row = rec(name)
    snapshot = IMP / "format-after" / name if name == NAME else Path(OLD_FREEZE[name]["snapshot"])
    row.update(snapshot=str(snapshot), matches_pre_GREEN=row["sha256"] == previous["sha256"], snapshot_matches_current=rec(snapshot)["sha256"] == row["sha256"])
    rows.append(row)
stable = all(x["matches_pre_GREEN"] and x["snapshot_matches_current"] for x in rows)
if not stable:
    status = "NEEDS_ASTRA_SOURCE_DRIFT"
write("source-freeze.json", {"status": status, "at_utc": NOW, "items": rows, "count": len(rows), "all_unchanged_since_pre_GREEN": stable, "post_terminal_product_writes": 0, "active_commands": []})
with (IMP / "r111-single-node.diff").open("x") as f:
    f.write("".join(difflib.unified_diff((IMP / "source-before" / NAME).read_text().splitlines(keepends=True), Path(NAME).read_text().splitlines(keepends=True), fromfile="R111-before/" + NAME, tofile="current/" + NAME)))
full = []
new = {"src/cloud_edge_robot_arm/vision/operational_windows.py", NAME}
for row in rows:
    name = row["path"]
    if name.endswith(".gz"):
        continue
    if name.startswith("tests/fixtures/") or name in new:
        before = []
    else:
        before = (BASE / "round102-p5-preflight-plan-shape-20261008/implementation/source-before" / name).read_text().splitlines(keepends=True)
    full += difflib.unified_diff(before, Path(name).read_text().splitlines(keepends=True), fromfile="P5-before/" + name, tofile="current/" + name)
with (IMP / "full-P5-owned.diff").open("x") as f:
    f.write("".join(full))
prior31 = REUSE["combined_prior31_nodeids"]
new_pass = [x["nodeid"] for x in cases if x["status"] == "PASS"]
combined = prior31 + new_pass
write("junit-summary.json", {"raw_JUnit": rec(IMP / "green/junit.xml"), "new_unique": unique, "counts": counts, "cases": cases, "actual_worker_lifecycles": len(lifecycles), "pair_assertions_completed": pair_complete, "denominator": "New1 pytest node /2 independent lifecycles + prior31 applicable; no new32/92"})
lifecycle_files = [rec(p) for p in raw_root.rglob("drift-case-result.json")]
write("two-lifecycle-evidence.json", {"status": "BOTH_INDEPENDENT_LIFECYCLES_COMPLETED" if pair_complete else "INCOMPLETE", "case_pair": rec(pair_paths[0]) if len(pair_paths) == 1 else None, "pair_raw": pair, "case_receipts": lifecycle_files, "check_basis": "Parse original test artifacts only; GREEN executes baseline/notclosed, sole mutation, actual rejection, finally restore, existing close exactly once and independent owner/nonce/repo assertions.", "fresh_case_roots": [str(Path(x["repository"]).parent) for x in lifecycles], "CPU_only": True})
write("combined-P5-coverage.json", {"status": status, "new1_nodeids": new_pass, "R107_prior29": REUSE["R107_prior29_nodeids"], "R110_prior2": REUSE["R110_prior2_nodeids"], "combined_PASS_unique": len(set(combined)), "all_PASS_nodeids": sorted(set(combined)), "original_C1_old_PASS_kept_not_reused": REUSE["prior_C1_PASS_preserved_but_not_reused"], "reuse_proof": rec(IMP / "reuse-applicability.json"), "actual_lifecycles_in_new1": len(lifecycles), "OC1_prior60": REUSE["OC1_prior60"], "claim": "New1 +31 applicable old nodes; no new32/92"})
write("budget.json", {"status": status, "at_utc": NOW, "commands": {k: {"authorized": 1, "used": 1, "remaining": 0, "exit_code": v["exit_code"]} for k, v in commands.items()}, "active_commands": [], "RED": 0, "import_sort": 0, "full32": 0, "OC1_rerun": 0, "extra_preflight_proof_repro_collect_compile_mypy": 0, "actual": 0, "network": 0, "Git": 0, "subagents": 0, "prior_budget": rec(OLD / "budget.json")})
write("command-index.json", {"commands": commands, "active_commands": [], "old_commands_not_repeated": True})
cpu = []
for p in sorted(raw_root.rglob("*")):
    if p.is_symlink():
        cpu.append({"path": str(p), "relative_path": str(p.relative_to(raw_root)), "type": "symlink", "target": str(p.readlink())})
    elif p.is_file():
        cpu.append({**rec(p), "relative_path": str(p.relative_to(raw_root))})
write("new-CPU-reference-manifest.json", {"root": str(raw_root), "preserved_in_place": True, "file_count": sum("sha256" in x for x in cpu), "files": cpu, "historical_CPU": "Preserved and referenced; not copied or re-enumerated", "remote_complete_raw": False})
write("explicit-paths.json", {"final13_source_fixture_paths": [x["path"] for x in rows], "legacy_codec_test_dependency_paths": REUSE["legacy_sources"], "CPU_cases": [str(Path(x["repository"]).parent) for x in lifecycles], "evidence_root": str(IMP), "Git_owner": "ROOT", "CPU_DB_raw_not_for_Git": True})
report = {
    "status": status, "at_utc": NOW, "author": "original GPT-6.1-sol implementation author",
    "independent_review": "Full R110 review identified C1; author validation cannot close independent-review gate",
    "scope": "Only original source-and-budget test node; fixed2 case roots/context, actual new owner/window VALID before distinct sole mutation, exact finally restoration, distinct owner/nonce/repository assertions; no product, fixture, helper, other31 node change",
    "new_execution": {"pytest_unique": unique, "counts": counts, "actual_worker_lifecycles": len(lifecycles), "pair_complete": pair_complete, "cases": lifecycles},
    "prior31": prior31, "combined_P5_PASS_unique": len(set(combined)),
    "old_C1_PASS": "Preserved original result but excluded from reuse; it was insufficient independent file-drift coverage.",
    "OC1_prior60": REUSE["OC1_prior60"], "OC1_rerun": 0, "denominator": "New1 pytest /2 workers + prior31; not new32/92",
    "commands": {k: {"exit_code": v["exit_code"], "start_utc": v["start_utc"], "end_utc": v["end_utc"]} for k, v in commands.items()},
    "final13_static": stable,
    "original_CPU": "All old failures/receipts and CPU retained; only new tree referenced with relative paths/bytes/SHA, no new history copies",
    "remaining_gates": ["Different-author C1 closure and ROOT P5 acceptance", "ROOT explicit-path Git", "P6 real lease/transaction/dispatch, actual/native/formal separate"],
    "artifacts": {"local_diff": str(IMP / "r111-single-node.diff"), "full_P5_diff": str(IMP / "full-P5-owned.diff"), "freeze": str(IMP / "source-freeze.json"), "lifecycles": str(IMP / "two-lifecycle-evidence.json"), "old31": str(IMP / "reuse-applicability.json")},
    "action": "All source/fixtures static. Await ROOT independent closure if author-verified, otherwise actual Astra; no self-fix/rerun."
}
write("step-report.json", report)
with (IMP / "step-report.md").open("x") as f:
    f.write("# R111 P5 C1 作者验证报告\n\n状态：" + status + "。作者不自行关闭不同作者审查门。\n\n")
    f.write(f"本轮新 {unique} unique pytest 节点，{counts}；实际完成 {len(lifecycles)} 个独立真实软件 worker 生命周期。budget/source 各有新工作根、SQLite/source与patch context，原始 case-pair/case receipts 见 two-lifecycle-evidence.json。两次基线 VALID、调用前未closed、单一突变 UNKNOWN、finally恢复、close一次及owner/nonce/repo独立断言由新节点实际执行。\n\n")
    f.write(f"原 R107 29 节点＋R110 2 节点按明确nodeids/全模块单节点回退证明复用，组合P5为 {len(set(combined))} unique PASS。原C1旧PASS仍保持，但不再冒充独立文件负控覆盖。OC1原60仅引用，未重跑；不称新32/92。\n\n")
    f.write("只改原一个函数，九产品/三fixture/shared helpers/其他31节点、全部原其他assert/decorator/参数不变；formatter→delta→Ruff→formatcheck→单node GREEN各一次，无额外preflight/proof/full32/OC1/repro。13项最终freeze静止："+str(stable)+"，五新预算耗尽，无在途。\n\n")
    f.write("source-before/semantic-after/format-after、局部与全P5差异、实际命令/UTC/原输出/JUnit、31适用清单、相对路径CPU/DB字节hash索引及有限pins已保留。临时device.py仅CPU注册一致性负控，不授设备/模型/硬件source资格。原历史不覆写/复制，Git只由ROOT后续有限交付。\n\n")
    f.write("仍待原不同作者闭合C1与ROOT P5验收。P6、actual/native/formal界限不变。所有主树源/fixture保持静止。\n")
(IMP / "progress.md").write_text("# R111 当前终态\n\n"+status+f"。新1节点结果 {counts}，实际2worker病例完成={pair_complete}；旧31适用复用、组合P5{len(set(combined))} unique PASS。13项静止、五新额度耗尽、无在途。等待不同作者C1 closure及ROOT验收，未自称review通过。\n")
files = ["input-check.json", "delta-proof.py", "delta-proof-result.json", "reuse-applicability.json", "pre-GREEN-freeze.json", "source-freeze.json", "budget.json", "command-index.json", "junit-summary.json", "two-lifecycle-evidence.json", "combined-P5-coverage.json", "explicit-paths.json", "step-report.md", "step-report.json", "progress.md", "r111-single-node.diff", "full-P5-owned.diff", "new-CPU-reference-manifest.json"]
pins = [rec(IMP / x) for x in files]
for name in commands:
    pins += [rec(IMP / name / x) for x in ["command-start.json", "command-result.json", "stdout.txt", "stderr.txt"]]
pins += [rec(IMP / "green/junit.xml"), rec(ROUND / "plan.md"), rec(ROUND / "plan.json"), rec(ROUND / "root-activation.json")]
history = [rec(OLD / x) for x in ["source-freeze.json", "budget.json", "step-report.json", "finite-evidence-pins.json", "combined-P5-coverage.json", "green/junit.xml"]]
history += [rec(x["path"]) for x in REUSE["legacy_sources"]]
write("finite-evidence-pins.json", {"at_utc": NOW, "current": pins, "historical_references_only": history, "final13": rows})
for name in ["step-report.json", "source-freeze.json", "budget.json", "finite-evidence-pins.json", "two-lifecycle-evidence.json", "combined-P5-coverage.json", "r111-single-node.diff", "full-P5-owned.diff", "junit-summary.json"]:
    print(json.dumps(rec(IMP / name), ensure_ascii=False))
print(json.dumps({"status": status, "new1": counts, "old31": len(prior31), "combined_unique_PASS": len(set(combined)), "lifecycles": len(lifecycles), "pair_complete": pair_complete, "final13_static": stable, "CPU_files": len(cpu)}))
