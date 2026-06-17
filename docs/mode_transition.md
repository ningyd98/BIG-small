# 模式切换

Phase 7 的模式切换建模为显式记录，而不是简单改一个字符串。

`ModeTransitionService` 支持：

- `prepare`
- `commit`
- `abort`
- 复用幂等 key
- 检测 payload 冲突
- 记录预期模式版本和新模式版本

`AutoModeRepository` 通过 InMemory 和 SQLite repository 持久化切换记录和模式状态。SQLite 重启恢复可以找到 `PREPARED` 切换，并在编排边界确定性地继续或回滚。

## 安全边界

普通模式切换只能发生在任务开始前、原子步骤完成后、`PAUSED`、`WAITING_CLOUD_UPDATE`，或显式安全停止恢复后。

切换不能重置已完成步骤、checkpoint、active contract、plan version、command sequence、重试预算、失败历史或完成历史。

SafetyShield 拒绝、急停和严重设备故障优先级最高，AUTO 不能覆盖它们。
