# R390 浏览器排队与目标可达性离线诊断

本轮只分析 R377 已结束运行的冻结证据，没有启动服务、产品测试、模型或新的物理采集。实际 Astra R390 计划和 R392 单字段修正均先完成独立静态审查；唯一隔离分析退出 0，内部耗时 0.084775 秒，stderr 为空。63 项输入及 10 份已关闭 trace 的 SHA256 匹配，原数据库 DB/WAL/SHM 元组前后保持原字节。SQLite 只打开取证副本，显式 `uri=True`、`mode=ro` 与 `query_only`，各表读取不超过 10000 行。

副本观察包含 14 个 job、2 个 attempt、79 个 event、2 个 lease。PCSC `sim-619c21103d71` 已成功，记录开始 10:59:34.193821、完成 10:59:35.697114 UTC。随后 ETEAC `sim-6364857a907b` 为 RUNNING/attempt 1，开始 10:59:36.009520、更新 11:06:46.974494 UTC，完成/attempt ended/lease release 均为空；记录跨度为 430.964974 秒，配置 timeout_seconds 为 30。其余选定任务仍为 QUEUED/attempt 0，包含三个 MuJoCo capture 任务。

源码显示 dispatcher 同步轮询 worker，heartbeat 另在线程运行。现有证据支持“ETEAC 同步执行未记录完成/返回，后续任务未领取”，但无线程栈或返回探针，不能定位到 runner.run、清理或某把锁。内部停点 UNKNOWN，死锁与性能根因 NOT_PROVEN。配置中的 30 秒不等于已证明的异步中断或包含排队的端到端 SLA；queue_position 来自 queued_count，也不是精确队列排名。

三个 RGBD 场景分别停在未到 SUCCEEDED、capture 仍 QUEUED 且尚未提交 visual-planning、published_groups 为 0 且尚未发出 cancel 请求。不能据此宣称渲染、视觉规划或取消逻辑已经执行并失败。R377 的 19 项失败或错误继续开放。

独审结论为 `APPROVED_R390_BOUNDED_OFFLINE_EVIDENCE_SCOPE`，无 Critical/Important/Minor。下一次主动探针、产品修复、等待或并发策略修改及重跑均需新实际 Astra 计划。本轮无剩余分析重试额度。完整数据库和 forensic-copy 留在本地；交付的派生诊断与清单不是完整远端复现包，也不构成真实硬件、性能或正式研究验收。

证据入口：[终态](analysis/diagnostic-result.json)、[输入冻结](analysis/input-freeze.json)、[目标映射](analysis/case-target-map.json)、[副本观察](analysis/database-copy-observations.json)、[最终独审](review/code-review.md)。
