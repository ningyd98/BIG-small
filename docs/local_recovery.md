# 本地恢复

Phase 6.1 的本地恢复是确定性的，并且由 repository 保存状态。

## 组件

- `LocalRecoveryManager`：评估 `EdgeEvent`，返回 `LocalRecoveryDecision`。它不执行机器人动作，也不伪造成功。
- `LocalRecoveryExecutor`：在配置了 `SafetySkillExecutor` 时，执行明确的本地恢复动作。
- `RetryBudgetService`：负责初始化重试预算、判断是否允许重试、原子消耗预算、记录结果审计和读取剩余预算。
- `TaskExecutor`：在 `EventTriggeredModeController` 返回 `RETRY_STEP` 后，重新执行同一个 `TaskStep`。

## 安全边界

每一次重试都是普通的 `SafetySkillExecutor.execute_attempt` 调用。也就是说，重试会重新读取遥测和场景，重建 `SafetyContext`，运行 SafetyShield 前置检查，执行技能，并在机器人动作成功后运行后置检查。

验证来源：

- `scripts/verify_phase6.py` 第 4-8 项检查。
- `tests/test_phase6_e2e_executor.py::test_task_executor_event_mode_retries_failed_step_before_next_step`。

## 重试预算语义

`RetryBudgetService` 使用任务级剩余池。当前重试的有效额度按下式计算：

```text
min(current_step.retry_limit, skill_policy.limit, task_remaining_limit, safety_policy.limit)
```

repository 使用 compare-and-swap 语义消耗重试预算：

- 内存实现：加锁比较 `retry_count_used`。
- SQLite 实现：单事务执行 `UPDATE ... WHERE retry_count_used = ? AND remaining_retries > 0`，并插入 `recovery_attempts`。

验证来源：

- `tests/test_phase6_e2e_executor.py::test_budget_cas_prevents_double_consume`。
- `scripts/verify_phase6.py` 第 8 和第 9 项检查。

## 失败行为

预算耗尽时，本地恢复不会继续执行下一步。控制器会创建并持久化失败摘要和重规划请求，写入 outbox 消息，并转入 `WAITING_CLOUD_REPLAN` / runtime `WAITING_CLOUD_UPDATE`。
