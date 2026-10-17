import hashlib
import json
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

out = Path(__file__).resolve().parent
plan = json.loads((out.parent / "plan.json").read_text())
owned = set(json.loads((out / "registered-scope-recipe.json").read_text()))

def pin(path):
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

def junit(stage):
    cases = []
    for node in ET.parse(out / (stage + ".junit.xml")).getroot().iter("testcase"):
        cases.append({"node": node.attrib.get("classname", "") + "::" + node.attrib["name"],
                      "status": "FAIL" if node.find("failure") is not None else
                                "ERROR" if node.find("error") is not None else
                                "SKIP" if node.find("skipped") is not None else "PASS"})
    assert len({case["node"] for case in cases}) == len(cases)
    counts = {key: sum(case["status"] == key for case in cases) for key in ("PASS", "FAIL", "ERROR", "SKIP")}
    return {"unique": len(cases), "counts": counts, "cases": cases}

commands = []
order = ["RED", "formatter", "proof", "ruff_check", "format_check", "mypy", "GREEN"]
previous_end = None
for name in order:
    start = json.loads((out / (name + ".command-start.json")).read_text())
    result = json.loads((out / (name + ".command-result.json")).read_text())
    assert result["exit_code"] == (1 if name == "RED" else 0), name
    if previous_end is not None:
        assert datetime.fromisoformat(start["start_utc"]) > previous_end, "command gate order"
    previous_end = datetime.fromisoformat(result["end_utc"])
    commands.append({"name": name, "invocations": 1, **start, **result})
red = junit("RED"); green = junit("GREEN")
assert red["unique"] == 16 and red["counts"] == {"PASS": 12, "FAIL": 4, "ERROR": 0, "SKIP": 0}
assert green["unique"] == 31 and green["counts"] == {"PASS": 31, "FAIL": 0, "ERROR": 0, "SKIP": 0}
assert {row["node"] for row in red["cases"]}.issubset({row["node"] for row in green["cases"]})
freeze = json.loads((out / "source-freeze.json").read_text())
for saved in freeze["files"]:
    actual = pin(Path(saved["path"]))
    assert actual == saved and Path(saved["path"]).read_bytes() == (out / "source-after" / saved["path"]).read_bytes()
freeze["state"] = "AUTHOR_VERIFIED_PENDING_INDEPENDENT_REVIEW"
freeze["frozen_at_utc"] = datetime.now(UTC).isoformat()
(out / "source-freeze.json").write_text(json.dumps(freeze, indent=2))
inputs = []
for row in plan["input_pins"]:
    assert type(row) is dict and type(row["path"]) is str and type(row["bytes"]) is int
    actual = pin(Path(row["path"]))
    same = actual["sha256"] == row["sha256"] and actual["bytes"] == row["bytes"]
    assert same or row["path"] in owned, row["path"]
    inputs.append({"path": row["path"], "state": "UNCHANGED" if same else "AUTHORIZED_OWNED_DELTA", "before": row, "after": actual})
