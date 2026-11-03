# R399 最终代码与证据独立审查

**Assessment: Not ready for delivery. `ready_for_delivery=false`。** 已审查的 SQLite 修复及 native MOCK 证据未发现 Critical / Important / Minor 代码问题；必需的 foreign-owner guard 尚未取得通过证据，R399 原 1800 秒预算已经耗尽。不得把 native 成功当作 guard 豁免。

本报告审查工作树内容，不是已提交的修复。Base 和审查时 HEAD 均为 `ac6351b66a6dd05fb67aadd59935ce5726748709`。产品 `src/cloud_edge_robot_arm/repositories/event_autonomy/sqlite.py` SHA256 为 `7d73669b175da19e278593b7db063740255a368a391915c59ea13001f5d93173`；最终 `tests/test_eteac_retry_lock_regression.py` SHA256 为 `1e74f8c3b03ceeb4bbcba6f8b6af4eb223268abff419782bf0b32314badff589`。**Candidate manifest absent / null：没有审查、批准或虚构交付清单，没有授权进入 Git 交付。** 索引未写入、两项原 dirty gitlinks 由实施者报告保持原样；本审查未进入 gitlinks 内部。

## Strengths

- 独立阅读完整限定产品 diff、六个读取体、调用处及 `protocol.py` 分派后，重新以只读 stdlib AST 比较：六个 helper 的读取体与 base 原函数体逐项一致；原其它方法只归一化七种 `self` 调用名称后全部一致。普通 `Lock`、连接上下文、`BEGIN IMMEDIATE`、内部 legacy guard、提交标志、CAS、SQL、哈希检查、深拷贝与回滚顺序保留。没有改 protocol、memory、worker、dispatcher 或产品超时。
- 外部 public getter 仍经过原装饰器，外部 `list_recoveries` 仍调用 public getter；仅已持锁的内部链使用私有读取体。独立静态展开实际持锁区域的 141 个 self 调用、35 个可达方法，未发现残留 wrapped-reader 边。该结论是静态源码检查，不冒充任意动态调用的形式化证明。
- 原 RED 是真实仓储死锁：子进程先输出调用入口，栈为 `protocol.py:215 -> sqlite.py:976`；8.012 秒内 kill/reap，外层 pytest 正常返回 1 failed。不是导入失败或外层 pytest 超时。修复后四个新仓储回归通过；原仓储模块 272 passed；visual 模块 220 passed、4 个原有 backend 专属 skip；worker 短测 4 passed。已检查 result、JUnit、cleanup，并阅读两连接竞争、预算冻结、CAS、回滚故障注入、重启及拷贝断言。
- R402 精确修正了测试身份关联。独立比对冻结旧测试与最终测试，仅 `experiment.run_id` 改为 `experiment.experiment_id`，其它断言保持。`worker.py:1812` 将 job.run_id 放入配置 experiment_id；`runner.py:814–821` 保留它作为结果 experiment_id，而结果 run_id 是 `stable_run_id` 的确定性哈希，并非随机值。
- R402 唯一 fresh-DB successor 自然通过：ETEAC 1.563512 秒、预排队 PCSC 1.692480 秒，各自 task_success=true、SUCCEEDED、attempt1，attempt 已结束、lease 已释放。ETEAC 返回时 PCSC 仍为 QUEUED / attempt0，随后真正被第二次 poll 消费。两次返回后 heartbeat 列表和运行 SQLite FD 列表为空；阶段 0 signals、已 reap、无存活后代、无源漂移。
- Native receipt 官方 source_tree_hash 为 `25b44519b8db3187f1376522ed983792de2a2b5e239513c82857d4c82f246912`，实际 source pinset SHA 为 `fa42f56a74eea705925e6739c11cdbea23b0e5474f158dd986b720eb07818802`。独立重算 pinset 哈希并核对其全部 22 个文件字节，均一致。receipt 明确说明 patched worktree 与修复前 HEAD 的区别；不把历史 manifest 当作修后来源。

