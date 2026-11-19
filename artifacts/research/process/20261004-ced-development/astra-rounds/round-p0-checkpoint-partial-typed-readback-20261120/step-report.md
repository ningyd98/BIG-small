# EGL 诊断部分终态的类型核验

修复后，诊断运行出口仍返回已发布的完整部分结果。它要求外层和内层均属于本次开发登记，canonical 登记哈希一致，两层资格均为严格整数 0，并且唯一 primary 是首动作 8 秒截止。运行出口再将原 worker 异常携带的快照与回执快照核对。坏 JSON、错结构、伪造截止和无关运行异常走原异常路径，原异常对象保留。现有来源 finally 核查仍执行。 [Astra 计划](plan.md) [验证、原件哈希与软件诊断](typed-readback-summary.json)

用同一新解析分支只读回放了原封存终态。返回对象与原文件完整相等，canonical 编码逐字节一致；原 worker 终态仍是 `BLOCKED_BY_ENV`，原 CLI 退出码仍是 1。登记文件的 SHA256 与 canonical 登记哈希各自绑定。确认 456 件冻结源、92 件受保护输入及原 SQLite、claim、两次独立读回和正式 reader 拒绝结果保持原字节。EGL、任务模型和新 claim 均为 0 次。 [原件核验](typed-readback-summary.json) [实际运行报告](../round-p0-teacher-checkpoint-egl-development-20261120/step-report.md)

定向回归先保留 31 个计划内失败和 6 个通过，修后 37 项通过，作用域内 Ruff 通过。mypy 在原基点为 31 项，在实测源为 32 项，修后为 31 项。按目标文件名和完整诊断文本逐项比较，原有 31 项全部一致，新增的 `no-any-return` 已消除。 [静态逐项对照](typed-readback-summary.json)

补测原冻结源的监测开销。固定单核，9 批各 15,000 次，在已有只读快照中测得 SQLite 上下文统计开销中位数 2.145 微秒。守卫的单调钟采样和数据类转换为 1.323 微秒。该离线夹具未执行生产 SQL 查询、I/O、worker 派发及物理推进。 [离线计时记录](typed-readback-summary.json)