(out / "input-check-after.json").write_text(json.dumps({"checked": len(inputs), "protected_unchanged": sum(row["state"] == "UNCHANGED" for row in inputs), "files": inputs}, indent=2))
cpu = {stage: json.loads((out / (stage + ".cpu-manifest.json")).read_text()) for stage in ("RED", "GREEN")}
report = {
    "round": "R93", "status": freeze["state"], "author": "/root/sol_t12_p1", "requested_model": "gpt-6.1-sol/high",
    "generated_at_utc": datetime.now(UTC).isoformat(), "authorization": pin(out.parent / "root-software-authorization.json"),
    "scope": sorted(owned), "source_freeze": freeze, "commands": commands, "unique_denominators": {"RED": red, "GREEN": green},
    "proof": "registered exact Path replacement scope; other product AST and old test definitions preserved except approved opt-in fixture; separate full formatter AST/comments/signatures equality with type-ignore tags and statement binding preserved",
    "cpu_originals": {stage: {key: value for key, value in data.items() if key != "files"} for stage, data in cpu.items()},
    "complete_cpu_regular_files": sum(data["regular_file_count"] for data in cpu.values()),
    "complete_cpu_regular_bytes": sum(data["total_regular_bytes"] for data in cpu.values()),
    "protected_input_pins_unchanged": 50,
    "actual": {"R93_actual": "NOT_RUN_NOT_AUTHORIZED", "historical_P4_attempt": "FAILED_EXIT1_PRESERVED", "old_external_publicreader_invocations": 0, "new_actual_invocations": 0},
    "remaining_gates": ["Different-author review of exact frozen three sources", "ROOT scoped Git delivery", "P3 software terminal and separate ROOT fresh P4 preflight/actual authorization before any actual execution"],
    "qualification": {"source_scope": "EXCLUDED_SOURCE_ONLY_PREFIX", "formal_accepted": False, "native_authority": "UNAVAILABLE", "UTC_SI_accuracy": "UNVERIFIED", "future_H_D": "UNKNOWN", "geometry_motion": "UNKNOWN", "calibration_groups": 0, "OC3": "NOT_TESTED"},
    "constraints": {"P3_product_edits": 0, "producer_backend_camera_worker_edits": 0, "historical_original_edits": 0, "model_network_actual": 0, "Git": 0, "subagents": 0, "full63_R03_old_suites": 0},
    "portability": "Complete CPU regular bytes and original symlink targets preserved locally; pytest current links retain absolute /tmp targets. No claim of a complete remote reproduction package."
}
(out / "step-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
summary = f'''# R93 P4 软件步骤报告

状态：AUTHOR_VERIFIED_PENDING_INDEPENDENT_REVIEW。仅schema/prefix reader/capture tests三个owned源；P3 R92与历史P4首败保持冻结。新actual/旧external reader/模型/网络/Git/子代理均0。

仅artifact inventory中完整匹配规范路径的instances.i32允许0B，默认source inventory仍必须正整数bytes。reader在pack前精确验证CAPTURE END、frozen auxiliary和source-frame元数据的IDs、signed32、长度、count、availability、labels和passes。所有其他原product AST和旧断言保留；fixture默认行为不变，opt-in经真实decorated cached capture。

唯一RED16：4预期FAIL/12PASS/0ERROR/SKIP，失败原件永久保留。formatter/proof/Ruff/formatcheck/mypy各一次exit0；单独命令逐项核退出，时序证据验证上一门结束后才开始下一门。独立formatter证明完整AST/comments/signatures等价，TypeIgnore先核tag及绑定再规范坐标（本三文件实际0条）。唯一GREEN31：31PASS/0FAIL/ERROR/SKIP，包括16新+15直接受影响旧case；没有63/R03/旧完整套件重跑。

CPU真实cached正链生成catalog/receipt，244events、120steps、3captures、0actions，IDs0/0/76800、instances0/0/307200B、availability false/false/true、passes2/2/3及SHA/source joins一致。它是CPU软件证据，不能替代真实运行/正式研究验收。

CPU分母：RED {cpu['RED']['regular_file_count']}普通文件/{cpu['RED']['total_regular_bytes']}B；GREEN {cpu['GREEN']['regular_file_count']}普通文件/{cpu['GREEN']['total_regular_bytes']}B；总{report['complete_cpu_regular_files']}文件/{report['complete_cpu_regular_bytes']}B，全部逐字复制保存并有完整manifest，原tmp未删。pytest链接原target记录，不冒称可移植远端包。JUnit是唯一case分母，不合并旧轮重跑。53输入复核，50保护输入字节不变，3为已批准owned delta；三source-after与当前源精确一致。

审查入口：source.diff、source-before/、semantic-after/、source-after/、source-freeze.json、scope-proof.py/json、registered-scope-recipe.json、各command-start/result/stdout/stderr、RED/GREEN.junit.xml、cached-cpu-evidence.json、RED/GREEN.cpu-manifest.json、finite-evidence-pins.json。产品源全部静止。不同作者独审、ROOT交付及后续单独真实资源授权尚未完成；最高author验证，不自行宣告review通过。formal false/native unavailable/UTC-SI unverified/future H-D与geometry unknown/calibration_groups0/OC3未验。
'''
(out / "step-report.md").write_text(summary)
(out / "progress.md").write_text(summary)
paths = sorted(str(path.relative_to(Path.cwd())) for path in out.rglob("*") if path.is_file() and not path.is_symlink() and "cpu-originals" not in path.parts and path.name not in {"finite-evidence-pins.json", "explicit-paths.json"})
(out / "explicit-paths.json").write_text(json.dumps({"owned_sources": sorted(owned), "small_evidence_paths": paths, "local_cpu_originals": "cpu-originals/ preserved, excluded from automatic Git path authorization", "Git_authorized_to_author": False}, indent=2))
paths.append(str((out / "explicit-paths.json").relative_to(Path.cwd())))
with (out / "finite-evidence-pins.json").open("x") as file:
    json.dump({"scope": "finite implementation evidence; CPU whole denominator separately pinned in RED/GREEN.cpu-manifest.json", "files": [pin(Path(path)) for path in paths]}, file, indent=2)
print(json.dumps({"status": report["status"], "GREEN": green["counts"], "cpu_files": report["complete_cpu_regular_files"], "cpu_bytes": report["complete_cpu_regular_bytes"], "protected_unchanged": 50}, indent=2))
