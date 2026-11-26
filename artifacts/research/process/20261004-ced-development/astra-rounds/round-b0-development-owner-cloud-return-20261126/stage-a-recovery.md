# A 的原失败与恢复边界

gpt-6.2-astra 核定。真实 SQLite 与 runtime 在历史曝光的 complete_capture 处抛出外层 RuntimeError，原计划预计的是时钟门内部的 ValueError。保留 A 的原驱动、异常日志与两份 SQLite。用只读连接核对作业、租约、attempt、采集 claim 和旧帧原身份，复算 captured_at < claimed_at，确认无后续提交且无独立 owner 异常。

现行 SQLite 将 derive_bootstrap 的 ValueError 或 TypeError 转成无提交，runtime 再抛通用异常。实测原件证明旧帧违反时钟且 gateway 拒绝。原异常归因不能由外层字符串唯一确定。冷读还可用封存输入单独重算底层时钟门，单列该重算结果。后续不重跑 A。通过只读冷读时才允许 B 启动，B 的一次真实复位、120 个 settle 步、三次曝光和零主动命令额度保持。
