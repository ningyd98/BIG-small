"""Preserve both R92 unexpected failures; no verification or product repair."""
import difflib
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
stamp = datetime.now(timezone.utc).isoformat()


def pin(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(repo)) if path.is_relative_to(repo) else str(path),
            "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def save(name, value):
    with (out / name).open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


trace = f'''Traceback (most recent call last):
  File "{out}/prove-scope.py", line 83, in <module>
    assert dump(a) == dump(reverted)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError
'''
(out / "scope-proof.tool-output.txt").write_text(trace)
proof_failure = {
    "command": [".venv/bin/python", str((out / "prove-scope.py").relative_to(repo))],
    "observed_exec_exit_code": 1, "exec_wall_time_seconds": 0.000008104,
    "observed_output": pin(out / "scope-proof.tool-output.txt"),
    "original_capture": "Preserved verbatim original exec tool output; separate subprocess stdout/stderr/start receipt was not recorded for this evidence helper",
    "reruns": 0, "restricted_scope_proof_passed": False,
    "root_cause": "UNCLASSIFIED_AWAITING_ACTUAL_ASTRA",
}
save("scope-proof.exec-observed-result.json", proof_failure)
source_rows, diff = [], []
for name in plan["scope"]["owned"]:
    source = Path(name)
    destination = out / "source-after" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    before = (out / "source-before" / name).read_text()
    after = source.read_text()
    source_rows.append(pin(source))
    diff.extend(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                   fromfile="before/" + name, tofile="after/" + name))
(out / "source.diff").write_text("".join(diff))
freeze = {"time_utc": stamp, "status": "FROZEN_NEEDS_NEXT_ACTUAL_ASTRA",
          "sources": source_rows, "all_product_sources_static": True,
          "restricted_AST_proof_passed": False}
save("source-freeze.json", freeze)
checks = []
for old in plan["input_pins"]:
    row = pin(Path(old["path"]))
    checks.append({**row, "expected_original_sha256": old["sha256"],
                   "matches_original": row["sha256"] == old["sha256"],
                   "owned_changed": old["path"] in plan["scope"]["owned"]})
assert all(row["matches_original"] or row["owned_changed"] for row in checks)
save("input-check-after.json", {"inputs": checks, "34_protected_pins_unchanged": True,
                               "old_P3_and_public_originals_unchanged": True})
cases = []
for node in ET.parse(out / "RED.junit.xml").getroot().iter("testcase"):
    outcome = "passed"
    detail = None
    for kind in ("failure", "error", "skipped"):
        entry = node.find(kind)
        if entry is not None:
            outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[kind]
            detail = {"message": entry.get("message"), "text": entry.text}
            break
    cases.append({"node": node.get("classname") + "::" + node.get("name"),
                  "outcome": outcome, "time_s": node.get("time"), "detail": detail})
assert len(cases) == len({row["node"] for row in cases}) == 11
assert Counter(row["outcome"] for row in cases) == {"passed": 8, "failed": 3}
save("test-outcomes.json", {"RED_unique_cases": 11, "passed_controls": 8,
                           "expected_failures": 3, "errors": 0, "skips": 0, "cases": cases})
temp = Path("/tmp/bigsmall-t12-p3-r92-red")
copy_root = out / "local-cpu-originals" / "RED"
copy_root.mkdir(parents=True, exist_ok=False)
files, links, directories, wire_receipts = [], [], [], []
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
            if name == "receipt.json":
                data = json.loads(original.read_text())
                if data.get("scope") == "CPU_SIMULATED_HTTP":
                    wire_receipts.append({"original_path": str(original), **data})
