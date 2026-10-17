"""Read receipts and preserve R84 stopped CPU evidence; no verification reruns."""
import hashlib
import json
import os
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

out = Path(__file__).resolve().parent
repo = Path.cwd()
plan = json.loads((out.parent / "plan.json").read_text())
stamp = datetime.now(timezone.utc).isoformat()


def pin(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(repo)) if path.is_relative_to(repo) else str(path),
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def save(name, value):
    with (out / name).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


changed = plan["scope"]["modify"][0]
owned = [changed, *plan["scope"]["protect_other_P2_owned"]]
assert (repo / changed).read_bytes() == (out / "source-after" / changed).read_bytes()
checks = []
for old in plan["inputs"]:
    actual = pin(repo / old["path"])
    checks.append({**actual, "expected_before_sha256": old["sha256"],
                   "matches_original": actual["sha256"] == old["sha256"],
                   "authorized_changed_source": old["path"] == changed})
assert all(row["matches_original"] or row["authorized_changed_source"] for row in checks)
save("input-check-after.json", {"time_utc": stamp, "inputs": checks,
                               "unchanged_protected_inputs": 49,
                               "changed_only_authorized_source": True})
freeze = {"time_utc": stamp, "status": "FROZEN_AWAITING_NEXT_ASTRA",
          "sources": [pin(repo / path) for path in owned]}
save("source-freeze.json", freeze)

results = {}
for name, spec in plan["verification"].items():
    if not isinstance(spec, dict) or "argv" not in spec:
        continue
    receipt = json.loads((out / f"{name}.command-result.json").read_text())
    assert receipt["argv"] == spec["argv"] and receipt["runs"] == 1
    results[name] = receipt
assert all(results[name]["exit_code"] == 0 for name in (
    "formatter", "ruff_check", "ruff_format_check", "mypy"))
assert results["GREEN"]["exit_code"] == 1

cases = []
for node in ET.parse(out / "GREEN.junit.xml").getroot().iter("testcase"):
    outcome = "passed"
    detail = None
    for kind in ("failure", "error", "skipped"):
        item = node.find(kind)
        if item is not None:
            outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[kind]
            detail = {"message": item.get("message"), "text": item.text}
            break
    cases.append({"node": node.get("classname") + "::" + node.get("name"),
                  "time_s": node.get("time"), "outcome": outcome, "detail": detail})
counts = Counter(row["outcome"] for row in cases)
assert len(cases) == len({row["node"] for row in cases}) == 94
assert counts == {"passed": 93, "failed": 1}
save("test-outcomes.json", {"unique_cases": 94, "passed": 93, "failed": 1,
                           "errors": 0, "skipped": 0, "cases": cases})

temp = Path("/tmp/bigsmall-t12-p2-green")
destination = out / "local-cpu-originals" / "GREEN"
destination.mkdir(parents=True, exist_ok=False)
files, links, directories = [], [], []
for parent, dirs, names in os.walk(temp, followlinks=False):
    parent = Path(parent)
    relative = parent.relative_to(temp)
    target_parent = destination / relative
    target_parent.mkdir(parents=True, exist_ok=True)
    directories.append(str(relative))
    for name in [*dirs, *names]:
        original = parent / name
        target = target_parent / name
        if original.is_symlink():
            link = os.readlink(original)
            target.symlink_to(link)
            links.append({"original": str(original), "copy": str(target.relative_to(repo)),
                          "link_target": link})
        elif original.is_file():
            with target.open("xb") as stream:
                stream.write(original.read_bytes())
            orig_pin, copy_pin = pin(original), pin(target)
            assert orig_pin["sha256"] == copy_pin["sha256"]
            files.append({"original": str(original), "copy": copy_pin["path"],
                          "relative_path": str(original.relative_to(temp)),
                          "sha256": orig_pin["sha256"], "bytes": orig_pin["bytes"]})
