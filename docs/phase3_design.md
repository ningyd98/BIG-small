# Phase 3 设计：独立边缘安全盾与确定性安全执行门控

## 范围边界

Phase 3 实现边缘安全盾（Safety Shield），包括 StopController 真实停机语义、22 条安全规则、
约束合并策略、Watchdog 超时检测和安全配置加载。不实现 MQTT、FastAPI 云端任务接口、
云端规划、大模型调用、周期云端监督、事件触发云端重规划或真实机械臂 SDK。

## 执行链路（Phase 3 增强）

```text
TaskContract
  -> EdgeContractValidator
  -> Repository.accept_command
  -> TaskRuntimeContext
  -> TaskStateMachine
  -> SafetyShield.pre_check       ← NEW
  -> SkillRegistry
  -> SkillExecutor
  -> RobotAdapter
  -> SafetyShield.post_check      ← NEW
  -> Repository
  -> AuditLog
```

## StopController

当任务进入 SAFETY_STOPPED 时，TaskExecutor 调用 StopController：

1. 调用 `robot.stop()` 并验证 `RobotState.stopped`。
2. 若 stop 失败或状态不可确认，调用 `robot.emergency_stop()`。
3. 验证 `stopped` 或 `estop_engaged`。
4. 将停机 ActionResult 写入 `action_executions`。
5. 写入安全停机审计日志。
6. 两种停机均失败时返回 `SAFETY_STOP_FAILED`。
7. 只有完成停机尝试后才能将任务转为 `SAFETY_STOPPED`。

## 安全盾架构

```text
src/cloud_edge_robot_arm/edge/safety/
├── __init__.py          # SafetyShield 入口
├── models.py            # SafetyContext, SafetyRuleResult, SafetyEvaluationResult, 等
├── policy.py            # OperationalSafetyPolicy, MergedSafetyConstraints, merge_constraints
├── shield.py            # SafetyShield, load_safety_config
├── rule_registry.py     # RuleRegistry, SafetyRuleEvaluator 基类
├── rules.py             # 22 条安全规则实现
├── stop_controller.py   # StopController
├── watchdog.py          # Watchdog 超时监控
├── workspace.py         # 工作空间边界检查
├── reachability.py      # 可达性检查
├── kinematics_limits.py # 运动学限制
├── obstacle.py          # 障碍物距离检查
├── freshness.py         # 场景/遥测新鲜度检查
└── errors.py            # 安全错误码
```

## 安全模型

### SafetyDecision

| 决策 | 优先级 | 说明 |
|------|--------|------|
| EMERGENCY_STOP | 6 | 立即急停 |
| REJECT | 5 | 拒绝执行 |
| PAUSE | 4 | 暂停等待 |
| REQUEST_CORRECTION | 3 | 请求修正 |
| ALLOW_WITH_LIMITS | 2 | 限制参数后允许 |
| ALLOW | 1 | 允许执行 |

### 安全规则清单（22 条）

1. **CMD_EXPIRED** - 指令过期检查
2. **TEL_FRESH** - telemetry 新鲜度
3. **SCENE_FRESH** - scene 新鲜度
4. **SCENE_VERSION** - scene_version 一致性
5. **CTX_MATCH** - 任务、计划、命令上下文匹配
6. **DEV_CONNECTED** - 设备连接状态
7. **ESTOP** - 急停状态
8. **COLLISION** - 碰撞状态
9. **WORKSPACE** - 工作空间
10. **FORBIDDEN** - 禁入区
11. **REACHABILITY** - 位姿可达性
12. **TCP_VEL** - 最大 TCP 速度
13. **JOINT_VEL** - 最大关节速度
14. **ACCEL** - 加速度限制
15. **MIN_HEIGHT** - 最低安全高度
16. **CARRY_MARGIN** - 携带物体安全余量
17. **OBSTACLE** - 障碍物安全距离
18. **PATH_COLLISION** - 起终点路径碰撞
19. **STEP_TIMEOUT** - 步骤超时
20. **TASK_DEADLINE** - 任务截止时间
21. **WATCHDOG** - Watchdog 超时

### 约束合并

有效安全约束 = min(hard_limit, operational_policy_limit, task_contract_limit, device_limit)

云端和任务契约只能收紧约束，不能放宽本地硬限制。

### 禁止绕过

以下参数名被安全盾拒绝：`disable_safety`, `bypass_safety`, `ignore_collision`, `force_execute`。

## 时间处理

- UTC wall clock：合同绝对截止时间
- `time.monotonic()`：运行超时和 Watchdog

检查点：第一个步骤前、每个步骤前、每次重试前、机器人动作前、动作后。

## 配置

- `configs/safety/default.yaml` - 默认配置
- `configs/safety/strict.yaml` - 严格配置
- `configs/safety/test.yaml` - 测试配置

配置启动时校验 Schema，计算 policy_hash，记录版本，非法配置拒绝启动。

## 新增和修改文件

新增：
- `src/cloud_edge_robot_arm/edge/safety/` (13 个文件)
- `configs/safety/` (3 个配置文件)
- `tests/test_phase3_stop_controller.py`
- `tests/test_phase3_safety_shield.py`
- `tests/test_phase3_safety_repository.py`
- `scripts/run_phase3_*.py` (7 个脚本)
- `scripts/verify_phase3.py`
- `docs/phase3_design.md`
- `docs/safety_policy.md`
- `docs/safety_rules.md`
- `docs/phase3_acceptance.md`
- `docs/phase3_report.md`

修改：
- `src/cloud_edge_robot_arm/edge/runtime/task_executor.py` - 集成 StopController + 连接验证
- `src/cloud_edge_robot_arm/simulation/mock_robot.py` - auto_connect 默认 False
- `pyproject.toml` - 添加 pyyaml 依赖
- 所有现有测试 - 适配 auto_connect=False
- 所有现有脚本 - 适配 auto_connect=False