inference = [row for row in wire_receipts if row["endpoint"] in ("completions", "chat")]
cpu = {"files": files, "file_count": len(files), "bytes": sum(row["bytes"] for row in files),
       "directories": directories, "symlinks": links,
       "suffix_counts": dict(Counter(Path(row["relative_path"]).suffix or "<none>" for row in files)),
       "case_denominator": 11, "expected_failed_cases": 3, "passed_control_cases": 8,
       "partial_failed_case_wire_files_preserved": True,
       "all_copies_byte_identical": True, "original_temp_retained": str(temp),
       "CPU_simulated_HTTP_open_count": len(wire_receipts),
       "CPU_simulated_inference_count": len(inference),
       "CPU_simulated_inference_statuses": dict(Counter(row["status"] for row in inference)),
       "CPU_simulated_sent_inference_bytes": sum(row["sent_bytes"] for row in inference),
       "CPU_simulated_received_inference_bytes": sum(row["received_bytes"] for row in inference),
       "wire_receipts": wire_receipts, "actual_model_or_network_requests": 0,
       "full_remote_raw_database_package": False}
save("cpu-originals-manifest.json", cpu)
receipts = {name: json.loads((out / (name + ".command-result.json")).read_text())
            for name in ("RED", "formatter", "ruff_check")}
ledger = {"commands": {name: {"allowed": 1,
            "used": 1 if name in receipts else 0, "remaining": 0 if name in receipts else 1,
            "actual_exit_code": receipts[name]["exit_code"] if name in receipts else None}
            for name in plan["verification"]["commands"]},
          "scope_proof_helper_runs": 1, "scope_proof_helper_exit": 1,
          "sequence_deviation": "Ruff executed in same sequential exec after scope proof failed. Author error; no further commands after Ruff failure",
          "additional_or_repeat_commands": 0, "GREEN_unspent": True,
          "actual_network_model_render_physics": 0, "Git": 0, "subagents": 0}
save("run-ledger.json", ledger)
failure = {"status": "NEEDS_ASTRA_R92_SCOPE_PROOF_AND_IMPORT_ORDER",
           "scope_proof": proof_failure,
           "ruff": {"receipt": pin(out / "ruff_check.command-result.json"),
                    "stdout": pin(out / "ruff_check.stdout.txt"),
                    "stderr": pin(out / "ruff_check.stderr.txt"), "actual_exit": 1,
                    "diagnostic": "I001 tests/test_rgbd_role_models.py:1154 local import block"},
           "retries_or_repairs_after_failures": 0, "remaining": ledger["commands"],
           "author_sequence_deviation": ledger["sequence_deviation"]}
save("failure-receipt.json", failure)
report = {"round": 92, "status": failure["status"], "author": "/root/sol_t12_p1",
          "requested_model": "gpt-6.1-sol", "requested_reasoning_effort": "high",
          "runtime_model_independently_verified": False, "software_verified": False,
          "independent_review_passed": False, "actual_or_formal_accepted": False,
          "intended_product_changes_landed": plan["scope"]["product_semantic_allowlist"],
          "RED": {"unique_cases": 11, "expected_failures": 3, "passed_controls": 8,
                  "errors": 0, "skips": 0, "actual_exit": 1},
          "formatter": {"used": 1, "actual_exit": 0, "equivalence_proof_completed": False},
          "scope_proof_failed": True, "Ruff_failed": True,
          "sequence_deviation": ledger["sequence_deviation"],
          "GREEN_format_check_mypy_runs": 0, "source_freeze": freeze,
          "protected34_pins_unchanged": True, "failure_receipt": "failure-receipt.json",
          "new_CPU_originals": {"files": len(files), "bytes": cpu["bytes"],
                                "all_copies_byte_identical": True, "manifest": "cpu-originals-manifest.json"},
          "simulated_request_denominator": {"HTTP_open": len(wire_receipts), "inference": len(inference),
                                            "statuses": cpu["CPU_simulated_inference_statuses"]},
          "P3_original_stop_and_P4_originals": "Unchanged; P4 not passed",
          "cost_ledger": "Unchanged, protected pin; CPU sent timeout/retry control passed, no actual billing",
          "role_actual": "NOT_RUN, future cold+3warm requires P8 source freeze and ROOT dispatch",
          "native_or_physical_qualification": "NOT_ESTABLISHED; old Max grasp v1 not new v2 acceptance",
          "next": "ROOT -> actual Astra for both new failures; all sources static, no R93/P4 repair or unapproved retry",
          "Git_network_model_renderer_physics_subagents": 0}