## Critical

无已发现的 Critical 代码问题。

## Important

无已发现的 Important 代码问题。下列验收阻断单列为 blocked gates，不能据此宣称交付已完成。

## Minor

无需在本轮扩大范围处理的 Minor 代码问题。

## Blocked gates

1. **FOREIGN_OWNER_GUARD_UNVERIFIED**：R399 原 combined operational fences 保持 TIMEOUT（180.041 秒、SIGTERM）；其中 memory call 138.021 秒及 teardown 通过。R401 SQLite successor 自然通过，但 remaining nodes 为 1 failed / 4 passed。失败在 `tests/test_operational_windows.py:890` 的 `captured(runtime)` 前置 reserve 路径，`operational_windows.py:887` 抛出 `OperationalTimeError: original transition obligations unavailable or exhausted`；尚未创建被测 foreign thread。不能称线程隔离断言失败，也不能称这些断言通过。根因尚未确证。
2. **R399_BUDGET_EXHAUSTED**：原时钟 2026-11-02 16:11:09 UTC 开始，1800 秒于 16:41:09 UTC 结束，未刷新。R403 计划仅允许一次原节点观察；实施者报告 adapter 在 invocation / Popen 之前因读取 `audit['pins']`、实际字段为 `inputs` 而抛 KeyError，未启动 pytest 子进程。R404 的 schema/空目录 gate 计划因原预算已耗尽而未实施。此末段未执行状态依据实施者最终关闭通知记录，不冒充审查员运行验证。

## Evidence honesty and limitations

原 RED、combined TIMEOUT、R401 前置失败以及原 native 错误身份断言失败均保留。原 native 只完成 ETEAC，不能作为 pair 成功；pair 成功仅来自 R402 successor。四个 skip 是原有 backend 不适用项，不能计为通过。worker 短测的 Starlette / AnyIO 弃用 warning 也保留，不属于本次锁修复范围。R402 测试快照改变已披露；产品与 guard 模块保持冻结不等于所有阶段完整 pinset 一致。

本审查只执行源码、文本、JSON、JUnit、hash 与 AST 读取；未运行产品、pytest、仓储 helper、SQL、网络或信号操作。未改产品、测试、计划、index 或 HEAD；只写本审查的两份最终记录。既有运行结论来自保存证据，未额外重复 probe。无 candidate，因此未审查精确交付排除表，也未证明提交/推送/远端 SHA 对齐。

## Declined to judge

- 全 4732 suite、T3 长 case 与新浏览器重测：实际 Astra 计划限定之外，未运行，不能声明通过。
- 19 项历史浏览器失败全部消除：本轮仅确证锁因与 native MOCK 队列回归，缺少对应浏览器证据。
- RGBD / MuJoCo / 物理机器人 / 正式研究验收：未运行，不属于此次开发软件验收。
- 完整远端 raw 复现包及 DB / WAL / SHM / 缓存 / 凭据 / 权重 / SDK 交付：未进入交付清单审查，派生报告不代表完整包。
- R401 foreign-owner 前置失败的确切根因：现有错误和栈不足以区分 source、descriptor、lease、clock、ownership；R403 未启动，不作猜测。
- 两项 dirty gitlinks 内部变化：用户要求保护且不纳入本轮，本审查未进入内部。

## Recommendations

保留修复工作树和全部失败证据。后续取得符合项目 Astra 流程的实际执行计划及预算后，先解决 R403 adapter 前置问题并取得原 guard 目标自然通过证据；随后生成明确 candidate 清单并重新完成剩余交付验收。不得刷新本轮时钟、伪称 guard 聚合通过或提前提交推送。

## Assessment

**Ready for delivery: No.** 已审查的最小锁修复与自然 native 队列行为有充分聚焦证据；剩余 guard 和预算门未通过，因此整体研发交付仍未完成。本报告仅是关闭与保留记录，不是新增运行授权。
