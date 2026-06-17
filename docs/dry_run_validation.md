# Dry-Run 验证

Phase 10.2A-R 没有新增 dry-run 类型，只把已有边界写清楚：Synthetic Dry-Run 和 MoveIt Runtime Dry-Run 是两件事，不能混用结论。

Dry-run 验证只跑软件安全链路，不发送硬件命令：

```text
TaskContract -> EdgeContractValidator -> SafetyShield -> dry-run planner
```

契约和安全检查都通过时，输出状态为 `DRY_RUN_VALIDATED`。硬件执行状态仍是 `PLANNED_ONLY`，证据里必须写入 `hardware_motion_observed=false`。

当前有两个 dry-run 层级：

- Synthetic dry-run：`planner_backend=SYNTHETIC`，`moveit_runtime_used=false`，`collision_validation_claimed=false`。
- MoveIt dry-run：`planner_backend=MOVEIT_RUNTIME`，`moveit_runtime_used=true`，轨迹摘要来自真实 MoveIt planning service。

两者都不能连接真实控制器。MoveIt dry-run 只能说明规划服务可用，不是硬件只读验证，也不是物理任务验证。
