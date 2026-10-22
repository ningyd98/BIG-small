# RPC 与执行链路修复交付（2026-10-23）

## 已完成

当前选定的开发验证链路已通过，所有运行均有实际工具返回、JUnit、原始日志、源码指纹和独立审阅记录。

- 观察器改为只在相关生命周期事件采样，并正确记录尚未安装到 worker 字段的 session，消除无关 profile 事件反复扫描 worker 历史的问题。
- PlannerDraft 按 Pydantic JSON 模型序列化，保留 None、嵌套时间和全部字段。
- 重启历史摘要按四个实际提交阶段核对精确操作编号和独立 SQL 行；保留无权限、无伪造回执和原预算不回填断言。

## 实际结果

| 检查 | 结果 | 用时 |
| --- | --- | --- |
| observer_green | 1 passed，0 skipped | 1.025 秒 |
| observer_serialization | 1 passed，0 skipped | 0.424 秒 |
| observer_detached_summary | 1 passed，0 skipped | 0.522 秒 |
| dual_behavior | 1 passed，0 skipped | 260.506 秒 |
| wait_memory | 1 passed，0 skipped | 12.952 秒 |
| wait_sqlite | 1 passed，0 skipped | 11.451 秒 |

双库测试覆盖 4 次真实 COMMIT 后同连接关闭、4 次重启无权限、同一 owner 的新提交／精确历史重复／变更请求拒绝。两后端分别覆盖 D_app 和 D_lease 的真实锁等待、计数器推进与过期拒绝。最终三项行为运行共记录 3060 次资源分配尝试并全部清理，18 对新数据库及归档在本地保留。

原始 RPC 超时、序列化 TypeError、首个阶段预期失败和观察器预期 RED 均保留；通过记录不覆盖旧失败。详细机器可读出处见 [step-report.json](step-report.json) 和 [phase-summary.json](phase-summary.json)。

## 交付边界

这些结果关闭当前选定的软件开发卡点，不构成整个 T2、P6、T12、原生硬件或正式研究验收。原有 35 个数据库和 90 个 sidecar 缺失没有恢复。运行数据库、模型权重、SDK、凭据及批量 raw 沿用既有交付边界。

117653675 字节的双库聚合证据保留本地原件，按 R308 计划新增可逐字节还原的 gzip 和恢复清单；九个 case 原文件同时提交。该交付不是完整远端 raw／数据库复现包。
