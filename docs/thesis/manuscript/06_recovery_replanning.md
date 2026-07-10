# 第六章 边缘自治和局部重规划

边缘端事件检测器覆盖完成、超时、网络、执行、设备、安全、场景和目标变化。LocalRecoveryExecutor 受 retry budget 约束，避免无限重试。若本地恢复失败，FailureSummary 提供失败类型、已完成步骤、现场状态和重规划约束。CompletedStepsProtectionValidator 和 ReplanMergeValidator 保证局部重规划不覆盖已完成步骤。Phase 11.1 Simulation Runtime 使用 SQLite、worker lease、heartbeat、restart recovery 和 duplicate worker competition evidence 保持运行恢复语义。

