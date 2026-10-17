from pathlib import Path
from datetime import datetime, UTC
import difflib
import hashlib
import json
import xml.etree.ElementTree as ET

BASE = Path("artifacts/research/process/20261004-ced-development/astra-rounds")
ROUND = BASE / "round107-p5-boundary-fixture-recovery-20261008"
IMP = ROUND / "implementation"
PLAN = json.loads((ROUND / "plan.json").read_text())
PRE = json.loads((IMP / "pre-GREEN-freeze.json").read_text())
OLD = BASE / "round106-p5-domain-schema-completeness-20261008/implementation"
OLD_FREEZE = {x["path"]: x for x in json.loads((OLD / "source-freeze.json").read_text())["sources"]}
NOW = datetime.now(UTC).isoformat()

def rec(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

def write(name, data):
    with (IMP / name).open("x") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

commands = {name: json.loads((IMP / name / "command-result.json").read_text()) for name in [
    "import_sort", "formatter", "delta_fixture_proof", "ruff", "format_check", "green",
]}
cases = []
for item in ET.parse(IMP / "green/junit.xml").getroot().iter("testcase"):
    status = "PASS"
    diagnostic = None
    for tag, label in [("failure", "FAIL"), ("error", "ERROR"), ("skipped", "SKIP")]:
        element = item.find(tag)
        if element is not None:
            status = label
            diagnostic = {"message": element.get("message"), "type": element.get("type")}
            break
    cases.append({"classname": item.get("classname"), "name": item.get("name"), "status": status, "time_s": item.get("time"), "diagnostic": diagnostic})
counts = {label: sum(c["status"] == label for c in cases) for label in ["PASS", "FAIL", "ERROR", "SKIP"]}
unique = len({(c["classname"], c["name"]) for c in cases})
passed = counts == {"PASS": 32, "FAIL": 0, "ERROR": 0, "SKIP": 0} and unique == 32 and all(x["exit_code"] == 0 for x in commands.values())
status = "AUTHOR_VERIFIED_PENDING_INDEPENDENT_REVIEW" if passed else "NEEDS_ASTRA_AFTER_GREEN_FAILURE"
rows = []
for original in PRE["sources"]:
    path = original["path"]
    current = rec(path)
    snapshot = IMP / "format-after" / path if path in PLAN["scope"]["modified_python"] else Path(OLD_FREEZE[path]["snapshot"])
    current.update(snapshot=str(snapshot), matches_pre_GREEN=current["sha256"] == original["sha256"], snapshot_matches_current=rec(snapshot)["sha256"] == current["sha256"])
    rows.append(current)
fixtures = []
for original in PRE["fixtures"]:
    current = rec(original["path"])
    current["matches_pre_GREEN"] = current["sha256"] == original["sha256"]
    fixtures.append(current)
stable = all(x["matches_pre_GREEN"] and x["snapshot_matches_current"] for x in rows) and all(x["matches_pre_GREEN"] for x in fixtures)
if not stable:
    status = "NEEDS_ASTRA_SOURCE_DRIFT"
write("source-freeze.json", {"status": status, "at_utc": NOW, "sources": rows, "fixtures": fixtures, "all_unchanged_since_pre_GREEN": stable, "post_terminal_product_writes": 0, "active_commands": []})
local, full = [], []
new = {"src/cloud_edge_robot_arm/vision/operational_windows.py", "tests/test_operational_windows.py"}
for row in rows:
    name = row["path"]
    current = Path(name).read_text().splitlines(keepends=True)
    if name in PLAN["scope"]["modified_python"]:
        local += difflib.unified_diff((IMP / "source-before" / name).read_text().splitlines(keepends=True), current, fromfile="R107-before/" + name, tofile="current/" + name)
    original = [] if name in new else (BASE / "round102-p5-preflight-plan-shape-20261008/implementation/source-before" / name).read_text().splitlines(keepends=True)
    full += difflib.unified_diff(original, current, fromfile="P5-before/" + name, tofile="current/" + name)
for path in PLAN["scope"]["new_fixture_paths"][1:]:
    full += difflib.unified_diff([], Path(path).read_text().splitlines(keepends=True), fromfile="/dev/null", tofile="current/" + path)
for name, data in [("r107-three-python.diff", "".join(local)), ("full-P5-owned.diff", "".join(full))]:
    with (IMP / name).open("x") as f:
        f.write(data)
write("command-index.json", {"commands": commands, "active_commands": [], "old_commands_not_repeated": True})
write("junit-summary.json", {"raw": rec(IMP / "green/junit.xml"), "total": len(cases), "unique": unique, "counts": counts, "cases": cases, "new_OC1_cases": 0, "prior_OC1_applicable_passes": 60, "denominator": "New32 P5 plus prior60 OC1, never newly run92"})
write("budget.json", {"at_utc": NOW, "status": status, "commands": {k: {"authorized": 1, "used": 1, "remaining": 0, "exit_code": v["exit_code"]} for k, v in commands.items()}, "active_commands": [], "RED": 0, "OC1_rerun": 0, "extra_repro_collect_compile_mypy": 0, "actual": 0, "network": 0, "Git": 0, "subagents": 0, "prior_exhausted_budget_reference": rec(OLD / "budget.json")})
raw = Path("/tmp/bigsmall-p5-r107-green")
raw_rows = []
for path in sorted(raw.rglob("*")):
    if path.is_symlink():
        raw_rows.append({"path": str(path), "type": "symlink", "target": str(path.readlink())})
    elif path.is_file():
        raw_rows.append(rec(path))
write("new-CPU-reference-manifest.json", {"root": str(raw), "preserved_in_place": True, "file_count": sum("sha256" in x for x in raw_rows), "entries": raw_rows, "complete_remote_raw_package": False, "historical_raw": "Preserved and referenced, not copied or re-enumerated"})
existing_owned = [x["path"] for x in PRE["sources"]]
write("explicit-paths.json", {"P5_product_owned": existing_owned, "R107_new_fixtures": PLAN["scope"]["new_fixture_paths"], "evidence_root": str(IMP), "compressed_binary_fixture": fixtures[0], "historical_and_CPU_raw_for_Git": False, "Git_by_ROOT_only": True})
report = {
    "status": status, "at_utc": NOW, "author": "original GPT-6.1-sol implementation author",
    "independent_review": "NOT_PERFORMED_BY_AUTHOR",
    "new_P5": {"total": len(cases), "unique": unique, **counts},
    "original_OC1": PRE["OC1_result_reuse"],
    "six_commands": {k: {"exit_code": v["exit_code"], "start_utc": v["start_utc"], "end_utc": v["end_utc"]} for k, v in commands.items()},
    "scope": "Exact worker type rejection before hashing; normalized untouched bootstrap payload comparison; two stopped=True fixtures; only one supervision CPU datetime context; pinned marker fixture real source/assets/OpenCV checks.",
    "failure_nodes": [x for x in cases if x["status"] != "PASS"],
    "source_and_fixture_static": stable,
    "historical_evidence": "Original RED27, old92 and R10632 failure receipts, original frame/registry/assets/raw unchanged. No old proof, test or preflight rerun.",
    "metadata_recovery": {
        "R108": rec(BASE / "round108-p5-preflight-optional-size-20261008/recovery/preflight/command-result.json"),
        "R109_syntax": rec(BASE / "round109-metadata-authoring-recovery-20261008/sol-recovery/script_syntax/command-result.json"),
        "R109_apply": rec(BASE / "round109-metadata-authoring-recovery-20261008/sol-recovery/apply_semantic/command-result.json"),
        "old_author_failure": rec(ROUND / "author-script-stop/step-report.json"),
        "old_metadata_failure": rec(ROUND / "startup-stop/step-report.json"),
    },
    "software_boundaries": ["supervision UTC fixed only in one CPU node; no proof of wall latency or actual eligibility", "marker diagnostic historical pixels NOT_ADMITTED; not new capture/calibration/live authority", "OC1 old60 reused with unchanged source/test/config hashes; no new92 claim"],
    "review_inputs": {"full_diff": str(IMP / "full-P5-owned.diff"), "local_diff": str(IMP / "r107-three-python.diff"), "freeze": str(IMP / "source-freeze.json"), "budget": str(IMP / "budget.json"), "CPU_refs": str(IMP / "new-CPU-reference-manifest.json")},
    "remaining_gates": ["Different-author full P5 review and ROOT acceptance", "ROOT explicit-path Git delivery", "P6 lease/transactions/dispatch and actual/formal evidence remain distinct"],
    "action": "All product source and three fixtures static; await ROOT. Any failure goes to actual Astra before fix/retry.",
}
write("step-report.json", report)
lines = [
    "# R107 P5 作者步骤报告", "",
    "状态：" + status + "。作者未自行进行不同作者审查。", "",
    f"新完整 P5 JUnit：{len(cases)} 节点、{unique} unique；{counts['PASS']} PASS / {counts['FAIL']} FAIL / {counts['ERROR']} ERROR / {counts['SKIP']} SKIP。原 OC1 60 PASS 仅按未变源/测试/config 引用复用，本轮 OC1 运行 0 次；不称新 92 通过。", "",
    "六项新授权各使用一次，真实 argv/UTC/退出/stdout/stderr/hash 在 command-index.json 与各原收据。原 RED/旧 CPU/旧 proof/成功 preflight 不重跑；R108 可选尺寸恢复与 R109 单层脚本恢复各有独立原收据。两作者工具失败原件保持。", "",
    "限定实现：from_worker 在 hash 前拒绝错误实际类型；bootstrap 从未变 normalized 副本做精确比较；两个 robot_stopped 正例传 stopped=True。supervision 仅一个原节点使用三模块 datetime 临时上下文，真实 SQL/lease/source、UTC 5秒 veto 和原 5/6/D 断言保留。marker 三独立夹具精确 spec SHA、gzip展开原字节，真实 source/assets/OpenCV 检查且 NOT_ADMITTED。", "",
    "软件 UTC 夹具不证明真实 wall 延迟；历史 marker 像素不等于新 actual/live authority/物理 admission。P6 真实租约/事务/dispatch、actual 和 formal 仍是独立门。", "",
    "十源和三夹具 final freeze 与 pre-GREEN 一致：" + str(stable) + "。完整 P5 diff、R107局部 diff、explicit paths、唯一JUnit、有限原件pins及新 CPU 引用 manifest 齐全；新原件留在 /tmp，未再次复制历史 raw。", "",
    "全部源码/夹具保持静止。由 ROOT 安排不同作者全 P5 审查及后续交付；任何新失败先 actual Astra，不自修/重跑。", "",
]
with (IMP / "step-report.md").open("x") as f:
    f.write("\n".join(lines))
(IMP / "progress.md").write_text("# R107 当前终态\n\n" + status + f"：新{unique} unique P5，{counts}。六新命令均已终态且额度耗尽，无在途。十源+三fixture静止，旧OC1只复用60、重跑0。详见 step-report.md/json 与 source-freeze.json；等待ROOT不同作者审查或实际Astra。\n")
current_names = [
    "apply-semantic.py", "semantic-edit-spec.json", "delta-proof.py", "delta-proof-result.json",
    "source-freeze.json", "pre-GREEN-freeze.json", "junit-summary.json", "command-index.json",
    "budget.json", "step-report.md", "step-report.json", "new-CPU-reference-manifest.json",
    "r107-three-python.diff", "full-P5-owned.diff", "explicit-paths.json", "progress.md",
]
current = [rec(IMP / x) for x in current_names]
for name in commands:
    current += [rec(IMP / name / x) for x in ["command-start.json", "command-result.json", "stdout.txt", "stderr.txt"]]
current += [rec(IMP / "green/junit.xml"), rec(ROUND / "plan.md"), rec(ROUND / "plan.json"), rec(ROUND / "fixture-spec.json"), rec(ROUND / "root-activation.json")]
history = [rec(OLD / x) for x in ["source-freeze.json", "budget.json", "step-report.json", "finite-evidence-pins.json"]]
history += [rec(PRE["OC1_result_reuse"]["original_JUnit"])]
write("finite-evidence-pins.json", {"at_utc": NOW, "current": current, "historical_references_only": history, "sources": rows, "fixtures": fixtures})
for name in ["step-report.json", "source-freeze.json", "budget.json", "finite-evidence-pins.json", "full-P5-owned.diff", "r107-three-python.diff", "junit-summary.json", "new-CPU-reference-manifest.json"]:
    print(json.dumps(rec(IMP / name), ensure_ascii=False))
print(json.dumps({"status": status, "counts": counts, "unique": unique, "source_static": stable, "CPU_files": len(raw_rows)}))
