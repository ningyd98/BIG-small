"""R85 bounded evidence preservation, without extra validation commands."""
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

repo = Path.cwd()
out = Path(__file__).resolve().parent
plan = json.loads((out.parent / "plan.json").read_text())
r84 = out.parent.parent / "round84-p2-native-types-20261007" / "implementation"
stamp = datetime.now(timezone.utc).isoformat()
changed = plan["repair_contract"]["only_file"]


def pin(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(repo)) if path.is_relative_to(repo) else str(path),
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def save(name, value):
    with (out / name).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


assert (repo / changed).read_bytes() == (out / "source-after" / changed).read_bytes()
rows = []
for old in plan["inputs"]:
    actual = pin(repo / old["path"])
    rows.append({**actual, "original_sha256": old["sha256"],
                 "matches_original": actual["sha256"] == old["sha256"],
                 "authorized_changed_test": old["path"] == changed})
assert len(rows) == 40 and all(row["matches_original"] or row["authorized_changed_test"] for row in rows)
save("input-check-after.json", {"inputs": rows, "protected39_unchanged": True,
                               "only_authorized_test_changed": True})
sources = [pin(repo / old["path"]) for old in json.loads((r84 / "source-freeze.json").read_text())["sources"]]
save("source-freeze.json", {"time_utc": stamp, "status": "AUTHOR_VERIFIED_AWAITING_ROOT_INDEPENDENT_REVIEW",
                           "sources": sources, "all_main_tree_product_sources_static_after": True})
receipts = {}
for name in ("ruff_check", "ruff_format_check", "targeted_GREEN"):
    receipt = json.loads((out / (name + ".command-result.json")).read_text())
    assert receipt["exit_code"] == 0 and receipt["runs"] == 1
    assert receipt["argv"] == plan["verification"][name]["argv"]
    receipts[name] = receipt
new_cases = list(ET.parse(out / "targeted_GREEN.junit.xml").getroot().iter("testcase"))
assert len(new_cases) == 1 and all(new_cases[0].find(kind) is None for kind in ("failure", "error", "skipped"))
new_node = new_cases[0].get("classname") + "::" + new_cases[0].get("name")
old_cases = json.loads((r84 / "test-outcomes.json").read_text())["cases"]
passing = [row["node"] for row in old_cases if row["outcome"] == "passed"]
failed = [row["node"] for row in old_cases if row["outcome"] == "failed"]
planned = [row["classname"] + "::" + row["name"] for row in plan["evidence_reuse"]["93_passed_nodes"]]
assert len(passing) == len(planned) == 93 and set(passing) == set(planned)
assert failed == [new_node] and len(set(passing + [new_node])) == 94
coverage = {"claim": "R84 original93 passing evidence remains applicable + R85 affected1 passes",
            "fresh_full94_run": False, "R85_unique_cases": 1, "R85_passed": 1,
            "cross_round_unique_cases": 94, "retained_passing_nodes": passing,
            "repaired_node": new_node,
            "original93_evidence": [pin(r84 / name) for name in (
                "GREEN.junit.xml", "GREEN.stdout.txt", "GREEN.command-result.json", "test-outcomes.json")],
            "basis": plan["evidence_reuse"]["reuse_basis"],
            "final_contact_assertion_reached": "Whole non-skipped test passed; original unconditional contact construction and pytest.raises(ValueError) statement preserved",
            "runtime_instrumentation_or_extra_probe": False}
save("cross-round-coverage.json", coverage)
temp = Path("/tmp/bigsmall-t12-p2-round85-contact")
copy_root = out / "local-cpu-originals" / "targeted_GREEN"
copy_root.mkdir(parents=True, exist_ok=False)
files, links, directories = [], [], []
for parent, dirs, names in os.walk(temp, followlinks=False):
    parent = Path(parent)
    relative = parent.relative_to(temp)
    target_parent = copy_root / relative
    target_parent.mkdir(parents=True, exist_ok=True)
    directories.append(str(relative))
    for name in [*dirs, *names]:
        original, target = parent / name, target_parent / name
        if original.is_symlink():
            link = os.readlink(original)
            target.symlink_to(link)
            links.append({"original": str(original), "copy": str(target.relative_to(repo)), "target": link})
        elif original.is_file():
            with target.open("xb") as stream:
                stream.write(original.read_bytes())
            first, second = pin(original), pin(target)
            assert first["sha256"] == second["sha256"]
            files.append({"original": str(original), "copy": second["path"],
                          "relative_path": str(original.relative_to(temp)),
                          "sha256": first["sha256"], "bytes": first["bytes"]})
cpu = {"files": files, "file_count": len(files), "bytes": sum(row["bytes"] for row in files),
       "directories": directories, "symlinks": links,
       "suffix_counts": dict(Counter(Path(row["relative_path"]).suffix or "<none>" for row in files)),
       "original_temp_retained": str(temp), "all_copies_byte_identical": True,
       "case_denominator": 1, "passed_cases": 1, "failed_or_skipped_cases": 0,
       "old_R84_CPU": {"manifest": pin(r84 / "cpu-originals-manifest.json"),
                       "files": 799, "bytes": 34846709, "new_recopy_or_large_tree_rehash": False},
       "new_actual_calls": 0, "full_remote_raw_database_package": False}
