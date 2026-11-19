# EGL 开发诊断的网络审计计数

封存的 `process-end.json` 中，`network_attempts` 是内容为空的 JSON 数组。新的离线摘要核定开始与结束记录来自同一进程，取该数组长度，得出 **0 个 Python 审计钩子命中的网络事件**。这个计数覆盖已登记的地址解析、连接和发送事件。任务模型请求单列为 0，正式资格单列为 false。原包装与运行记录保持原字节。 [Astra 计划与输入哈希](plan.md) [离线摘要](network-audit-summary.json)

旧的补充检查将数组与整数比较，退出 1。现场终端的 AssertionError 只保留了观察转录，证据等级仍为 `observed_terminal_only`。此前正式出具的两次开发独立读回均退出 0，输出逐字节一致。正式资格 reader 退出 1，并报 `registered operational calibration protocol required`。新摘要保留三类读回的原哈希与退出状态。 [离线摘要](network-audit-summary.json)

新工具两次独立运行生成同一 SHA256 `17a6138433c5ba9d50ce54584cc7d258d015beb5fb81124ef0580b420646c1e3`。13 项小样例通过，覆盖合法非空事件及重复次数、缺字段、错误类型与未知事件。验收仅读原件，EGL、云、模型及设备调用均为 0。 [离线工具](read_network_audit_summary.py)
