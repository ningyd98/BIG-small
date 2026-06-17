# 失败摘要

`FailureSummary` 是边缘执行交给云端重规划的持久化交接件。

## 创建时机

当本地恢复无法继续时，`EventTriggeredModeController` 会创建失败摘要，包括重试预算耗尽和需要重规划的决策。

摘要会先持久化，再发送 outbox 请求。

## 内容

模型至少记录：

- 失败事件身份。
- 失败步骤 ID 和技能。
- 已完成步骤 ID。
- 重试次数和重试上限。
- 请求的重规划范围。
- 可用时的场景和机器人上下文字段。
- 确定性的摘要哈希。

## repository 操作

`EventAutonomyRepository` 支持：

- `save_failure_summary`
- `get_failure_summary`

内存和 SQLite 实现都可用。SQLite 会把原始 payload 存在 `failure_summaries.payload_json`，并按 task 建索引。

## 验证

行为由以下内容覆盖：

- `scripts/verify_phase6.py` 第 12 项检查。
- `tests/test_phase6_recovery_replanning.py` 的失败摘要构建测试。
- `tests/test_phase6_e2e_executor.py` 的预算耗尽/重规划路径检查。

单独的摘要并不代表恢复成功。完成与否要由 `CompletionEvaluator` 另行判断，并在验证后持久化为 `CompletionSummary`。
