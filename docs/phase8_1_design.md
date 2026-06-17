# Phase 8.1 设计

Phase 8.1 用来补上 Phase 8 留下的实验有效性缺口。它不引入新的机械臂行为；目标是让实验层驱动既有 Phase 3-7 runtime chain，并从真实 repository、ACK、安全决策、执行记录和模式切换记录中采集证据。

## 范围

- 保留 Phase 8 的模型、CLI、batch runner、artifact 和可复现实验入口。
- 用 `RuntimeExperimentHarness` 替换 runner 侧的合成结果。
- 保持 `TaskExecutor`、`SafetyShield`、`PeriodicSupervisorService`、`EventTriggeredModeController`、`LocalReplanningService`、`ReplanApplyService` 和 `ModeTransitionService` 的生产语义。
- 指标只从正式事件和 repository 中记录。

## 架构

- `RuntimeExperimentHarness` 用注入的 `VirtualClock`、`MockRobotAdapter`、SQLite/in-memory repository、安全 provider、risk evaluation、AUTO selection 和 transition service 组装真实 runtime graph。
- `ExperimentRunner` 只负责调度故障、推进虚拟时间、投递命令和收集结果。
- `ExperimentMetricsCollector` 从 audit event、execution record、ACK record、supervisor decision、replanning record、mode transition、safety evaluation、network event 和 cache record 重建指标。

## 证据来源

- Contract validation：validator 调用和 accepted command record。
- Execution：`TaskExecutor` step record、checkpoint state 和 completion evidence。
- Safety：safety decision、reject 和 emergency-stop record。
- PCSC：supervisor decision 和 cloud invocation event。
- ETEAC：retry-budget consumption、failure summary、replan 和 CAS apply。
- AUTO：持久化 decision、prepared transition、commit、abort、dwell、cooldown 和 switch-limit record。
- Crash recovery：repository reopen 和 restart verification。

## 兼容性

- 不要求消费者修改 Phase 3-7 数据模型。
- observer 和 clock 注入是可选项，默认保持原行为。
- AUTO 仍只是两个既有执行模式之间的选择器。
