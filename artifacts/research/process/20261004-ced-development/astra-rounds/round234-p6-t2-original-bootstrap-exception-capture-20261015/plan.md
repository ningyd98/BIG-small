# R234：原始异常旁观采集计划

实际作者 `/root/astra_status_plan`，实际模型 `gpt-6-astra`。仅计划；ROOT 全文/输入/角色门后才允许一次独立诊断运行。

R233 已真实完成 6 个只读连接、66 SQL，原始字节不变，但没有保存内层异常。Memory 只有 QUEUED/attempt0；SQLite 两例只有 INTERRUPTED 和末端 original worker poll ended。不能从这些末端状态推定修复。Memory writer 的 task KeyError 仍是次生清理唤醒，本轮不改。

## 输入与最小范围

完整输入索引 `input-observation.json`：27767 bytes，SHA256 `feb7a33c110a5f97b82c890d226dcbaf01a0eb436125bf364c03bd61418487e1`，绑定 15 项证据、27 current/archive 源对、211 保护清单与 8 个旧角色时间点。所有旧测试、观察器、产品和 runner 都不修改。原 race test 全部字节保持，故不需要新 race helper。

只允许原唯一 Sol 新写 `implementation/r234_exception_observer.py` 与 `implementation/run-capture.py`。ROOT 完整读源码和有限 diff 后冻结新 pin；不运行 import、静态、collector 或额外试探。

## 旁观合同

新 pytest 插件仅在本轮子进程内，用独立 sys/threading trace 通道围住每个精确节点的 setup/call/teardown。保留并 finally 恢复先前 trace；若已有 trace，分配夹具前拒绝并如实记录。原 profile 通道完全不改。

只匹配已核实绝对文件、co_qualname 和首行：SimulationWorker._execute:242；OperationalLeaseSession.__init__:417、_serve:654；VisualWorkerRuntime._initialize_local:420。保存实际异常类型/消息、有限原始 traceback/cause、线程/事件身份。_serve 仅额外记录六个明确源码里程碑首次 line event。它们只是行事件，不冒充 readiness 或权限。

不包装真实方法，不改 __code__/globals，不通过 wrapper 获权，不重采 OC1、不调 wait/deadline。回调只缓冲有限原始数据，不调用产品、不做文件 I/O、不持有产品锁。每节点最多512事件、32帧、3层cause、8KiB消息、1MiB trace；只有精确 queue.Empty 空闲事件可实际计数压缩。任何丢失/越界/回调错误必须标 incomplete，不能静默通过。

在精确 session.__init__ 的异常事件处，还可一次旁观既存 startup_error、ready状态、真实 broker ident；仅按该 ident 取最多16帧的当前 broker 栈，不取locals、不读其他线程、不等待/重采clock/重试初始化。结果是非原子时间点观察；不存在或不足时仍unknown，不能臆断死锁。有限cause/context同时保留。

trace 本身可能影响时序。未复现、换一种异常或测试通过都只是诊断结果，不作为修复、合法 RED 或 GREEN。旧402仅是原观察器实际分母，不代表所有未单独观察的部分初始化broker均被计数；本轮也不得以补充trace伪造资源close。

## 一次预算与证据

新增独立 `R234_exception_capture` 1次，无重试；仅原三个 race 节点，精确 argv/env 在 JSON。600秒 child + 15秒总清理界限。原R223/R232命令不重用。新 basetemp `/tmp/bigsmall-p6-r234-capture`；全部证据写本轮 `implementation/capture/`。

同一次命令内保存前后27源/211保护和新脚本/角色证据，启动真实 pytest 加显式插件。完整 stdout/stderr、JUnit、3条 trace、case/resource、文件索引、真实进程清理和 toolreturn 必须先保存再判定。退出0/1且精确3节点并不等于产品通过；只可判采集是否完整。实际资源分母来自本次记录，不能沿用旧402或假设每节点固定数。未观测仍为null。

独立 runner 的短 stdout ≤6000 UTF-8 bytes。所有代码先由 ROOT 全文/SHA/精确参数门控，不在规划中执行。

## 结算与停止

R233诊断、R232两槽、R223原两槽仍永久spent；两个旧RED仍非legal。原R223四槽、父GREEN7继续HELD。旧settler与R232continuation不改不运行。无新静态/Git/审查槽。

ROOT 仅结算本轮独立一次采集，并可 full-before/CAS 更新 STATE planning.R234 事实、PHASE追加；不得改变既有验收字段。取得原异常或如实unknown后 STOP，另请实际Astra制定精确修复/新baseline/合法RED方案。本轮不预授权修复；T2/T12/native/formal 均 false。