save("step-report.json", report)
(out / "step-report.md").write_text(f"""# P3 Round92 双失败停止报告

状态：`{failure['status']}`。39输入pins/计划MD/JSON/授权/P4终态匹配；ROOT已释放源写窗口，但P4未通过。旧P3停点不覆盖。

六命名函数11case唯一RED：3预期assertion失败（pixel配置、false/true请求字节缺thinking），8保护通过、0error/skip；完整原收据/stdout/stderr/JUnit保留。随后仅三意图产品变更落盘：YAML normalized1000、角色generation thinkFalse、compatible存在think才映射enable_thinking。未改cost ledger/resolver/schema/全局helper/旧断言。

唯一formatter exit0，semantic-after保存。范围证明helper首次在prove-scope.py:83的整模块AST回退相等断言失败，根因尚未分类；本轮没有完成范围/formatter等价证明，不能声称通过。原exec Traceback逐字保存于scope-proof.tool-output.txt；该helper没有独立stdout/stderr/start文件，记录此证据限制，不补造时间。

作者执行顺序失误：同一串行exec在proof失败后仍消费唯一Ruff check。实际exit1，仅tests/test_rgbd_role_models.py:1154局部import I001。两项新失败及顺序偏差已即时报ROOT。现已停止，不排序imports、不修proof、不重跑。format-check、mypy、GREEN均未用，各剩1；RED/formatter/Ruff已用1各剩0，下一轮额度由实际Astra/ROOT明确，不擅自重置。

完整新RED CPU分母：11unique，{len(files)}files/{cpu['bytes']}bytes，包含失败节点部分wire；全部原字节复制并核同，原/tmp保留。HTTP fake open {len(wire_receipts)}，其中模拟inference {len(inference)}，statuses {dict(Counter(row['status'] for row in inference))}；这些是CPU边界替身，实际模型/网络请求0。旧成功35请求仅历史availability，非本轮role/source资格。

34保护pins（含旧P3及成功原件）仍原SHA；5owned完整before/semantic-after/after及diff/freeze保存。全部主树产品静止。软件/独审/actual/physical/formal未验收，role真实4请求等待P8与单独ROOT派单；Git/模型/网络/渲染/physics/子代理0。交ROOT→实际Astra，不抢写P4 R93。
""")
with (out / "progress.md").open("a") as stream:
    stream.write(f"\nSTOP：scope proof首次Assert失败（line83，未归因），作者同一exec误续Ruff实际exit1/I001局部imports，已如实告ROOT；不修不重跑。format-check/mypy/GREEN0次剩1，RED/formatter/Ruff各已用1。5source冻结/完整diff、34pins复核、双失败收据、CPU完整{len(files)}files/{cpu['bytes']}bytes全复制及模拟request分母已保存。未完成范围证明/软件验收，全部产品静止，待下一实际Astra，不能自行修R93。\n")
(out / "local-evidence-paths.txt").write_text("\n".join(row["copy"] for row in files + links) + "\n")
bounded = sorted(path for path in out.rglob("*") if path.is_file() and "local-cpu-originals" not in path.parts)
delivery = [row["path"] for row in source_rows] + [str(path.relative_to(repo)) for path in bounded]
delivery += [str((out / name).relative_to(repo)) for name in ("delivery-paths.txt", "report-evidence-pins.json")]
(out / "delivery-paths.txt").write_text("\n".join(sorted(set(delivery))) + "\n")
save("report-evidence-pins.json", {"bounded_files": [pin(path) for path in bounded],
                                 "delivery_index": pin(out / "delivery-paths.txt"),
                                 "local_CPU_originals_indexed_by": "cpu-originals-manifest.json"})
print(json.dumps({"status": failure["status"], "files": len(files), "bytes": cpu["bytes"],
                  "simulated_HTTP": len(wire_receipts), "simulated_inference": len(inference),
                  "sources": source_rows}, ensure_ascii=False))
