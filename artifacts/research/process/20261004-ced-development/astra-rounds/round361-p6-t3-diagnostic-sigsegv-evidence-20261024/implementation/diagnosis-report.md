# R361 静态证据诊断

作者 `/root/p6_t3_sol`，按实际 Astra R361 与 R362 的报告限定范围手写。R354 的 SIGSEGV 根因及原 R350 的 600 秒非完成根因仍为 **UNKNOWN**。本报告没有证明任何源修复，也不授予诊断中立性、行为通过或新的运行额度。

R361-A 是新的真实崩溃：子进程退出 −11，stderr 明确记录 `Fatal Python error: Segmentation fault`；外层 runner/timeout 退出 1，外层未超时，`deadline_events` 为空。270.1065520400007 秒是子开始至 cleanup 的耗时，不能定位故障指令时间。cleanup 已回收 leader、进程组为空且无 cleanup 错误。七阶段均留有 receipt，其中 raw、source-after、inventory、prerequisite 完成，resources、JUnit、cases 因真实记录不完整而失败。完成采证终态不等于测试成功；genuine completed resource counts 是 UNKNOWN，不能填写零或用允许的 poll 上限代替实际值。

ROOT 的既有完整性记录证明 539 个冻结源码输入一致、79 个输出文件共 20,243,954 字节得到保留；ROOT 已拒绝该诊断。此处沿用该完整性结论，不重新扫描历史输出或打开数据库。原始 raw、result/completion 和 ROOT disposition 全部保留，未作重标签。

可用观察包括 148 条 profile、55 条 OS、18 条 stack-request、7 条 native-ownership 记录及 77,146 字节原生栈文本。Profile 只有一次 `bridge:1` 入口和 exercise call，没有退出记录。最后完整 checkpoint 在 JSONL 第 139 行，距子开始 60.17118936998304 秒；第 148 行是之后的饱和记录，在约 61.5274091239844 秒达到 30.000000374 秒测得观察器 CPU，callback 计数 18,132,876、hotspot events 713,868。饱和后的 profile 覆盖 UNKNOWN；没有最终 observer-status 或 retirement/restoration 确认。不能把最后 checkpoint 当作饱和记录或完成场景。

较早的 main-thread 栈摘录反复出现 local copy、decode、semantic/history 验证；早期区间还包含观察器与资源 profile。最后完整 checkpoint 中 `_copy` 已记录 311,810 次调用，`LocalEnvelope.from_payload` 49 次调用、48 次 return 事件。这支持“本次带仪器运行的前缀存在大量复制与验证工作”的有限假设。Return 事件可以是异常展开，inclusive wall/CPU 时间相互嵌套，不能相加，也不能据此证明断言成功、原基线性能、SIGSEGV 或原 600 秒非完成的根因。

ROOT 归档算数来源是 R362 `root-independent-arithmetic.json`（tool `294072`，SHA256 `7e12ca84749b03267880998b7f7f0eadb7eff2b12462f32e31d84798188f33a3`），本报告仅转录，不重算。OS 的 55/55 个 eligible result `completed_monotonic - observed_monotonic` span 最大为 0.004541469010291621 秒，位置是**一基 result record 28**。此 span 排除 `observed_monotonic` 之前的 setup，不能称为完整 guard elapsed。原始 JSONL 的 pre-receipt span 最大为 0.0016216319927480072 秒，位置是**一基 raw JSONL line 7**，还排除 append 和后续簿记。Result 的 guard_overrun 55 个均记录 false，须与这两种 span 分开理解。

CPU 端点经过同 PID/starttime/CLK_TCK=100 核对：55 个样本覆盖 269.99525773499045 秒，user 增加 109.09 秒、system 增加 161.15 秒。这与本次进程持续消耗 CPU 相容，但包含仪器工作及多线程成本，不能证明某个函数、扩展或锁的责任。末次报告有 18 个线程，采样只选择最多 16 个真实 TID，并非全线程覆盖。没有把原生十六进制线程地址映射为 OS TID；thread delta 也不能绕过 TID/starttime 身份要求。`wchan` 是瞬时上下文，不是锁 owner 证据。

`stack-offset-map.json` 转录九个 pre-request 文件 size 至下一 size/最终长度的增长区间及其哈希。18 行请求是九个 intent/outcome 对；`SIGNAL_SYSCALL_RETURNED_NOT_STACK_ACK` 只证明 kill syscall 返回，不能作为完整 dump ACK、独占区间或因果栈。区间 1–8 各有一个 Current thread header。第九区间 `[76832,77146)` 只有 314 字节，缺失 Current thread header，包含 `operational_lease.py` 的 `_rpc`、`line ???`，截断于 `File `。不能把它当作崩溃主栈、故障指令或锁 owner；冻结 `_rpc` 存在两处 wait，未知行号不能选择其中一处。

第九次提交时间 252675.775778051 与首次观察到非零退出 252675.876453007 相差 0.10067495598923415 秒。它是观测时序关联，不是信号导致崩溃的证明或因果延迟。信号处理/unwinding 与解释器或 native 状态的相互作用、独立的产品/扩展缺陷等均仍是未区分的假设。stderr 列出的已加载扩展只能证明存在，不能指认责任模块。没有证据把本次崩溃与 R311 的历史 SIGSEGV 合并同因，也不能把它替换成 R350 的 timeout 原因。

R361-B 是独立行政 schema 读取错误：tool `2268ac` 把 stack 的 `actual_monotonic` 当成 OS 字段，触发 KeyError。实际 OS 用 `observed_monotonic`；stack 用 `actual_monotonic/submitted_monotonic`。原输出 `maximum_guard_elapsed=0` 来自缺失字段默认值，本报告明确撤销它作为测量证据的资格。缺失/null/非法值应为 UNKNOWN，bool 不作为数字。Raw JSONL 的 pre-receipt 字段不能用稍后 result 中添加的完成时间回填。原命令、输出和 raw keys 不改。

后续报告准备时发生的 Delete/Add 同路径 patch 被工具验证拒绝，未生效；17,842 字节草稿保留未解析、未执行。R362 改用四份手写报告，未制造 generator stdout/stderr/result。以上行政处置不修复、也不解释真实 SIGSEGV。

若下一步需要区分信号交互、native/interpreter 状态或工作量问题，必须先由实际 Astra 制定新的有限计划，明确假设、最小源范围、新命令身份、时间/资源/输出/cleanup 及双 ledger 单次 reservation。本报告没有授权禁用信号、切换 profile、延长 timeout、重跑节点或新增 native/DB/proc 探针。R354 两侧 SPENT1/0，R350 三 SPENT/六 HELD 均不重开；所有根因判断保持 UNKNOWN，等待 ROOT 对这组静态报告独立验收。
