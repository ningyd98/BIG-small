# Phase 3.2 设计：真实安全意图解析、运行时安全数据接入与完整集成验收

## 范围边界

Phase 3.2 修复 Phase 3/3.1 中的类型约束、伪造时间戳、目标二次计算、速度/加速度默认 0、
ALLOW_WITH_LIMITS 未实现、集成脚本绕过 TaskExecutor 等问题。

## 核心变更

### 1. 类型约束
- `shield` 参数从 `Any` 改为 `SafetyShield`（无默认值）
- 构造时 `isinstance` 检查 → 非 SafetyShield 立即 TypeError
- mypy 可静态验证 shield 接口

### 2. 运行时 Provider
- `TelemetryProvider` Protocol：提供 `TelemetrySample(timestamp, tcp_velocity, joint_velocities, acceleration)`
- `SceneStateProvider` Protocol：提供 `SceneSnapshot(scene_version, updated_at, obstacles)`
- `MockTelemetryProvider` / `MockSceneStateProvider`：支持 missing、stale、正常三种模式
- TaskExecutor 默认使用 Mock 实现，可注入自定义 Provider
- 不再伪造时间戳 — 缺失时直接传递 None → fail closed

### 3. SkillSafetyIntentResolver
- 从 `resolve_target_pose(skill, params) → Pose` 获取单一目标位姿源
- `SafetyExecutionIntent`：current_pose, target_pose, path_start, path_end, requested_tcp_velocity, requested_acceleration, resolved_parameters
- 速度/加速度解析优先级：显式参数 > telemetry > 本地保守默认（记录来源）
- 所有运动技能（HOME/MOVE_ABOVE/APPROACH/LIFT/MOVE_TO_REGION/PLACE/RELEASE/RETREAT）均支持

### 4. 单真源目标位姿
- `RuntimeSkillRobot` 协议新增 `resolve_target_pose`
- `MockRobotAdapter.resolve_target_pose` 实现与运动方法相同的几何计算
- 运动方法接受 `resolved_target`、`tcp_velocity`、`acceleration` 参数
- Handlers 将解析后的目标传递给机器人 — 安全盾检查和执行使用相同目标
- `MotionParams` 扩展支持 `tcp_velocity`、`acceleration`、`target_pose`

### 5. 真实速度/加速度
- `SafetyContextBuilder.build` 接受 `requested_velocity`、`requested_joint_velocities`、`requested_acceleration`
- 不再默认 0
- 维度：`absolute_max_*`（硬限制）vs `merged_*`（软限制）

### 6. ALLOW_WITH_LIMITS 真实实现
- `TcpVelocityRule`：requested ≤ merged → ALLOW；merged < requested ≤ absolute → ALLOW_WITH_LIMITS；> absolute → REJECT
- `JointVelocityRule` / `AccelerationRule` 同理
- `SafetyShield.pre_check` 聚合所有规则的 `limited_parameters`
- `SafetySkillExecutor` 将限幅参数传递给机器人，原始参数写入审计

### 7. Post-check 状态传播
- error.details 包含 `safety_decision`、`rule_id`、`reason_code`、`policy_version`、`policy_hash`
- PAUSE → PAUSED；REJECT → FAILED；EMERGENCY_STOP → StopController → SAFETY_STOPPED

### 8. 安全审计事件
- `SAFETY_EVALUATION_STARTED`、`SAFETY_RULE_PASSED`、`SAFETY_RULE_FAILED` 等
- 每条包含 `task_id`、`plan_version`、`command_seq`、`step_id`、`rule_id`、`decision`、`reason_code`、`policy_version`、`policy_hash`、`measured_value`、`limit_value`

### 9. 验证
- 所有集成脚本通过 TaskExecutor + TaskContract
- 无手动 SafetyContext 构造（verify_phase3_2.py 检查）
- 119 项测试 + 22 项集成测试
- ruff、mypy、pytest 全部通过
