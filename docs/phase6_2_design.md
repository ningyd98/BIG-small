# Phase 6.2 设计

Phase 6.2 的目标是收紧事件触发边缘自治闭环，但不启动 Phase 7。范围只包括校验、加固、测试、文档和 CI。

## 权威状态

`EventAutonomyRepository` 是 checkpoint 的权威来源。边缘侧在任务开始、步骤开始、步骤成功、步骤失败、请求云端重规划、恢复开始和完成校验时写入 `ExecutionCheckpoint`。云端重规划必须从同一个 repository 读取 active contract、触发事件、`FailureSummary` 和最新 checkpoint。request ID 只是标识符，系统不能通过切割 request 字符串推导 `task_id`。

`InMemoryEventAutonomyRepository` 只用于测试和仿真。持久化重启验收必须使用 `SQLiteEventAutonomyRepository`。

## 重规划合并规则

`ReplanMergeValidator` 在组装新合约前校验 partial replan：

- 已完成 step ID 必须与 checkpoint 完全一致。
- 已完成步骤必须保留，内容逐字节不变，顺序不变。
- 替换步骤不能复用已完成的 `step_id`。
- 合并后的 contract 不能包含重复 step ID。
- 已完成的非可重复技能，例如 `GRASP`、`PLACE`、`RELEASE`，不能被重新生成。
- 低层执行器字段和安全绕过字段会被拒绝。

只有 validator 通过后，`ReplanContractAssembler` 才会创建新的可信 contract。新 contract 的 `plan_version` 和 `command_seq` 必须严格递增，`current_step_id` 指向第一个待执行步骤，并保留旧 active contract 的已完成前缀。

所有时间敏感的重规划组件都接受可注入 clock。`LocalReplanningService`、`ReplanApplyService`、`ReplanContractAssembler` 和 replanner adapter 必须使用配置的 clock 生成响应时间、合约组装时间、校验时间、ACK 和 rejection 记录。

## CAS 与幂等

`ReplanApplyService` 是 active contract 更新的唯一写入方。它通过 `advance_active_contract_if_current()` 校验期望的 `plan_version` 和 `command_seq`。基于旧 active contract 的过期结果必须返回 `VERSION_CONFLICT`，不能覆盖更新后的 active contract。

repository 幂等以 hash 为准：

- 同一个 idempotency key 加同一 payload，返回已存储对象。
- 同一个 idempotency key 但 payload 不同，抛出 `IdempotencyConflictError`。
- 重复完成证据使用确定性的 `cs-{task_id}` summary ID 和语义化 `summary_hash`；相同证据返回原 summary，冲突证据被拒绝。

## 崩溃恢复

崩溃恢复流程：

1. 边缘侧执行任务，直到重试预算耗尽。
2. 边缘侧持久化 event、`FailureSummary`、replan request、outbox message 和 checkpoint。
3. 进程对象可以被销毁。
4. 云端或重启后的进程重新打开同一个 SQLite 数据库。
5. 云端从 SQLite 读取 active contract、event、summary 和 checkpoint。
6. 通过 CAS 生成并应用重规划。
7. 重启后的 `TaskExecutor` 从持久化 checkpoint 和新 active contract 恢复执行。
8. 已完成步骤被跳过；失败步骤在新 contract 下重新执行；后续步骤继续执行。

## 完成证据

任务成功不能由调用方自行宣布。`TaskExecutor._complete_task()` 会调用 `CompletionEvaluator`，检查步骤完成情况、终态、完成条件、最终安全决策、机器人状态、目标状态、场景新鲜度、关键事件和 `VERIFY_RESULT`。

云端 completion API 也必须先评估证据，再持久化 summary。伪造或不完整的 completion request 返回 422，且不会创建 `CompletionSummary`。

## 边界

Phase 6.2 不实现以下内容：

- Phase 7 skill cache。
- AUTO mode selection 或双模式自动切换。
- 基于风险的调度。
- 真实机械臂、真实 telemetry 和真实 scene provider。
- CI 中执行外部 planner 生产 adapter。

Phase 7 尚未开始。
