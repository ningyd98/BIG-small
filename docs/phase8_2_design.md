# Phase 8.2 设计

Phase 8.2 继续限定在 mock/virtual 实验范围内，不加入 ROS 2、MoveIt 2 或真实机械臂集成。

## 周期 PCSC 闭环

PCSC supervision 通过 `VirtualClock` 按 `supervision_period_ms` 调度。第一个 tick 在首个周期后触发，随后只要 PCSC 仍处于活动状态就继续调度。mock robot action 会推进同一个虚拟时钟，因此 tick 会与 `TaskExecutor` 的步骤执行交错，而不是在提交任务前一次性跑完。

每个 tick 通过 `RuntimeExperimentHarness._edge_snapshot()` 读取当前 harness 状态：当前步骤、已完成 step id、scene version、target/obstacle 状态、robot 状态，以及 checkpoint 推导的完成状态。ETEAC 不启动这个 tick loop。AUTO 会先 prepare transition；PCSC tick 只在提交为 PCSC 执行后启动，并在离开 PCSC 时停止。

## 故障检测

故障注入现在只记录 `fault_injected`。`fault_detected` 必须由 runtime 来源发出：

- `PeriodicSupervisorService` tick 检测 scene、target、obstacle、network、cloud 和 emergency-stop 观测。
- `TaskExecutor` 结果事件检测失败或暂停的原子执行。
- network monitor callback 检测 reconnect 和 heartbeat delivery。
- cloud timeout callback 由虚拟时钟调度触发。

检测延迟从 `fault_injected_at` 到同一 fault type 的第一个后续 `fault_detected` 事件计算。

## 安全边界模式切换

AUTO mode 不再在 prepare 后立即 commit。transition 会先记录为 prepared/deferred，执行仍留在旧模式。只有当 `TaskExecutor` 发出终端安全边界事件，也就是 `step_completed` 后，pending transition 才能 commit。如果没有到达安全边界，transition abort，当前模式保持不变。

计数器覆盖 deferred、aborted、dwell-block、cooldown-block 和 switch-limit-block decision。

## 恢复

S15 覆盖 9 个 restart point。每个点都会关闭并重建 runtime repository，记录 recovery，并在不重复已完成步骤的情况下恢复到合法终态。recovery payload 包含 `command_seq`、`plan_version` 和 checkpoint progress，用于防止回滚。

## 实验敏感性

网络消息全部通过 `NetworkSimulator` 发送，因此 latency、jitter、loss 和 reordering 会影响 PCSC command arrival、recovery heartbeat delivery、ETEAC cloud upload 和 replan application timing。batch summary 包含 mode x scenario、network x scenario、mode x network 和 seed variability 视图。
