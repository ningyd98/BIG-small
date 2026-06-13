# Phase 2 设计：任务契约驱动的边缘执行运行时

## 范围边界

Phase 2 只实现边缘侧运行时，不实现 MQTT、FastAPI 云端任务接口、云端规划、大模型调用、
周期云端监督、事件触发云端重规划、完整安全盾或真实机械臂 SDK。

## 执行链路

```text
TaskContract
  -> EdgeContractValidator
  -> Repository.accept_command
  -> TaskRuntimeContext
  -> TaskStateMachine
  -> SkillRegistry
  -> SkillExecutor
  -> RobotAdapter
  -> Repository records
  -> AuditLog
```

## 状态机

状态集合：

```text
CREATED VALIDATING READY EXECUTING LOCAL_RECOVERY WAITING_CLOUD_UPDATE
PAUSED SAFETY_STOPPED FAILED COMPLETED
```

合法转换由 `LEGAL_TRANSITIONS` 显式声明。非法转换返回结构化错误
`INVALID_STATE_TRANSITION`，并保持原状态不变。`TaskRuntimeContext.state` 是只读属性，
只能由 `TaskStateMachine.transition()` 推进。

## TaskRuntimeContext

运行时上下文保存：

- `task_id`
- `plan_version`
- `command_seq`
- `state`
- `contract`
- `current_step_id`
- `current_step_index`
- `completed_step_ids`
- `failed_step_id`
- `step_attempts`
- `task_started_at`
- `task_deadline`
- `last_transition_at`
- `last_error`

## 技能执行器

`SkillRegistry` 使用 `SkillName` 显式映射到 `SkillDefinition`，每个技能都有 Pydantic
参数模型。`SkillExecutor` 的顺序是：

1. 参数模型校验；
2. 前置条件校验；
3. 调用固定 handler；
4. 成功条件校验；
5. 生成 `StepExecutionResult`。

参数校验失败和前置条件失败不会调用机械臂动作。

## 重试策略

最大尝试次数：

```text
min(step.retry_limit, failure_policy.local_retry_limit) + 1
```

可重试错误：

- `GRASP_FAILED`
- `ACTION_TIMEOUT`
- `RESULT_NOT_VERIFIED`

不可重试错误：

- `COLLISION_DETECTED`
- `EMERGENCY_STOP_ACTIVE`
- `ROBOT_DISCONNECTED`
- `INVALID_TARGET_POSE`
- `TARGET_UNREACHABLE`

`COLLISION_DETECTED` 和 `EMERGENCY_STOP_ACTIVE` 进入 `SAFETY_STOPPED`，其他不可恢复错误进入
`FAILED`。

## Repository

仓库抽象位于 `src/cloud_edge_robot_arm/repositories/base.py`，实现包括：

- `InMemoryRepository`
- `SQLiteRepository`

持久化记录：

- `tasks`
- `task_state_transitions`
- `step_executions`
- `action_executions`
- `accepted_commands`
- `audit_events`

## 防重放

`accepted_commands` 按 `task_id + command_seq` 持久化，同时保存 `plan_version` 和
payload hash。

- 相同序号、相同 payload：`COMMAND_SEQ_REPLAYED`
- 相同序号、不同 payload：`COMMAND_SEQ_CONFLICT`
- 小于等于已接受最大序号：`COMMAND_SEQ_REPLAYED`
- 落后 `plan_version`：`STALE_PLAN_VERSION`

SQLite 持久化保证进程重启后重复指令仍会被拒绝。

## 重启恢复

`recover_interrupted_tasks()` 扫描处于 `EXECUTING` 的任务，不自动继续运动，而是：

1. 状态切换到 `PAUSED`；
2. 写入状态转换记录；
3. 写入审计事件 `RUNTIME_RECOVERY_REQUIRED`；
4. 等待后续显式恢复操作。

## 审计事件

当前记录：

- `CONTRACT_RECEIVED`
- `CONTRACT_ACCEPTED`
- `CONTRACT_REJECTED`
- `TASK_STATE_CHANGED`
- `STEP_STARTED`
- `STEP_RETRYING`
- `STEP_COMPLETED`
- `STEP_FAILED`
- `TASK_COMPLETED`
- `TASK_FAILED`
- `SAFE_STOP_TRIGGERED`
- `RUNTIME_RECOVERY_REQUIRED`
