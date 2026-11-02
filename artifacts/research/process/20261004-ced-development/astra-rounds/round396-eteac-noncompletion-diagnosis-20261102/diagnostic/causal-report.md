# ETEAC 不结束的定位结论（R396）

结论：本次使用原冻结请求语义的真实 MOCK worker 复现，确认 ETEAC 在重试预算初始化发生同线程自锁死锁。它尚未进入正常场景执行循环，也没有进入 harness.close。产品代码未修改。

## 实际证据

同一个真实 SimulationWorker 和新隔离 SQLite job repository，按 PCSC→ETEAC 各执行一次原 poll_once，S01/seed0、LEGACY_PIPELINE、NORMAL、cache enabled、retry2、supervision300ms、timeout30000ms 保持原请求语义。新 manifest 明示 DEVELOPMENT_ONLY、当前源码提交及独立 source pinset；原 manifest 仅历史记录，source_tree_hash 未计算。

PCSC 原生 SUCCEEDED，attempt1，耗时 6.015125242 秒，返回后租约线程已结束。ETEAC 进入原 TaskExecutor → EventTriggeredModeController.initialize_task → RetryBudgetService.initialize → SQLiteEventAutonomyRepository.initialize_retry_budget_if_absent。

在 ETEAC 开始后 5、15、35、65 秒的四组全线程原生栈和 frame 快照中，MainThread 始终相同，repository self_id=127610451227424、lock_id=127610430543232 始终相同。外层 sqlite.py:976 停在 self.get_retry_budget 调用；其所在 sqlite.py:973 的 with self._write_lock 尚未退出。内层 protocol.py:215 在 get_retry_budget 装饰器内再次 with 同一 lock，scope=None、locked=true。构造器 sqlite.py:121 使用普通 threading.Lock，不可重入。结合控制流和同线程、同对象、同锁身份，确认它在等待自己释放锁。没有将稳定栈单独当作证明，也没有声称 profile 捕获到了 C __enter__。

进入/返回边界共 71 条，没有被采样上限截断、observer error 或 reporting error。ETEAC runner.run、harness.submit_contract 和原 initializer 均各进入一次、返回0次；close 进入0次。底层 get_retry_budget 原函数尚未进入，卡点在其装饰器加锁前。

## 为什么 30 秒超时没有结束它

SimulationWorker._execute 在 worker.py:296 同步调用 _run，只有返回后才在 :297 检查 timeout；_run 进入分支前的检查也无法覆盖后来发生的无限锁等待。MOCK _run_mock 在 :1196 同步调用 runner.run，未向该锁等待提供中断机制。ETEAC 仅观察到进入前的 timeout 检查，超过30秒的35秒和65秒快照仍在同一锁处；不是一个独立超时线程在30秒时强制终止 runner。

simulation-lease 是另一线程，四组 ETEAC 栈中均存在并在等待下次心跳；历史 R390 数据显示心跳持续更新且 lease 未释放。这解释了工作无进展时仍显示 RUNNING/租约有效。此处没有额外查询新旧运行 DB，也没有把线程存在等同于逐次 DB 心跳成功证据。

## 为什么后续浏览器场景也被拖住

SimulationJobDispatcher.poll_once（dispatcher.py:84-90）在同一 dispatcher 线程中按固定 backend 顺序同步调用各 worker.poll_once。MOCK 的 ETEAC 不返回，该次调用就无法推进到后续 worker/任务，也无法进入下一轮。历史冻结 DB 中后续任务保持 QUEUED、attempt0，与此链路一致。它支持解释排队/等待类失败，不能把未到达的 RGBD、规划或取消路径记为已执行的功能失败，也不能把全部19个浏览器问题归为这一根因。

## 验收边界

唯一 supervisor 耗时81.622711040秒；ETEAC达到75秒诊断上限后，以校验身份的自有进程组 SIGTERM 结束，child returncode=-15，已 reap、无遗留自有进程，cleanup≤10秒。35项源/证据 pins 前后相同，无网络拒绝或额外运行，AUTO/MuJoCo/模型/硬件调用为0。诊断按计划完成取证，ETEAC 原生终态仍未产生；强制截断不是产品 timeout/cancel 成功或软件 PASS。

当前复现强支持历史 E2E07 的 ETEAC 长时间 RUNNING 与同一根因有关，但 R377 历史运行没有自己的内部栈，不能声称直接证明原进程栈。本轮没有修产品、重跑浏览器或提升真实运行/正式研究验收。

下一修复轮应由实际 Astra 根据本轮证据限定方案，同时保护 repository 公共读取/写入/私有 scope 的并发与事务语义，并验证同请求 ETEAC 真正返回及后续调度恢复。不能把单纯提高超时作为该死锁的修复。