suffixes = Counter(Path(row["relative_path"]).suffix or "<none>" for row in files)
cpu = {"scope": "All files and symlinks in the sole R84 inherited GREEN basetemp",
       "original_temp_retained": str(temp), "copy_root": str(destination.relative_to(repo)),
       "files": files, "file_count": len(files), "bytes": sum(row["bytes"] for row in files),
       "directories": directories, "symlinks": links, "suffix_counts": dict(suffixes),
       "partial_failed_case_included": True, "all_copies_byte_identical": True,
       "pytest_unique_case_denominator": 94, "successful_cases": 93, "failed_cases": 1,
       "new_actual_groups": 0, "actual_calls": 0,
       "old_transport_raw_reused_by_regression_is_new_actual": False,
       "remote_full_raw_database_package": False,
       "note": "CPU fixtures are software evidence. Preserve originals and copies; no clean or deletion."}
save("cpu-originals-manifest.json", cpu)
ledger = {"round": 84, "commands": {name: {"allowed": 1, "used": 1, "remaining": 0,
            "exit_code": receipt["exit_code"], "wall_s": receipt["wall_s"],
            "receipt": str((out / (name + ".command-result.json")).relative_to(repo))}
            for name, receipt in results.items()},
          "GREEN": {"inherited_P2_allowance_consumed": 1, "new_additional_runs": 0,
                    "remaining": 0, "passed": 93, "failed": 1},
          "forbidden_repeats_actual": {name: 0 for name in plan["verification"]["forbidden_repeats"]},
          "actual": 0, "network": 0, "Git": 0, "subagents": 0,
          "new_failure_retry_authorized": False}
save("run-ledger.json", ledger)
report = {"round": 84, "status": "STOPPED_R84_P2_GREEN_FIXTURE_PARENT_AWAITING_ASTRA",
          "time_utc": stamp, "author": "/root/sol_t12_p1",
          "requested_model": "gpt-6.1-sol", "requested_reasoning_effort": "high",
          "runtime_model_independently_verified": False,
          "source_freeze": freeze, "original_50_inputs_prechecked": True,
          "protected_49_inputs_unchanged_after": True,
          "restricted_AST_comments_signatures_proof": "restricted-ast-proof.json",
          "cast_basis": "cast-basis.json", "typing_and_static_author_verified": True,
          "software_acceptance_satisfied": False, "independent_review_passed": False,
          "GREEN": {"exit_code": 1, "unique_cases": 94, "passed": 93, "failed": 1,
                    "errors": 0, "skips": 0, "wall_s": results["GREEN"]["wall_s"]},
          "new_failure": {"node": next(row["node"] for row in cases if row["outcome"] == "failed"),
             "error": "FileNotFoundError", "test_line": "tests/test_native_references.py:356",
             "call": "sample(tmp_path / 'contact', 'GRASP')",
             "raw_path": "/tmp/bigsmall-t12-p2-green/test_fixed_goal_zero_reference0/contact/cloud.py",
             "observed_chain": "sample -> role_binding -> path.write_text before parent directory exists",
             "stopped_before": "contact reference creation and forged fixed_goal_coordinate_invariant rejection assertion",
             "source_fix_or_test_retry_performed": False},
          "CPU_denominator": {"unique_cases": 94, "files": len(files), "bytes": cpu["bytes"],
                              "all_copies_byte_identical": True, "manifest": "cpu-originals-manifest.json"},
          "known_support": {"GRASP_mutable_contact_full_future_D": "NOT_SUPPORTED",
                            "full_future_qualification": "UNKNOWN", "native_authority": "UNAVAILABLE",
                            "dependent_nine_group_large_pilot": "STOPPED"},
          "actual_calls": 0, "formal_acceptance": "NOT_ACCEPTED", "Git_calls": 0,
          "next": "ROOT -> actual Astra for new fixture failure; no retry, P3, or product writes pending dispatch",
          "original_P2_reports_RED_mypy_and_freeze": "preserved without writes"}
save("step-report.json", report)
save("failure-receipt.json", {"status": report["status"], "new_failure": report["new_failure"],
                              "GREEN": report["GREEN"], "originals": [pin(out / path) for path in (
                                  "GREEN.command-start.json", "GREEN.command-result.json", "GREEN.stdout.txt",
                                  "GREEN.stderr.txt", "GREEN.junit.xml")], "retries": 0})
