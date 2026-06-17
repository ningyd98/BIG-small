# 安全设计

系统在边缘侧执行机器人动作前后都进行安全约束。

## SafetyShield

`SafetyShield` 使用确定性规则评估 `SafetyContext`。规则覆盖 command freshness、telemetry freshness、scene freshness、scene version、device connection、emergency stop、collision、workspace、forbidden zone、reachability、velocity、acceleration、minimum height、obstacle/path/carry safety、step timeout、task deadline 和 watchdog check。

## 运行时集成

`TaskExecutor` 必须持有 `SafetyShield` 实例。`SafetySkillExecutor` 从以下信息构造 `SafetyContext`：

- 已校验的 `TaskContract`。
- 当前 robot state。
- 最新 telemetry provider sample。
- 最新 scene provider snapshot。
- 技能专用 resolved intent。
- 配置好的硬性安全限制和运行安全限制。

对 motion skill，安全检查和机器人动作使用同一份 resolved target 与受限参数。

## 事件模式重试

本地恢复重试不能绕过安全检查。`RETRY_STEP` 结果会让同一个任务步骤再次通过 `SafetySkillExecutor` 执行，因此 telemetry、scene、context construction、pre-check、action execution 和 post-check 都会重新运行。

对应验证：

- `scripts/verify_phase6.py` 的第 6 项。
- `tests/test_phase6_e2e_executor.py::test_task_executor_event_mode_retries_failed_step_before_next_step`。

## 完成安全

`CompletionEvaluator` 要求最终安全决策为 allow，并且 robot state 安全。只有 completed step list 不能生成成功结果。

## Fail-Closed 行为

telemetry 或 scene timestamp 缺失时可以暂停执行。emergency stop 和 collision 条件会触发 safety-stop。validation failure 和未处理的 completion criteria 会阻止成功。
