# Phase 7 并发制动与 LIFT 次生保持异常补充计划

gpt-6.2-astra · 2026-11-23 · Git 基线 `2ec0c98f82a6cab7fb1f9abbec37631226d3d605`。已核对独立 advanced 探针的八个零步结果、前一补轮的顺序回归和当前输入。运行探针时的 backend/skill SHA 与计划写入时不同，两套均在 [plan.json](plan.json) 中；当前代码仍有 BRAKING 路径的正常提前返回及未经保护的异常分支 hold。实施前先在同一候选快照复跑以确认因果，一切原日志只读。

## 失败与既有行为

1. 正常 owner 开始制动并进入 hold。第二线程调用公共同步 emergency_stop 在首线程仍工作时无错返回，返回时 ESTOP=false。首线程随后收到原 OSError。最终 0 命令、0 物理步、未制动，TERMINATION ABORTED。
2. 真实 skill_robot.lift 收到 MotionGuardViolation(GRASP_LOST)，处置该故障时专用 hold 抛 OSError。OSError 取代原动作结果，原 cause 仅在异常 context，guard 把它记为 body 的 OSError；随后一次带父的制动成功。
3. 同日志前六例为顺序对照。控制写失败后虽然闩锁为真，ctrl[0] 仍为 0.75；scope 内/外再次请求均真实写至 0，保留第一失败和独立终止区间。纯入/出审计失败且制动完成时均不重发；已处理的外部异常与明确归因的停止分别产生 CLOSED/COMPLETE、FAILURE/ABORTED。

## 实施范围与验收

- [ ] **复核及 RED。** 限定产品为 simulation/mujoco/backend.py 和 skill_robot.py，测试为 tests/test_native_collection_authority.py、test_mujoco_execution_guard_v1.py，以及实际 LIFT 控制器的 test_visual_servo_control.py。先运行原八项探针至新的私有日志，核源版本、实际 worker/后端和异常对象。用 Event/Barrier 置入 hold 或真正的 control write，以客观发生顺序构造 owner/其他调用，线程 finally 释放并有界 join；不能用 sleep 猜测并发。复现首次成功／物理失败／控制已排队但写未完成、两位以上调用者、同线程递归与 recorder/guard/observer 回调重入。断言每个公共调用的结果、控制缓冲写入时间、闩锁/异常及实际 writer 峰值，保留首个 RED。
- [ ] **确定的同步完成语义。** recorder 绑定的 guard 内将或已进行的真正制动由一个写者负责。状态同步涵盖认领、物理完成/失败、提交结果及释放等待者；真正控制写返回才承认物理成功。CLOSING/BRAKING、闩锁为真、已记命令都不足以向重叠请求报告成功。可让其他线程有界等待本次 attempt 的明确结果，或直接显式报告进行中/无法完成；任何返回成功必须能在返回时验证真实制动已完成。若采用等待，使用带代次的谓词和有限超时以区别首尝试结果与稍后重试；不得要求调用者线程先完成才能让原写者继续，也不得把 timeout 当作成功。失败必须可观测，下一个有效显式请求允许在唯一写者下做必要补制动；允许一个已等待请求在原写者完成失败后承接一次有界补制动。原失败者仍看到原错误，两个调用若都失败必须各有明确失败结果并保留之后补制动能力。多个等待者、连续失败都不能产生无限隐式重试、并行命令或放行新动作。
- [ ] **同线程与真实来源。** owner 的公共递归请求和 recorder/observer 回调重入应立即拒绝或走已有明确受限的内部物理步骤，使普通公共调用无法伪造成功。锁内只操作同步状态；运行 recorder purpose/用户回调、物理 I/O 或可能重入的状态采样均须在锁外。成功后多余显式请求不再写；首次失败与后续物理成功分别可追溯，若来源仅允许 owner 线程，依既有规则即时安全制动并标注缺证。登记区间的 BEGIN/END、真实 command/CONTROL 顺序、owner 归属、事件容量、首因和次错误均保持；无 recorder 和普通 guard 接口不改变。
- [ ] **LIFT 双故障。** 测试实际 lift 的 MotionGuardViolation 两种既有域码、非零 held_steps（含一个已完成步后观察失败）和零步边界。专用 hold 成功时沿用原动作结果与代码；hold 失败时保留原域错误对象、原因、status/error_code、真实已执行步数/反馈与 session.terminal_reason。立即执行一次现有带明确 cause 的安全应急流程，使必要的重保、撤销待执行目标及真实控制写得以发生；不得私自推进物理或继续动作。动作回执以不同字段分别记录专用 hold 故障与应急制动的二次故障（type/message/phase），两者同时发生时各保留一份。既有非 Exception BaseException 仍传递原对象与 traceback；普通 Exception 产生原失败回执，清理失败为次因。覆盖 hold 失败后制动成功、制动再次失败且可重试、主非域异常与次生故障、健康 hold 和普通 LIFT 正常完成，严禁把仅发出意图称作真实制动。
- [ ] **独立复核与边界。** 对八项原探针及补充的交叉并发正负控形成逐调用结果；使用真实递归拒绝与一次原 hold、后续控制写计数而非只查内部枚举。复核前一补计划的五例与 guard 事件上限、公共 reader 对 faulty CLOSED 的拒绝，以及冻结 v9/v10 的原准入/STOP、缺项和资格。必要时运行既有隔离完整 collector/SQLite→公共读回、最终源的隔离预检，保留冻结输入、主计划与此前补轮字节，私有原始输出另存。正式仿真/新正式 claim/模型/硬件 0，允许有限非正式模拟测试。新根因或需扩路径先回 Astra；步骤结果汇入阶段总结。

## 验证命令

在指定工作树设置 PYTHONPATH=src:.、PYTHONDONTWRITEBYTECODE=1、MUJOCO_GL=egl。E 为 Phase 7 私有证据目录，PY 为相邻隔离解释器；所有输出使用新名称。先后保存 RED、修复后正负控和最终源 SHA。

```bash
"$PY" "$E/review-final-advanced.py" > "$E/concurrent-stop-post-advanced.log"
"$PY" "$E/review-stop-probe.py" > "$E/concurrent-stop-post-original.log"
"$PY" -m pytest -q tests/test_native_collection_authority.py tests/test_mujoco_execution_guard_v1.py tests/test_mujoco_full_horizon_sampling.py tests/test_native_harness_stop_diagnostics.py
"$PY" -m pytest -q tests/test_visual_servo_control.py -k lift_hold
"$PY" -m pytest -q tests/test_native_full_horizon_originals.py tests/test_native_registered_teacher_release.py
```

新增并发回归按相同 nodeid 在静态候选反复执行并核无挂起；全链 E2E、既有历史 CLI 和新登记预检按主计划的路径与输入验证。明确报告未经真实硬件或新正式试次验证的边界。