text = f"""# P2 Round84 实施停止报告

状态：`{report['status']}`。仅类型修正与三项静态作者验证通过；P2 软件验收未满足，未宣称独审通过。

50 输入实施前全匹配；实施后只有允许的 native_references.py 改动，49 保护输入保持原 SHA。只添加 TYPE_CHECKING 内精确18字段 TypedDict、values 局部注解和有闭合 producer 依据的 arg4 Mapping cast。受限还原后整模块 AST、旧 comments/signatures、18 kwargs 次序/表达式及 digest/constructor 相同。独立 source-before/after 和 source.diff 保存本轮差异；P2 原冻结与 RED/mypy 失败不改写。

| 命令 | 本轮次数 | 实际 exit | wall 秒 |
|---|---:|---:|---:|
"""
for name, receipt in results.items():
    text += f"| {name} | 1 | {receipt['exit_code']} | {receipt['wall_s']:.6f} |\n"
text += f"""
唯一继承 GREEN 消费原 P2 额度：94 个唯一节点，93 通过、1 失败、0 error/skip。失败节点 test_fixed_goal_zero_reference_velocity_is_not_zero_body_velocity 在 test_native_references.py:356 调用 sample(tmp_path / 'contact', 'GRASP')；role_binding 在 contact 父目录不存在时写 cloud.py，原日志保留 FileNotFoundError。此前 body 位移>50mm、合法 fixed reference 坐标速度0、正 TCP 速度、改 execution digest 被拒绝的断言已执行通过；后续 contact 构造与伪造 fixed bool 拒绝断言未执行。不能把整个节点记为通过。

新失败已报 ROOT，未修测试或重跑。formatter、Ruff check、format-check、mypy、GREEN 均剩余0；原 RED/baseline/P1/历史 actual 额外运行0。须先由实际 Astra 规划新的修复与额度。

完整本次 CPU 临时目录含 {len(files)} 个文件、{cpu['bytes']} 字节，全部逐字复制到 local-cpu-originals/GREEN 并有 manifest；失败节点部分文件包括在分母，原 /tmp 目录保留。历史 transport raw 仅由既有回归读取，不是新真实观察。manifest/报告不冒充完整远端 raw/database 包。

GRASP/full future D 缺失仍 NOT_SUPPORTED；future qualification UNKNOWN、native authority UNAVAILABLE，依赖九组/大批量暂停。actual/native/model/network/Git/子代理均0，正式研究未验收。全部产品源静止，不启动 P3；等待 ROOT/Astra 后续派单及不同作者审查。
"""
(out / "step-report.md").write_text(text)
with (out / "progress.md").open("a") as stream:
    stream.write(f"\n唯一 GREEN 结束 exit1：94 unique /93 pass /1 fail /0 error/skip。contact 夹具父目录未创建，FileNotFoundError；新失败已停报 ROOT，未修测试/重跑，原 GREEN 额度剩余0。源冻结已保存，49 protected pins不变，完整 CPU 原件 {len(files)} files/{cpu['bytes']} bytes 全复制核同。step-report.md/json、failure-receipt、run-ledger、cpu-originals-manifest 完成。全部主树产品源静止，不启动 P3，等待实际 Astra。\n")
local = [row["copy"] for row in files] + [row["copy"] for row in links]
(out / "local-evidence-paths.txt").write_text("\n".join(local) + "\n")
bounded = sorted(path for path in out.rglob("*") if path.is_file()
                 and "local-cpu-originals" not in path.parts)
delivery = [changed, *[str(path.relative_to(repo)) for path in bounded],
            str((out / "delivery-paths.txt").relative_to(repo)),
            str((out / "report-evidence-pins.json").relative_to(repo))]
(out / "delivery-paths.txt").write_text("\n".join(sorted(set(delivery))) + "\n")
save("report-evidence-pins.json", {"bounded_files": [pin(path) for path in bounded],
                                 "delivery_index": pin(out / "delivery-paths.txt"),
                                 "local_CPU_bytes_indexed_by": "cpu-originals-manifest.json"})
print(json.dumps({"status": report["status"], "files": len(files), "bytes": cpu["bytes"],
                  "source_sha256": freeze["sources"][0]["sha256"], "protected_pins": 49,
                  "GREEN": report["GREEN"]}, ensure_ascii=False))
