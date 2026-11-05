"""Derive reports from retained stage evidence; never rerun or rewrite experiments."""

from collections import Counter
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[7]
BASE = Path(__file__).resolve().parents[2]
R435 = BASE / "round435-t7b-guarded-execution-20261105"
R436 = BASE / "round436-guard-validation-contract-20261105"
R437 = BASE / "round437-guard-observer-closure-20261106"
PRODUCT = [
    "src/cloud_edge_robot_arm/simulation/mujoco/backend.py",
    "src/cloud_edge_robot_arm/research/guarded_execution_v1.py",
    "tests/test_mujoco_execution_guard_v1.py",
    "tests/test_guarded_execution_v1.py",
]


def read(path):
    return json.loads(path.read_text())


def rel(path):
    return str(path.relative_to(ROOT))


def pin(path):
    raw = path.read_bytes()
    return {"path": rel(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as out:
        if isinstance(value, str):
            out.write(value)
        else:
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.write("\n")


def phase(directory, expected_passed, expected_failed):
    result = read(directory / "result.json")
    events = [json.loads(line) for line in (directory / "pytest-events.jsonl").read_text().splitlines()]
    collection = next(x for x in events if x["event"] == "collection_finished")
    counts = Counter((x["when"], x["outcome"]) for x in events if x["event"] == "report")
    total = expected_passed + expected_failed
    expected = {("setup", "passed"): total, ("teardown", "passed"): total}
    if expected_passed:
        expected["call", "passed"] = expected_passed
    if expected_failed:
        expected["call", "failed"] = expected_failed
    assert counts == Counter(expected), (directory, counts)
    assert collection["collection_errors"] == 0 and len(collection["nodeids"]) == total
    assert result["state"] == "FINISHED" and result["reaped"]
    assert not result["remaining_live"] and not result["source_drift"]
    assert result["returncode"] == int(bool(expected_failed))
    return {
        "stage": rel(directory), "collected": total, "setup_passed": total,
        "call_passed": expected_passed, "call_failed": expected_failed,
        "teardown_passed": total, "skipped": 0, "collection_errors": 0,
        "elapsed_s": result["elapsed_s"], "remaining_live": [], "source_drift": [],
        "evidence": [pin(directory / name) for name in
                     ("result.json", "terminal.json", "stdout.log", "stderr.log", "junit.xml", "pytest-events.jsonl")],
    }


def run():
    phases = {
        "r435_red": phase(R435 / "validation/red", 0, 2),
        "r435_initial_green": phase(R435 / "validation/green", 157, 2),
        "r436_focused": phase(R436 / "validation/focused", 2, 0),
        "r437_red": phase(R437 / "validation/red", 0, 3),
        "r437_green": phase(R437 / "validation/green", 162, 0),
        "r437_diagnostic": phase(R437 / "validation/diagnostic", 1, 0),
    }
    for name in ("r435_initial_green", "r437_green"):
        phases[name]["deselected"] = 1
    static = read(R437 / "validation/static/results.json")
    assert [x["name"] for x in static] == ["ruff", "format", "mypy"]
    assert all(x["returncode"] == 0 and not x["source_drift"] and not x["remaining_live"] for x in static)

    raw = R437 / "validation/diagnostic/actual-diagnostic"
    result = read(raw / "result.json")
    prereg = read(raw / "preregistration.json")
    operations = read(raw / "operations.json")
    checks = read(raw / "clock-readings.json")
    guards = read(raw / "guard-events.json")
    commands = read(raw / "command-records.json")
    final = read(raw / "final-state.json")
    deadline = result["original_deadline"]
    assert result["status"] == "PASS" and result["physics_steps"] == 2
    assert result["primary_error"] is None and result["secondary_errors"] == []
    assert result["expected_refusals"] == ["expired_command", "expired_step", "closed_step"]
    assert result["qualification"] == "UNKNOWN" and result["full_horizon_producer"] == "UNAVAILABLE"
    assert deadline == read(raw / "deadline.json")
    assert deadline["deadline_ns"] == deadline["origin"]["lower_ns"] + 10_000_000_000
    assert deadline["domain"]["api"] == "Linux time.clock_gettime_ns(time.CLOCK_BOOTTIME)"
    allowed = [x for x in checks if x["outcome"] == "ALLOWED"]
    rejected = [x for x in checks if x["outcome"] == "REJECTED"]
    assert len(allowed) == 24 and len(rejected) == 1
    assert all(x["current_upper_ns"] < deadline["deadline_ns"] for x in allowed)
    assert rejected[0]["current_upper_ns"] >= deadline["deadline_ns"]
    assert all(x["deadline_identity"] == deadline["issuance_identity"] for x in checks)
    assert all(x["deadline_ns"] == deadline["deadline_ns"] for x in checks)
    physics = [x for x in operations if x["kind"] == "PHYSICS" and x["phase"] == "END"]
    assert [x["physics_step"] for x in physics] == [1, 2]
    assert not any(x["kind"] == "CAPTURE" for x in operations)
    assert not read(raw / "observer-failures.json")
    assert final["physics_step"] == 2 and final["estop_engaged"]
    assert len(guards) == 26 and sum(x["kind"] == "FAILURE" for x in guards) == 1
    command_counts = Counter(x["type"] for x in commands)
    assert command_counts == {"joint_target": 1, "gripper": 1, "hold_current_joints": 2, "emergency_stop": 2}
    assert all(x["accepted"] for x in commands)
    assert all(pin(ROOT / name)["sha256"] == row["sha256"] for name, row in prereg["source_pins"].items())
    diagnostic = {
        "status": "PASS", "attempt": "R435.diagnostic.1", "attempts": 1,
        "evidence_scope": result["evidence_scope"], "real_engine": "MuJoCo 3.3.7",
        "clock_api": deadline["domain"]["api"], "original_budget_ns": deadline["budget_ns"],
        "original_lower_ns": deadline["origin"]["lower_ns"], "deadline_ns": deadline["deadline_ns"],
        "last_allowed_ns_from_origin": max(x["current_upper_ns"] for x in allowed) - deadline["origin"]["lower_ns"],
        "first_rejected_ns_from_origin": rejected[0]["current_upper_ns"] - deadline["origin"]["lower_ns"],
        "physics_steps": 2, "final_sim_time_s": final["sim_time_s"], "estop_engaged": True,
        "guard_checks_allowed": 24, "guard_checks_rejected": 1, "guard_event_rows": 26,
        "operation_boundaries": dict(Counter(x["kind"] + ":" + x["phase"] for x in operations)),
        "accepted_command_counts": dict(command_counts), "expected_refusals": result["expected_refusals"],
        "primary_error": None, "secondary_errors": [], "observer_failures": [],
        "native_authority": "UNAVAILABLE", "qualification": "UNKNOWN", "complete_native_guard": "NOT_PROVEN",
        "full_horizon_producer": "UNAVAILABLE", "rendering": False,
        "raw_directory": rel(raw), "raw_remote_delivery": "NOT_INCLUDED; manifest and derived summary only",
        "preregistered_source_pins": prereg["source_pins"],
    }
    save(R437 / "validation/diagnostic/trace-summary.json", diagnostic)
    save(R437 / "validation/diagnostic/local-raw-manifest.json", {
        "scope": "LOCAL_ONLY_DIAGNOSTIC_ORIGINALS", "not_remote_reproduction_bundle": True,
        "files": [pin(p) for p in sorted(raw.iterdir()) if p.is_file()],
    })

    baseline = read(R435 / "implementation/baseline.json")["files"]
    changed = [x["path"] for x in baseline if pin(ROOT / x["path"]) != x]
    assert changed == [PRODUCT[0]], changed
    plan = read(R437 / "plan.json")
    unplanned = [x["path"] for x in plan["input_pins"] if pin(ROOT / x["path"]) != x and x["path"] not in PRODUCT]
    assert not unplanned
    final_pins = [pin(ROOT / name) for name in PRODUCT]
    for stage in ("green", "diagnostic"):
        rows = read(R437 / f"validation/{stage}/preflight/runtime-source-pins.json")["files"]
        lookup = {x["path"]: x for x in rows}
        assert all(lookup[x["path"]] == x for x in final_pins)
    main = subprocess.check_output(["git", "rev-parse", "refs/heads/main"], cwd=ROOT, text=True).strip()
    assert main == "fdb2e94d3d7bc041e7d958f2514a08406fad4668"
    source_audit = {
        "baseline_tracked_paths": len(baseline), "changed_existing_source": changed,
        "unchanged_baseline_paths": len(baseline) - len(changed),
        "allowed_new_paths": PRODUCT[1:], "final_product_pins": final_pins,
        "non_product_plan_input_drift": [], "green_and_diagnostic_same_source_generation": True,
        "main_unchanged": main,
    }
    save(R437 / "validation/source-audit.json", source_audit)

    # Only three default-argument bindings changed between RED and final test text.
    # Recover those exact RED bytes, explicitly labelled, and verify their original pins.
    red_pins = {x["path"]: x for x in read(R437 / "validation/red/preflight/runtime-source-pins.json")["files"]}
    proof = []
    for name in PRODUCT:
        if name.startswith("src/"):
            raw_bytes = (R437 / "implementation/frozen" / name).read_bytes()
        else:
            text = (ROOT / name).read_text()
            text = text.replace(
                "                def observe(\n                    event,\n                    backend=backend,\n                    failure=failure,\n                    raised=raised,\n                    before_stop=before_stop,\n                    kind=kind,\n                    phase=phase,\n                ):\n",
                "                def observe(event):\n",
            ).replace(
                "        def bad_control_once(control_calls=control_calls, original_control=original_control):\n",
                "        def bad_control_once():\n",
            ).replace("        def reject(_, primary=primary):\n", "        def reject(_):\n")
            raw_bytes = text.encode()
        original = red_pins[name]
        assert len(raw_bytes) == original["bytes"] and hashlib.sha256(raw_bytes).hexdigest() == original["sha256"]
        dest = R437 / "implementation/red-source-reconstruction" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("xb") as out:
            out.write(raw_bytes)
        proof.append({"red_source": original, "reconstructed_file": pin(dest)})
    save(R437 / "implementation/red-source-reconstruction/proof.json", {
        "method": "Reconstruct from R437 frozen input or reverse the documented post-RED default-argument bindings; exact original RED runtime SHA256 and length match. Not claimed as a contemporaneous capture.",
        "files": proof,
    })

    review = read(R435 / "review/fresh-astra-review.json")
    findings = [
        {"id": "R435-F1", "status": "FIX_VERIFIED_BY_IMPLEMENTER", "node": "test_stop_bypass_rejects_foreign_command_and_physics", "change": "thread-local, exact internal CONTROL exemption; ordinary commands and physics always checked"},
        {"id": "R435-F2", "status": "FIX_VERIFIED_BY_IMPLEMENTER", "node": "test_operation_observer_failure_closes_guard_without_guard_rejection", "change": "first guarded observer/source exception propagated outside callback; unguarded behavior and STOP preserved"},
        {"id": "R435-F3", "status": "FIX_VERIFIED_BY_IMPLEMENTER", "node": "test_diagnostic_retained_failures_change_status", "change": "typed stop/snapshot secondary errors merged before status, including overflow closure"},
    ]
    save(R437 / "review/fix-verification.json", {
        "original_review": pin(R435 / "review/fresh-astra-review.json"),
        "original_review_unchanged": True, "new_reviewer": False,
        "findings": findings, "red": phases["r437_red"], "green": phases["r437_green"],
        "diagnostic": diagnostic,
    })
    save(R437 / "review/fix-verification.md", """# R437 三项独立审查问题的修复核对

唯一 fresh review 由实际 gpt-6-astra 完成；原审查提出三项 Important，其原报告保持不变。本文件是实施者依据 RED→GREEN 与实际诊断的修复核对，不冒充第二次独立审查或改写原审查结论。

| 原问题 | 反例与修复后的行为 |
|---|---|
| F1 停止窗口允许外线程命令 | RED 中夹爪命令成功穿透。GREEN 中另一线程的夹爪和 step 均在效果前拒绝，夹爪 ctrl 仍为 0.039，物理步数为 0，原主异常与内部停止 CONTROL 均保留。豁免仅在当前线程的内部 CONTROL 调用期间生效。 |
| F2 observer 独立失败未关闭 guard | RED 中 COMMAND BEGIN 异常后命令成功返回。GREEN 覆盖 COMMAND/CONTROL/PHYSICS × BEGIN/END：BEGIN 对应效果为 0，END 保留 1 次效果，原异常对象向外传播，会话关闭并停止；无 guard 对照保持原语义。另核对 source snapshot 失败、STOP observer 二次失败和不可打印异常。 |
| F3 诊断遗漏停止/快照失败 | RED 缺少失败归并入口。GREEN 使用真实软件 backend 生成的 guard-events：先失败后恢复仍为 FAIL，纯预期到期拒绝仍为 PASS，overflow closure 内的附加失败不丢失。真实诊断在计算 status 前调用该归并。 |

三项 RED 均是预期 call 阶段断言失败，setup/teardown 正常。最终合并 GREEN 为 162 PASS、1 deselected；静态三项通过；唯一真实诊断为 1 PASS、实际 2 步、无附加错误。原始证据和哈希见 fix-verification.json。R437 计划要求不再派第二 reviewer，本轮遵守。
""")

    boundaries = {
        "software_validation": "SCOPED_PASS", "real_no_render_diagnostic": "PASS",
        "local_guard_proof": "COMMAND_CONTROL_PHYSICS_IN_THIS_DIAGNOSTIC",
        "complete_native_guard": "NOT_PROVEN", "native_qualification": "UNKNOWN",
        "full_horizon_producer": "UNAVAILABLE", "independent_geometry_motion_calibration": "NOT_ACCEPTED",
        "normal_pick_place_closed_loop": "NOT_ACCEPTED", "formal_research_acceptance": "NOT_ACCEPTED",
        "hardware": "NOT_RUN", "full_4751_suite": "NOT_RUN_THIS_DELIVERY",
    }
    report = {
        "generated_at_utc": datetime.now(UTC).isoformat(), "status": "VERIFIED_LOCAL_DELIVERY_PENDING_GIT",
        "rounds": [435, 436, 437], "phases": phases, "final_static": static,
        "initial_static": {"ruff": "PASS", "format": "PASS", "mypy": "FAIL_4_ARG_TYPES"},
        "superseded_unrun": ["R436 full GREEN", "R436 static", "R436 diagnostic"],
        "actual_diagnostic": diagnostic, "source_audit": source_audit, "review_findings": findings,
        "real_physics_steps": {"r435_initial_regression": 2, "r437_merged_regression": 2, "unique_diagnostic": 2, "total": 6},
        "acceptance_boundaries": boundaries,
        "git_receipt": "delivery/delivery-receipt.json (created locally after push; not part of its own commit)",
    }
    save(R435 / "test-report.json", report)
    save(R435 / "test-report.md", """# R435–R437 执行守卫测试报告

日期：2026-11-06（Asia/Shanghai）。本报告对应限定执行守卫交付，并未重跑全库 4751 项或长测。所有结果来自保留的 stdout/JUnit/pytest phase events 与 bounded supervisor；没有用通过数覆盖历史失败。

| 阶段 | 实际结果 | 说明 |
|---|---|---|
| R435 API RED | 2 个预期断言失败 | setup/teardown 均通过，无 collection 错误 |
| R435 初始 GREEN | 157 PASS / 2 FAIL / 1 deselected | 两个测试预期 RuntimeError，实际契约为 TimeoutError；原始失败保留 |
| R435 初始静态 | ruff、format 通过；mypy 4 错误 | 既有边界字段需要明确的 Literal/可空字符串类型收窄 |
| R436 focused | 2 PASS | 精确修正到期异常测试；四处 cast 的行为不变证明保留 |
| R437 三个反例 RED | 3 个预期断言失败 | 分别证实 observer 失败、外线程停止窗口、遗漏 secondary |
| R437 合并 GREEN | **162 PASS / 1 deselected** | 162 项 setup/call/teardown 全通过，无 skip、源漂移或残留进程；耗时 84.08 秒（pytest） |
| R437 静态 | **三项通过** | ruff check、format --check 四文件，mypy 两源文件；mypy 的 unused-section 提示不是错误 |
| 唯一实际诊断 | **1 PASS** | 实际 MuJoCo 两步 + 真实 BOOTTIME 到期；pytest 10.97 秒，supervisor 12.012 秒，cap 60 秒 |

R437 合并 GREEN/静态替代了未执行的 R436 全批验证；实际诊断仅在 R437 运行一次，消耗 R435.diagnostic.1。GREEN 中排除的 1 个节点正是该实际诊断，之后独立执行，并非遗漏或 skip。

真实诊断使用 S01_NORMAL_STATIC、seed=0、dt=1/240、无渲染。原始 10 秒预算在 initialize/reset 前发放，未刷新。一次当前关节同位目标、一次开夹爪、两次 mj_step；24 个检查点允许，原 deadline 后的命令检查拒绝，随后 expired_step 与 closed_step 也拒绝。最终 sim time=0.008333333333333333 秒、physics_steps=2、estop=true，无 observer failure、primary 或 secondary error。另有两次 HOLD/STOP，是故障处理记录，不计为抓放动作。

两次历史/合并回归各有 2 步真实 MuJoCo，唯一实际诊断 2 步，本次研发链累计 6 步；新增反例使用软件 backend，不能冒充实测物理。真实到期拒绝的读数是原始起点后 10.001499563 秒，这只是一次测量；Python 同线程无法硬抢占阻塞中的 mj_step，不据此声称硬实时保证。

原始实际诊断位于 ../round437-guard-observer-closure-20261106/validation/diagnostic/actual-diagnostic/，本地保留。远端交付 trace-summary、local-raw-manifest 和验证日志，不包含该原始目录、完整批量 raw、运行 DB、缓存、凭据、权重或 SDK；清单不是完整远端复现包。

源核对以原始 772 个受控 src/tests/configs/assets 路径为基线：仅既有 backend 改动，另新增研究模块及两个测试；771 个旧路径不变。GREEN 和实际诊断使用同一源码世代。详细原始路径、SHA256、阶段分母、审查修复核对及验收边界见 test-report.json 和 R437 validation/source-audit.json。

验收仍分开：本轮软件与实际小步诊断通过；完整 native guard 为 NOT_PROVEN，full-H producer 为 UNAVAILABLE，native qualification 为 UNKNOWN，完整正常抓放和正式研究验收尚未完成。
""")
    save(R435 / "step-report.json", {"round": 435, "final_outcome": "SCOPED_DELIVERABLE_VERIFIED_WITH_R436_R437", "test_report": "test-report.json", "initial_failures_preserved": True, "boundaries": boundaries})
    save(R435 / "step-report.md", """# R435 步骤报告

已新增后端同步执行守卫、OC1 原始 deadline 组合及固定两步真实诊断。COMMAND/CONTROL/每次 mj_step 在作用前后检查；observer 返回之后再次检查；故障保留真实已发生效果并关闭会话，STOP/HOLD 保持可用，guard 不能重装或通过 reset 恢复。

初始 RED 为两个预期失败。初始 GREEN 的两个异常类型测试失败和 mypy 四项错误进入实际 Astra 的 R436；唯一 fresh review 的三项 Important 进入实际 Astra 的 R437。原证据与原计划没有覆盖。最终 R437 合并验证 162 PASS、静态通过、唯一真实诊断 1 PASS；详细记录见 test-report.md/json。

本轮完成的是实际执行拦截接缝，没有接通完整 worker/lease/取消/TTL/native 动作链。完整 full-H producer 仍 UNAVAILABLE，正式资格 UNKNOWN，正常抓放和正式实验未验收。Git 交付结果由推送后的本地 delivery/delivery-receipt.json 单独记录。
""")
    save(R436 / "step-report.json", {"round": 436, "focused": phases["r436_focused"], "changes": ["deadline equality/later expect exact TimeoutError", "four type casts in existing source event constructor"], "merged_validation": rel(R437 / "validation/green/result.json"), "static": static, "own_green_static_diagnostic": "NOT_RUN_SUPERSEDED_BY_R437"})
    save(R436 / "step-report.md", """# R436 步骤报告

实际 Astra 计划之后，精确修正 equality/later 对 TimeoutError 的预期，并保留原异常消息、已发生一步和 estop/关闭断言；focused 2 PASS。既有 source boundary 构造器的四处类型收窄用 cast 明示，AST 去掉 cast 后等价证据见 implementation/cast-ast-proof.json。

未单独运行 R436 GREEN、静态或实际诊断。R437 计划将这些验证合并：最终 162 PASS、三项静态通过、唯一真实诊断 1 PASS。原始 R435 157 PASS/2 FAIL 及 mypy 4 错误仍保存，不改写成通过。本轮不新增或提升 native/研究资格。
""")
    save(R437 / "step-report.json", {"round": 437, "red": phases["r437_red"], "green": phases["r437_green"], "static": static, "actual_diagnostic": diagnostic, "findings": findings, "boundaries": boundaries})
    save(R437 / "step-report.md", """# R437 步骤报告

15 项计划输入在实施前核对并冻结。新增三个反例，单次 RED 全部按预期在 call 断言阶段失败。限定修复包括：停止豁免收窄到当前线程的内部 CONTROL；observer/source 首个异常在安全检查点传播；诊断归并已记录的停止/快照 secondary，包括 overflow closure。无 guard 的观察器语义保持。

一次合并 GREEN：162 PASS、1 deselected，162 项 setup/call/teardown 均通过；一次 ruff/format/mypy 均通过。之后唯一实际诊断 1 PASS，真实 MuJoCo 两步，真实 BOOTTIME 到期拒绝命令及后续步进，安全停止完成，无额外步和附加错误。所有阶段源未漂移、子进程已回收。没有派第二 reviewer，三个 finding 的实施者修复核对见 review/fix-verification.md/json。

RED 后为显式绑定循环闭包变量调整了测试默认参数；implementation/red-source-reconstruction 保留按已知差异恢复的 RED 源字节，逐一匹配当时 runtime pins 的 SHA256 与长度，并明确标为事后恢复，不冒称当时冻结。

本轮不构成 full-H/native、完整抓放或正式研究验收。完整限制和主线后续见 R435 phase-summary.md；分层测试和源审计见 R435 test-report.md/json。
""")
    save(R435 / "phase-summary.md", """# 毕业设计研发主线阶段总结：执行守卫从接口验证进入实际诊断

本阶段完成了一个必要的运行环节：原始 BOOTTIME deadline 已接入 MuJoCo 的命令、控制与逐步物理执行。软件反例验证了到期、取消、时钟身份变化、记录器失败、线程越界、重入和关闭后复活的拒绝行为；一次真实无渲染诊断验证了两步实际执行及到期后的拒绝与停止。

| 对开题报告研发任务的贡献 | 当前可据实陈述的进展 |
|---|---|
| 云、边、端协同基础与接口 | 在既有架构上补上执行约束的落地点；用户选定云方案、边缘选型后置、OpenCV/可见标记/顶视相机/控制器均保持。 |
| 任务约束与状态一致性、事件触发决策 | 原始时间约束可以在执行前后被消费；记录失败会封闭本次执行，不能继续产生成功返回。 |
| 有界恢复与异常闭环 | 原始异常保留为主因，STOP/HOLD 与必要 CONTROL 可继续；停止错误单列，后续恢复不能把失败抹成 PASS。 |
| 系统集成与实验评价 | 已得到小步真实仿真证据。尚未得到当前正式资格下的完整正常抓放、连续效果证明、基线对照和统计实验结论。 |

研发产物为两个源文件（既有 backend 修改、guarded_execution_v1 新增）及两个测试文件；实际 gpt-6-astra 完成 R435/R436/R437 规划与唯一独立审查。最终限定回归 162 PASS，静态三项通过，唯一实际诊断 1 PASS；历史失败完整保留。详见 test-report.md/json、R437 review/fix-verification.md/json。

仍未完成：完整 full-H 实际 producer、真实应用/worker owner 与原 lease/cancel/hard-stop、观测 TTL 的整体接通；独立几何/联合运动误差校准；连续抓取—搬运—放置效果证明。full-H producer=UNAVAILABLE，完整 native guard=NOT_PROVEN，native qualification=UNKNOWN，正式研究验收未通过。诊断的 2 步、无渲染和同位目标不能代替这些任务。

下一块应沿现有 R91 完整动作设计与开题后的总计划，接通真正产生全时域执行记录的入口：由实际 owner 发放同一个原始 H/deadline，在该接缝上贯通租约、取消、观测 TTL、单一 recorder 与既有控制器，完整保存逐步原始证据；再按独立校准准入条件开展正常抓放闭环。此后才进入合格周期基线和协同/恢复对照实验，不把下一块替换为新的离线审计器，也不扩展 UI 或模型选型。

远端仅交付明确列入清单的源码、测试、计划、冻结输入、阶段日志和派生报告。实际诊断原始目录及完整批量 raw/运行 DB/缓存/凭据/权重/SDK 按既有边界保留本地；交付清单不代表完整远端复现包。提交推送后另存本地三方 SHA 回执，不为给回执自引用而循环提交。
""")
    ledger = ROOT / ".superpowers/sdd/plan-round435-t7b-guarded-execution-20261105/progress.md"
    with ledger.open("a", encoding="utf-8") as out:
        out.write("\nR435 initial validation: RED 2 expected; GREEN 157 passed/2 failed; mypy 4 errors, preserved.\nR436: actual Astra plan, focused 2 passed; four behavior-preserving casts.\nR437: actual Astra plan for sole fresh-review F1/F2/F3; RED 3 expected, merged GREEN 162 passed/1 deselected; ruff/format/mypy passed; unique actual no-render BOOTTIME diagnostic 1 passed, exactly 2 physical steps.\nTask 1/2 scoped software and actual diagnostic complete; full-H/native remain unavailable/unknown. Reports built; exact-path Git delivery pending.\n")
    print(json.dumps({"phases": {k: {a: v[a] for a in ("collected", "call_passed", "call_failed")} for k, v in phases.items()}, "source_audit": source_audit, "diagnostic": {k: diagnostic[k] for k in ("status", "physics_steps", "expected_refusals", "primary_error", "secondary_errors")}}, ensure_ascii=False))


if __name__ == "__main__":
    run()
