# UTC codec 性能修复

输入核验覆盖原计划的 31 项快照，并额外核对历史 memory 工件的 SHA256。原两个节点合计 600 秒超时和先前 watchdog 崩溃原件均留存。UTC 替身的时钟源与外层 monotonic 计时独立，开发诊断将耗时定位到实际 worker 调用的本地 codec。

## 实施与反馈

- 保留外部 strict snapshot 与完整嵌套 history 校验。codec 的公开导出从已验证的不可变 JSON 生成独立新对象，去掉该导出的重复重拷贝。纯投影在本次严格校验后使用同一树的子记录。
- 历史回放先完整验证 request，再使用 enclosing snapshot 的相同字段和投影。每次部署运行仍执行 lease、owner、CAS 和真实时钟检查。R315 成功项 memo 的完整字节与类型键、128 项和 8 MiB 上限、上下文所有权与生命周期规则保留。
- UTC 用例单独用 CPython code-local 事件观察真实 poll、session 等入口和返回。分析型 profiling 的旧行为留给相邻故障用例。UTC 用例的 AST 去掉观察器开关后与原版一致。
- 新回归在原代码的两个预期失败分别观察到 43,271 次重复 strict-copy 调用和 7 次独立根校验。修后验证了独立可变导出和每次外部投影只做一次根校验。包括这两项在内的 48 项 codec、安全和 UTC 边界回归全部通过，耗时 16.15 秒。

## 性能和输出验证

从原 evidence 读取完整生产 route、supervision、staged adoption，以及已冻结 promotion，对照独立规范 JSON 与投影。四者的规范字节、摘要和投影均一致。代表样本无 profile 的当前裸解码 wall 为 route 0.427 秒、supervision 0.687 秒、staged adoption 0.035 秒、full promotion 0.024 秒。旧相同 route 和 supervision 分别为 1.018、3.326 秒。[观察器严格对照执行记录](../round-utc-observer-probe-20261118/step-report.md)

原始开发证据在工作树的 `experiments/results/phase9/real-harness-20261118/utc-codec-performance/`，包括 `input-verification.json`、`red.log`、`red.xml`、`green-codec-final.log`、`green-codec-final.xml`、`representative-codec.log` 及四组独立观察器资源记录。开发验证全程使用 CPU 软件工厂。

## 原 600 秒联合门

**PASS。** 原始 memory、SQLite 两节点按原顺序在同一次 pytest 调用中全部通过。外部 monotonic 用时 **381.627 秒**，上限 600 秒，退出 0，未重试。pytest 报 2 passed，1 条 Starlette/AnyIO 弃用警告。运行使用指定 CPU 7、15，BLAS/OMP 单线程，pytest 原生 faulthandler 关闭。执行期间的因果源文件哈希固定，原测试除观察器切换外经 AST 对照一致。

两个节点各有三个实际 poll、两个 UTC 偏移情景和一个迟到边界情景。六次 poll 均正常返回，原始资源证据的清理错误为空，观察器均恢复。原 startup 两项、terminal 三项与 public 两项也各自通过，完整输出和角色/清理资源记录单独保存在本轮 raw 目录。此次通过是 CPU 软件门的验收结果。 [联合回执](verification/result.json) · [JUnit](verification/pytest.xml) · [回归和哈希汇总](verification/summary.json)
