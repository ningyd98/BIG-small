# Phase 3.1 设计：安全盾强制集成、真实规则补全与 fail-closed 收口

## 范围边界

Phase 3.1 将安全盾强制集成到 TaskExecutor 和 SkillExecutor 主执行链路中，补全所有占位规则的真实实现，
实施 fail-closed 逻辑，并确保所有安全上下文数据来自真实运行时。

## 执行链路（Phase 3.1 完整）

```text
TaskContract
  -> EdgeContractValidator
  -> Repository.accept_command
  -> TaskRuntimeContext
  -> TaskStateMachine
  -> SafetySkillExecutor
    -> SafetyContextBuilder.build (from real robot_state, contract, timestamps)
    -> SafetyShield.pre_check
    -> 安全决策处理 (ALLOW/ALLOW_WITH_LIMITS/PAUSE/REJECT/EMERGENCY_STOP)
    -> RobotAdapter handler
    -> 刷新机器人状态
    -> SafetyShield.post_check
    -> 成功条件验证
  -> Repository
  -> AuditLog
```

## SafetyContextBuilder

从真实运行时构造 SafetyContext：
- `robot_state`：connected, stopped, estop, collision, tcp_pose, holding_object
- `contract`：plan_version, command_seq, scene_version, safety_constraints
- `step`：step_id, skill, parameters
- `scene_updated_at` / `telemetry_timestamp`：真实时间戳
- `step_started_at` / `task_started_at_mono`：time.monotonic()
- `merged` constraints：从 SafetyConfig.merged 获取

## SafetySkillExecutor

包装 SkillExecutor，在每次执行前后添加安全门控：
- `pre_check`：参数校验 → 前置条件 → SafetyContextBuilder → SafetyShield.pre_check
- 安全决策处理：ALLOW/ALLOW_WITH_LIMITS → 执行；PAUSE/REJECT/EMERGENCY_STOP → 拒绝
- `post_check`：动作完成后刷新状态，调用 SafetyShield.post_check

## 安全决策映射

| 决策 | 后续动作 |
|------|----------|
| ALLOW | 执行原参数 |
| ALLOW_WITH_LIMITS | 执行 limited_parameters |
| REQUEST_CORRECTION | 不调用机器人，返回结构化错误 |
| PAUSE | 不调用机器人，任务进入 PAUSED |
| REJECT | 不调用机器人，任务进入 FAILED |
| EMERGENCY_STOP | 调用 StopController，确认停止后进入 SAFETY_STOPPED |

## fail-closed 规则

| 缺失数据 | 决策 |
|----------|------|
| telemetry_timestamp | PAUSE |
| scene_updated_at | PAUSE |
| task_started_at_mono (watchdog) | REJECT |
| step_started_at | REJECT |
| step 不存在 | REJECT |
| command_valid_until / wall_clock_now | REJECT |
| task_deadline_utc | REJECT |
| collision_check_required=True 但无障碍物数据 | PAUSE |

## 真实规则实现

1. **PathCollisionRule**：三维线段-球形障碍物最短距离，支持 TCP 半径、工具半径、carry margin
2. **AccelerationRule**：检查 requested_acceleration vs merged.max_acceleration
3. **CarrySafetyRule**：携带物体时扩大 obstacle clearance 和 path clearance
4. **MinimumHeightRule**：低高度例外需要 scene 数据新鲜
5. **WorkspaceRule**：同时检查 current_pose 和 target_pose
6. **ReachabilityRule**：检查 target_pose 距离 vs merged.max_reach_m
7. **所有规则**：使用 merged constraints (min of hard, operational, contract, device)

## StopController 状态一致性

两种停机均失败时：
- 返回 `success=False`
- 记录 `SAFETY_STOP_FAILED` 审计事件（带 critical=True）
- 任务标记为 `FAILED`（非 SAFETY_STOPPED）
- 禁止自动恢复

## 约束合并

所有规则使用 `merged` constraints：
- `merged_max_tcp_velocity`
- `merged_max_joint_velocity`
- `merged_max_acceleration`
- `merged_minimum_safe_height`
- `merged_max_reach_m`
- `merged_obstacle_safety_distance`
- `merged_carry_safety_margin`

任务契约不得关闭本地强制 collision check。
