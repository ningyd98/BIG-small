# Phase 7 B 停止生命周期独立审阅修复计划

gpt-6.2-astra · 2026-11-23 · 研发基线 `2ec0c98f82a6cab7fb1f9abbec37631226d3d605`。实施输入为主计划 B 的未提交候选。主计划原件与四个候选产品指纹均已核对。逐文件 SHA256、探针记录和当前测试输入见 [plan.json](plan.json)。

## 五次零步探针

| 探针 | 原始观测 |
| --- | --- |
| repeat-public-stop | guard 正常退出、recorder 仍存活时第二次公共急停又发 hold 和 STOP，两者的父均为 unbracketed-operations。 |
| retry-after-failed-brake | 第一次 hold 抛 OSError，第二次公共急停返回，命令 0，最终 ESTOP 未置位。 |
| purpose-entry-error | 正常 body 后 TERMINATION 分配失败，制动执行但没有真实父。应用和审计保留异常，guard 仍为 CLOSED。 |
| purpose-exit-error | 正常 body 后区间结束失败，真实区间 PARTIAL，应用抛 OSError，guard 仍为 CLOSED。 |
| caught-becoming-stop | except 中急停后重抛同一 ValueError，命令有父，guard CLOSED、TERMINATION COMPLETE。实际 skill_robot.lift 对 Exception 返回失败 ActionResult，非 Exception 的 BaseException 才重抛；原探针模拟重抛顺序。 |

独立探针的 reader_guard_clause 是 operations() 内一条谓词，后两项记账故障均获该子谓词接受。尚须独立执行公共读回。测试文件在审阅后有并发修改；保留两个指纹，修复前用当前测试与原探针重放并核对事实。四个产品指纹与主线程提供的数值完全一致。

## 根因与范围

关闭开始即把布尔 closed 置真，终止回调随后在 guard 退出时被清除。它无法表示物理制动何时真正完成。终态行早于审计入场、制动和审计退出结果，无参公共停机也没有收到控制器的明确故障原因。允许修改 simulation/mujoco/backend.py、实际故障发起点 skill_robot.py、research/native_collection_application.py，必要时修改 research/native_full_horizon_recorder.py、vision/raw_recorder_v3.py、research/native_full_horizon_originals.py 的 operations 判定，以及相关 guard/controller/collector/reader 测试。原计划其它工作独立继续。

## 修复与验证

- [ ] **先留 RED。** 以原目录、相邻 Python、当前候选和真实 recorder/backend 建立五个回归。覆盖 scope 内、退出后 recorder 尚开、第一次 hold 在闩锁前抛错、ESTOP 位已设但控制写未完成、只有审计失败而制动已完成。核第一次和重试的真实命令顺序、有效控制、是否制动、物理步、区间/父和实际发生时钟。保留审阅原件与新日志，勿覆盖原五行。
- [ ] **一次成功制动与失败后的安全重试。** 从开始关闭即禁止新非安全操作。增加 recorder 绑定 episode/guard 的必要状态，区分正在制动、已真实完成、未完成。仅当 hold 和实际制动控制均完成才能抑制同一生命周期后续公共急停；覆盖 guard 已退出而 recorder 仍开的情形。仅凭 closed 或 estop_engaged 不能判断完成。先前物理处理未完成时，下次显式安全请求必须真实制动，允许重试必要的安全步骤；仍保留首个失败并禁止普通动作。若纯审计失败但制动成功，则保留失败并避免重复制动。有有效 recorder 时重试要有真实、当时创建的 TERMINATION，不复用先前已关闭父；无法记账时仍立即制动并如实记录来源缺失。保持原线程约束、阻止回调重入且无无界自动重试。普通无 recorder 的公共 API、异常及原操作顺序须有回归。
- [ ] **guard 和作用域故障。** 对最先实际获知的 body、控制器、停止、分配或结束异常保留主因、对象/traceback、阶段与次错误。正常 body 后 termination 入口/出口失败也形成可独立读取的失败终态。保留原命令、PARTIAL/ABORTED、未分配的父、实际时钟与事件上限时内嵌的 closure。第一次安全尝试失败而重试成功时，首因不能被覆盖为 clean CLOSED。若已有主异常，次要制动/记账失败不遮蔽其抛出或既有失败回执。区间发生时没有的证据不得倒填。
- [ ] **控制器明确传递当时已知的原因。** 允许从 skill_robot.lift 的异常分支向后端一个窄的故障停机接口传递当前实际 cause，保留无参公共入口和普通调用。在真实控制器测试覆盖失败 ActionResult、BaseException 原样重抛、MotionGuardViolation 原 hold/错误码和停止自身二次失败。已知 cause 的停止记录 FAILURE 和真实 ABORTED 区间。无参急停后较晚才由 body 重抛时，应在展开时独立记录该新获故障；早先正常指令和真实 COMPLETE 的时间/处置保留。原无参探针按实际得知时间验收。此前在外层已经处理的异常中运行正常 guard、正常手动停和成功关闭是三个负控。禁止用线程环境 sys.exc_info()/sys.exception() 猜测因果。
- [ ] **读回和兼容。** 在足以通过前置来源检查的软件夹具上运行 _Audit.operations，并通过公共 group/registry 入口确认报告 operations 拒绝。正控为已有无错误 CLOSED；负控含显式 FAILURE、旧格式 CLOSED 同行带 termination_entry_error/termination_exit_error/stop_error、失败记录后随看似正常关闭，以及错误写入嵌套 closure。保持历史健康记录与正常无 recorder guard 可读，确认拒绝具体来自 operations。复跑真实 collector→SQLite→worker→recorder→原格式落盘→公共 reader 的隔离失败路径，核主次异常、制动和无重试/后续派发。核冻结 v9/v10 对应协议、raw inventory 和唯一已消费 claim；最终代码按主计划 C 的 --verify --source-root 重放，保留原一/四个动作、两/八条准入、v10 原始 428/429、UNKNOWN、八组 NOT_RUN 和空联合界。已有结果若作为验证引用，记录已复核的输入、运行代码 SHA 与实际覆盖。
- [ ] **交付与边界。** 使用指定工作树、隔离本地证据路径、相邻解释器与可用测试后端；新登记/单帧预检使用本轮最终源。正式仿真、新正式 claim、模型/硬件调用均为 0。允许有限非正式测试；保持顶视、原控制方案、阈值、原 claim/DB/正式原件与主计划字节。限定同一停止生命周期根因的诊断、修复、正负控；出现新独立根因/扩围则先另轮 Astra 计划。保存 RED、GREEN 和独立复核，阶段总结可另记本轮及此次软件边界。

## 命令

从指定工作树运行。E 为独立审阅所在的既有私有目录，PY 为相邻 harness-candidate-20261118/.venv/bin/python。以下输出文件使用新名称，并设置 PYTHONPATH=src:.、PYTHONDONTWRITEBYTECODE=1、MUJOCO_GL=egl。

```bash
"$PY" "$E/review-stop-probe.py" > "$E/guard-review-post-probe.log"
"$PY" -m pytest -q tests/test_native_collection_authority.py tests/test_mujoco_execution_guard_v1.py tests/test_mujoco_full_horizon_sampling.py tests/test_native_harness_stop_diagnostics.py
"$PY" -m pytest -q tests/test_visual_servo_control.py -k lift_hold
"$PY" -m pytest -q tests/test_native_full_horizon_originals.py tests/test_native_registered_teacher_release.py
```

同步执行新增测试与隔离 E2E nodeid、主计划的历史读回和新源预检、Ruff 及基线类型检查差异。全量重放与阶段交付由主线程负责。
