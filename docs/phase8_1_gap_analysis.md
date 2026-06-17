# Phase 8.1 差距分析

Phase 8 已经提供了确定性的实验框架，但 runner 里仍混有一部分实验侧的合成结果。Phase 8.1 不改 Phase 8 的模型、CLI、场景、artifact 和复现实验入口，重点是把这些合成结果替换为真正驱动 Phase 3-7 控制链的运行时 harness。

## 已发现的合成行为

- `ExperimentRunner._run_network_warmup()` 会先安排网络投递，再调用 `VirtualClock.run_until_idle()`。场景故障也挂在同一个时钟上，因此动态故障可能在任何原子步骤开始前就触发。
- `ExperimentRunner._execute_step()` 直接推进虚拟时间、记录遥测和命令、写入 `SafetyDecision.ALLOW`、标记步骤完成，并用递归方式模拟抓取重试；它没有调用 `TaskExecutor`。
- `_execute_scenario()` 中的场景分支直接设置 safety、replan、cache、SQLite restart 和 command rejection 计数。
- S10 目前只记录 stale、duplicate 和 reordered command 计数，没有把异常或过期命令交给边缘命令校验路径。
- `_cloud_invocations()` 根据已完成步骤数和模式公式推导云端调用次数，而不是读取 supervisor、planner 或 replanning service 的真实记录。
- `_apply_fault()` 用常量填充故障检测和恢复延迟，没有从故障、检测、ACK 和恢复事件中计算。
- `_switch_mode()` 调用 `ModeTransitionService.prepare()` 后立即修改 `current_mode`，没有真正经历持久化状态的 commit/abort 边界。
- `_simulate_sqlite_restart()` 只对 auto-mode 和 event-autonomy repository 做最小写入后重开，没有覆盖 risk snapshot、decision、transition、replan、checkpoint、outbox、command ACK 或技能执行统计等崩溃点。

## 可复用的生产入口

- 合约校验与命令接收：`edge.contract_validator.EdgeContractValidator.accept_payload()`，以及 `repositories.memory`、`repositories.sqlite` 中的 `TaskRepository.accept_command()`。
- 执行链路：`edge.runtime.task_executor.TaskExecutor.submit_contract()` 已经串起 `TaskContract -> EdgeContractValidator -> TaskStateMachine -> SafetyShield -> SafetySkillExecutor -> SkillRegistry -> MockRobotAdapter -> repositories`。
- 安全链路：`edge.safety.shield.SafetyShield` 和 `edge.safety.safety_skill_executor` 会向 runtime repository 写入 safety audit event。
- PCSC：`cloud.supervision.service.PeriodicSupervisorService.evaluate_snapshot()` 与 `cloud.supervision.repository.*SupervisionRepository` 已覆盖 snapshot、supervisor decision、planner invocation flag、version CAS 和 audit event。
- ETEAC：`edge.event_mode.controller.EventTriggeredModeController`、`edge.recovery.retry_budget.RetryBudgetService`、`cloud.replanning.service.LocalReplanningService` 和 `cloud.replanning.apply_service.ReplanApplyService` 已覆盖事件检测、重试预算、失败摘要、outbox、云端重规划、CAS apply、ACK 持久化、checkpoint 合并和恢复执行。
- 模式切换：`auto_mode.selector.AutoModeSelector`、`auto_mode.transition_service` 和 `auto_mode.repository.*AutoModeRepository` 已支持持久化 risk snapshot、decision、prepared transition、status、commit、abort、幂等和重启查询。
- 技能缓存：`skill_cache.repository.*SkillCacheRepository` 已支持可信查找、执行记录、promotion、quarantine、invalidation、CAS、幂等和 SQLite 重启。
- SQLite 恢复：runtime、supervision、event autonomy、auto-mode 和 skill-cache repository 都已有持久化实现；Phase 8.1 只需要一个实验级重启 harness，在相同文件上关闭并重建服务。

## 集成策略

- 新增 `RuntimeExperimentHarness`，作为实验侧唯一的组装层。它负责构造真实合约、repository、`TaskExecutor`、`SafetyShield`、`MockRobotAdapter`、`PeriodicSupervisorService`、`EventTriggeredModeController`、`LocalReplanningService`、`ReplanApplyService`、`RiskEvaluator`、`AutoModeSelector`、`ModeTransitionService` 和缓存 repository。
- 给生产执行组件增加可选 observer hook，默认行为不变。hook 只把 repository/audit 事实镜像到实验事件中，并在 mock action 执行期间推进 `VirtualClock`。
- 移除任务前的 `run_until_idle()`。故障使用绝对虚拟时间，只在任务执行或显式网络投递推进时钟时触发。
- 命令一致性实验通过 harness 的 command-ingress 方法进入，必须走 `EdgeContractValidator`、repository 命令接收、scene-version 检查和持久化 `CommandAck` 记录。
- AUTO transition 先持久化 decision 和 prepared transition，再在步骤边界通过 harness 方法 commit 或 abort。当前模式从已提交的 `AutoModeStatus` 读取。
- 新增 `ExperimentMetricsCollector`，从正式事件、runtime repository、command ACK、supervisor decision、replan/apply 记录、mode transition、safety audit、network event 和 cache record 里重建指标。

## 必要适配器与夹具

- `VirtualClockAdapter`：向使用 clock protocol 的服务暴露 `now()` 和 `monotonic()`。
- `ExperimentTelemetryProvider` 与 `ExperimentSceneProvider`：基于虚拟时间、`MockRobotAdapter` 和 `SimulatedWorld` 的确定性安全 provider。
- `ExperimentExecutionObserver`：记录步骤开始、完成、失败、安全评估和任务终态证据，但不决定结果。
- `ObservableMockRobotAdapter`：或在 `MockRobotAdapter` 上提供可选 callback，用于记录动作开始/结束并推进虚拟动作时长。
- `CountingPlannerAdapter` 与 `CountingReplannerAdapter`：确定性 mock adapter，输出正式云端调用事件，同时保持 planner 输出的高层语义。
- S15 崩溃点 C1-C9 需要临时 SQLite 目录。夹具必须关闭并重建 repository/service，不能复用旧对象。

## 兼容性约束

- Phase 3-7 的数据模型不需要破坏性字段变更。
- 新增的 observer/clock 参数必须有默认值，保持现有构造函数、序列化、SQLite payload 和测试兼容。
- `AUTO` 仍只是实验模式选择器；提交后的 runtime 状态仍为 `PERIODIC_CLOUD_SUPERVISION` 或 `EVENT_TRIGGERED_EDGE_AUTONOMY`。
- 安全反事实指标只允许作为 shadow metric，绝不能把未检查动作送进 `TaskExecutor`。