save("cpu-originals-manifest.json", cpu)
ledger = {"commands": {name: {"allowed": 1, "used": 1, "remaining": 0,
                             "actual_exit": receipt["exit_code"], "wall_s": receipt["wall_s"]}
                         for name, receipt in receipts.items()},
          "forbidden_repeats_actual": {name: 0 for name in plan["verification"]["no_repeat"]},
          "formatter": 0, "actual": 0, "network": 0, "Git": 0, "subagents": 0,
          "original_P2_GREEN94_remaining": 0}
save("run-ledger.json", ledger)
report = {"round": 85, "status": "AUTHOR_SOFTWARE_VERIFIED_AWAITING_DIFFERENT_AUTHOR_REVIEW",
          "author": "/root/sol_t12_p1", "requested_model": "gpt-6.1-sol",
          "requested_reasoning_effort": "high", "runtime_model_independently_verified": False,
          "change": "Only local (tmp_path / 'contact').mkdir() before existing sample call in named test",
          "only_test_changed": True, "protected39_pins_unchanged": True,
          "proof": "restricted-ast-proof.json", "sources": sources,
          "commands": receipts, "coverage": coverage["claim"], "new_targeted_case_passed": True,
          "original93_evidence_applicable": True, "cross_round_unique_coverage": 94,
          "fresh_full94_run": False, "CPU_files": len(files), "CPU_bytes": cpu["bytes"],
          "CPU_all_copies_byte_identical": True, "old_R84_CPU_originals_unchanged": True,
          "original_RED_type_failure_GREEN_fixture_failure": "Preserved, not rewritten or rerun",
          "R84_production_static_and_mypy": "Reused unchanged source bytes, no mypy repeat",
          "known_support": "GRASP/full future D NOT_SUPPORTED; native UNKNOWN/UNAVAILABLE; dependent batch stop",
          "independent_review_passed_by_author": False, "actual_calls": 0,
          "formal_acceptance": "NOT_ACCEPTED", "Git_calls": 0,
          "next": "Freeze all product sources; ROOT independent final review and scoped delivery; no P3/P4/actual/Git"}
save("step-report.json", report)
md = """# P2 Round85 作者验证报告

状态：作者软件验证完成，等待不同作者终审。仅在命名失败测试原 contact sample 前新增 `(tmp_path / "contact").mkdir()`；无 parents/exist_ok，不改产品、共用 fixture、任何原断言或调用顺序。

实施前40 pins及计划/授权SHA全匹配。实施后其余39 pins不变，五源冻结见 source-freeze.json。删除唯一登记 mkdir Expr 后，完整 AST(type_comments=True)恢复原模块；其余精确bytes、comments、签名、assert/raises、参数化和fixture完全保持。source-before/after、source.diff及restricted-ast-proof独立保存。

| 验证 | 次数 | 实际exit | wall秒 |
|---|---:|---:|---:|
"""
for name, receipt in receipts.items():
    md += f"| {name} | 1 | {receipt['exit_code']} | {receipt['wall_s']:.6f} |\n"
md += f"""
唯一受影响完整节点1pass、0failure/error/skip；保留原无条件contact构造及伪造fixedflag拒绝断言，整个节点通过证明这些原语句已执行。跨轮覆盖：R84原93例通过证据仍适用＋R85修复后受影响1例通过，合计94个唯一节点。本轮未全跑94例。R84生产静态/mypy沿用未变source字节；formatter/mypy/RED/原93/全94/P1重复均0。

本轮唯一CPU temp完整分母 {len(files)} files/{cpu['bytes']} bytes，全部原字节保存于local-cpu-originals/targeted_GREEN；原/tmp保留。原R84 799 files/34,846,709 bytes仅引用冻结manifest，不重写/重复制；原P2 RED、mypy类型失败和R84 GREEN夹具失败原件保留。清单不冒充完整远端raw/database复现包。

GRASP/full future D缺真实支持仍NOT_SUPPORTED；native UNKNOWN/UNAVAILABLE、依赖批量暂停。实际运行/网络/模型/渲染/physics/Git/子代理新增0，正式研究未验收。作者不宣称独审通过。当前五源静止，不启动P3/P4；交ROOT终审与明确路径交付。
"""
(out / "step-report.md").write_text(md)
with (out / "progress.md").open("a") as stream:
    stream.write(f"\n唯一targeted GREEN完成exit0，1pass/0fail/error/skip，contact原伪fixedflag拒绝已到达。原93通过复用＋新1通过覆盖94unique，未全跑94。39保护pins不变，五源freeze已保存；完整新CPU {len(files)} files/{cpu['bytes']} bytes逐字复制核同，旧799原件只读引用。报告/账本/交付索引完成，全部产品静止，等待ROOT不同作者终审；不P3/P4/actual/Git。\n")
(out / "local-evidence-paths.txt").write_text("\n".join(row["copy"] for row in files + links) + "\n")
bounded = sorted(path for path in out.rglob("*") if path.is_file() and "local-cpu-originals" not in path.parts)
delivery = [row["path"] for row in sources] + [str(path.relative_to(repo)) for path in bounded]
delivery += [str((out / name).relative_to(repo)) for name in ("delivery-paths.txt", "report-evidence-pins.json")]
(out / "delivery-paths.txt").write_text("\n".join(sorted(set(delivery))) + "\n")
save("report-evidence-pins.json", {"bounded_files": [pin(path) for path in bounded],
                                 "delivery_index": pin(out / "delivery-paths.txt"),
                                 "CPU_bytes_indexed_by": "cpu-originals-manifest.json"})
print(json.dumps({"status": report["status"], "CPU_files": len(files), "CPU_bytes": cpu["bytes"],
                  "sources": sources, "coverage": report["coverage"]}, ensure_ascii=False))
