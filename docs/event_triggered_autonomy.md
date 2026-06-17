# 事件触发边缘自治

本文说明 Phase 6.1 已实现并验证的事件触发边缘自治路径。

## 范围

已实现内容：

- API 同时声明 `EVENT_TRIGGERED_EDGE_AUTONOMY` 和 `PERIODIC_CLOUD_SUPERVISION`。
- `AUTO` 控制模式不在本阶段范围内，API 不对外声明。
- 边缘事件通过 `EventAutonomyRepository` 持久化。
- 本地重试决策通过 `RetryBudgetService` 管理预算。
- 预算耗尽时创建 `FailureSummary`、`LocalReplanningRequest` 和 outbox 消息，然后执行等待云端更新。
- 任务完成由 `CompletionEvaluator` 判断；只把步骤跑完不等于任务成功。

不在本阶段范围内：

- Skill Cache。
- AUTO 模式选择。
- 双模式自动切换。
- 风险调度。

## 运行流程

已验证的本地重试路径如下：

```text
TaskExecutor
→ SafetySkillExecutor pre-check
→ robot action
→ SafetySkillExecutor post-check
→ CompositeEventDetector
→ EventTriggeredModeController
→ LocalRecoveryManager.evaluate
→ RetryBudgetService.consume_if_available
→ RETRY_STEP
→ 同一个 TaskStep 再次通过 SafetySkillExecutor 执行
```

回归测试 `tests/test_phase6_e2e_executor.py::test_task_executor_event_mode_retries_failed_step_before_next_step` 验证了机器人动作顺序：

```text
APPROACH, GRASP, GRASP, LIFT, MOVE_TO_REGION, PLACE, RELEASE, VERIFY_RESULT
```

因此更短的不变量也成立：

```text
APPROACH, GRASP, GRASP, PLACE
```

## 持久化状态

控制器通过配置好的 `EventAutonomyRepository` 保存事件模式状态，不依赖进程内字典。SQLite 实现会创建事件、重试预算、尝试记录、状态转移、摘要、重规划请求/结果、outbox、审计事件和计划版本表。

验证来源：

- `scripts/verify_phase6.py` 第 10-15 项检查。
- `tests/test_phase6_e2e_executor.py::test_sqlite_restart_preserves_state`。
- `tests/test_phase6_e2e_executor.py::test_sqlite_outbox_retry_wait_survives_restart_and_reclaims`。

## 生产配置

`EventTriggeredModeController(runtime_profile="production")` 会拒绝缺失的 repository 配置。生产环境必须明确提供 SQLite 或其他持久化 repository。内存 repository 只用于测试和 CI。
