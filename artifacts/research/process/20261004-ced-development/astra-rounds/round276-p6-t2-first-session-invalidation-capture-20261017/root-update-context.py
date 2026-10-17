from pathlib import Path
import base64
import copy
import hashlib
import json
import os
D = Path("/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round276-p6-t2-first-session-invalidation-capture-20261017")
def pin(p):
    p = Path(p)
    b = p.read_bytes()
    return {"path": str(p), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
def checked(row):
    p = Path(row["path"])
    b = p.read_bytes()
    assert len(b) == row["bytes"] and hashlib.sha256(b).hexdigest() == row["sha256"]
    return b
P = json.loads(checked({"path": str(D / "plan.json"), "bytes": 48080, "sha256": "bf3f11ceb390c316021714feffb54775d47bd2dcd5dc6f0ae59f9f8169a1c2a8"}))
S = json.loads(checked({"path": str(D / "prerequisite-supplement.json"), "bytes": 5095, "sha256": "9e1011333681dd85f92d302d995a28c0b28cfc8ee9fac259954fe97f66733374"}))
checked({"path": str(D / "root-initial-plan-input-review.json"), "bytes": 67608, "sha256": "f1e43f82d23123c0fe9b0cff4001822988b6307fbb78d7004cc3bc01892703b8"})
for row in P["inputs"] + S["inputs"]:
    checked(row)
def input_record(round_name, filename):
    hits = [row for row in P["inputs"] + S["inputs"] if Path(row["path"]).name == filename and Path(row["path"]).parent.name.startswith("round" + round_name[1:] + "-")]
    assert len(hits) == 1
    return hits[0]
originals = P["context_update"]["before_inputs"]
assert len(originals) == 2
state_path, phase_path = [Path(row["path"]) for row in originals]
state_before, phase_before = [checked(row) for row in originals]
original = json.loads(state_before)
state = copy.deepcopy(original)
old_r268 = copy.deepcopy(state["planning"]["R268"])
state["planning"]["R268"].update({
    "status": "TWO_DIAGNOSTICS_CAPTURED_BOTH_TESTS_FAILED",
    "previous_planning_state": old_r268,
    "runtime_released": True,
    "commands": {
        "wait_memory_failure": {"authorized": 1, "used": 1, "remaining": 0, "state": "SPENT_DIAGNOSTIC_CAPTURE", "child_exit": 1, "wrapper_exit": 0, "timed_out": False, "elapsed_seconds": 217.1277223950019, "integrity_checks": 358, "acceptance": input_record("R268", "root-wait-memory-independent-acceptance.json"), "result": next(x for x in P["inputs"] if x["path"].endswith("/wait_memory_failure/result.json"))},
        "dual_progress": {"authorized": 1, "used": 1, "remaining": 0, "state": "SPENT_DIAGNOSTIC_CAPTURE", "child_exit": 1, "wrapper_exit": 0, "timed_out": False, "elapsed_seconds": 344.20256431700545, "integrity_checks": 353, "acceptance": input_record("R268", "root-dual-independent-acceptance.json"), "result": next(x for x in P["inputs"] if x["path"].endswith("/dual_progress/result.json"))}
    },
    "actual_findings": {"wait": "Original missing expected raise traceback at test4309; independent accumulated-clock/error-propagation fixture issue later corrected by R274.", "dual": "Original capture reserve_plan failed at helper4017 and lease ingress471 before commit-loss injection; first session invalidation reason unknown.", "resource_observed_attempts": 887, "resource_initialized_observed": 884, "resource_cleanup_observed": 887, "new_retained_DB_count": 6, "limits": "Only the two diagnostics; not full-suite/native/formal evidence. Old GREEN7 remains spent and its timeout cause unknown."},
    "latest_context_manifest_path": str(D / "root-context-update.json"),
    "T2_complete": False, "T12_complete": False, "native_accepted": False, "formal_accepted": False
})
descriptions = {
"R269": "Accepted exact passive whitelist helper-name correction; original frozen plan retained.",
"R270": "Unqualified python read exit127 retained; original abandoned, no optional corrective execution or environment repair.",
"R271": "Original display-cache JSON assembly failure retained; cached assembler abandoned, exact physical reader completed once.",
"R272": "Exact source-only pytest native float ini normalization accepted; original candidate retained.",
"R273": "Unexecuted ROOT gate manifest reference corrected through explicit parent-plan chain; corrected gate passed, no original draft execution."
}
for key, description in descriptions.items():
    state["planning"][key] = {"status": "DISPOSITION_RECORDED", "description": description, "plan": input_record(key, "plan.json"), "step_report": input_record(key, "step-report.json"), "T2_complete": False}
accept = next(x for x in S["inputs"] if x["path"].endswith("/root-independent-source-acceptance.json"))
source_acceptance = json.loads(checked(accept))
assert source_acceptance["status"] == "ROOT_SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED" and all(x["passed"] for x in source_acceptance["checks"])
state["planning"]["R274"] = {"status": "SOURCE_ACCEPTED_BEHAVIOR_UNVERIFIED", "plan": input_record("R274", "plan.json"), "step_report": input_record("R274", "step-report.json"), "source_acceptance": accept, "source_checks": 429, "current_test": source_acceptance["source_generation"]["after"], "scope": "Exactly five wait helper/test substitutions; no dual/product repair.", "T2_complete": False}
state["planning"]["R275"] = {"status": "DISPOSITION_ACCEPTED_FIRST_SESSION_INVALIDATION_UNKNOWN", "plan": input_record("R275", "plan.json"), "step_report": input_record("R275", "step-report.json"), "product_or_dual_fix": False, "new_runtime": 0, "T2_complete": False}
state["planning"]["R276"] = {"status": "PLAN_ACCEPTED_SOURCE_PREPARATION_PENDING", "plan": pin(D / "plan.json"), "supplement": pin(D / "prerequisite-supplement.json"), "initial_input_acceptance": pin(D / "root-initial-plan-input-review.json"), "commands": {key: {field: cmd[field] for field in ("budget_identity", "authorized", "used", "remaining", "state", "kind")} for key, cmd in P["commands"].items()}, "runtime_released": False, "old_budget_reset": False, "context_manifest_path": str(D / "root-context-update.json"), "T2_complete": False, "T12_complete": False, "native_accepted": False, "formal_accepted": False, "Git_authorized": False}
allowed = ["R" + str(i) for i in range(268, 277)]
check_old, check_new = copy.deepcopy(original), copy.deepcopy(state)
for key in allowed:
    check_old["planning"].pop(key, None)
    check_new["planning"].pop(key, None)
assert check_old == check_new
state_after = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode()
steps = [input_record("R" + str(i), "step-report.json") for i in range(269, 276)]
section = "\n\n## R276：R268实际取证结算与R274源码修复（2026-10-17）\n\n"
section += "本节补充此前尚未运行的历史状态。R268两个独立诊断已实际结束：memory等待217.127722秒、dual344.202564秒，均child1/wrapper0，无超时；ROOT分别358与353项完整性检查通过，仅证明证据完整，不代表测试通过。两个槽均用1余0；父GREEN7原失败与600秒超时原件保留，未重置额度。\n\n"
section += "等待用例原异常位于test4309；R274已完成五处限定替换，使时钟筛选只使用本次exercise创建的对象，并将holder异常断言保留在finally。ROOT429项源码/原件/native检查通过，实际test为254132B/ebf1e58187dc14fb607f8b6506284fd64532cbef1b41931740c216eba50367bb，尚无行为通过。完整旧ed602物理原件/base64/mode、26其他源与211保护项均保留。\n\n"
section += "dual在capture的reserve_plan入口已遭会话失效拒绝，早于commit-loss故障注入；最初关闭/撤销/注册条件原因仍未确定。R275不授权猜测修产品。两诊断实际887次资源尝试/884初始化/887观察清理，仅为其实际分母；新4+2数据库及旧数据库/缺失侧文件边界分别保持，无SQL。\n\n"
section += "R269至R273处置原helper命名、ROOT读命令/显示缓存、pytest ini归一化和ROOT清单引用问题，原始失败、冻结候选和实际回执保留。R276新增wait_memory、wait_sqlite行为验证与dual_first_invalidation诊断三个独立once身份，各尚用0余1并HELD；仅在源码/输入/argv门及逐槽预留后串行运行。当前仅计划接受，未准备新脚本、未运行本轮命令；fresh12与Git0仍未放行，T2/T12/native/formal均未通过。\n\n"
section += "证据：\n\n"
for row in [input_record("R268", "root-wait-memory-independent-acceptance.json"), input_record("R268", "root-dual-independent-acceptance.json"), accept] + steps + [pin(D / "plan.json"), pin(D / "prerequisite-supplement.json")]:
    section += "- " + row["path"] + "；" + str(row["bytes"]) + " B；SHA256 " + row["sha256"] + "\n"
phase_after = phase_before + section.encode()
assert phase_after.startswith(phase_before)
folder = D / "before/context/generation001"
folder.mkdir(parents=True, exist_ok=False)
changes = []
for record, before, after in zip(originals, (state_before, phase_before), (state_after, phase_after)):
    target = Path(record["path"])
    mode = target.lstat().st_mode
    assert mode == 33204
    archive = folder / target.name
    with archive.open("xb") as f:
        f.write(before)
    os.chmod(archive, mode & 0o777)
    candidate = folder / ("prepared-" + target.name)
    with candidate.open("xb") as f:
        f.write(after)
    os.chmod(candidate, mode & 0o777)
    assert target.read_bytes() == before and target.lstat().st_mode == mode
    changes.append({"before": {"original": record, "archive": pin(archive), "base64": base64.b64encode(before).decode()}, "after": {"path": str(target), "bytes": len(after), "sha256": hashlib.sha256(after).hexdigest()}, "after_archive": pin(candidate), "mode": mode})
manifest = {"round": "R276", "status": "FACTUAL_CONTEXT_UPDATED_NO_COMPLETION_PROMOTION", "changes": changes, "allowed_state_keys": P["context_update"]["allowed_state_keys"], "state_other_values_preserved": True, "phase_prefix_preserved": True, "new_commands_executed": 0, "T2_complete": False, "T12_complete": False}
manifest_path = D / "root-context-update.json"
assert not manifest_path.exists()
for record, before, after in zip(originals, (state_before, phase_before), (state_after, phase_after)):
    target = Path(record["path"])
    assert target.read_bytes() == before and target.lstat().st_mode == 33204
    target.write_bytes(after)
    assert target.read_bytes() == after and target.lstat().st_mode == 33204
with manifest_path.open("xb") as f:
    f.write((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
print(json.dumps({"round": "R276", "status": manifest["status"], "manifest": pin(manifest_path), "after": [x["after"] for x in changes], "state_other_values_preserved": True, "phase_prefix_preserved": True, "T2_complete": False}, ensure_ascii=False))
