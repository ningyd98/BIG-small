# Phase 4 设计：云端初始任务规划服务

## 范围边界

Phase 4 实现云端初始任务规划服务，包括：
- 结构化规划器适配层
- 安全任务契约生成流水线
- FastAPI 云端 API
- 模型不可信边界强制
- 边缘网关（InProcess）

不实现：MQTT、周期云端监督、事件触发重规划、局部重规划、技能缓存、真实机械臂 SDK。

## 核心架构

```
InitialPlanningRequest
  → 请求校验（幂等性、request_id 冲突检测）
  → 场景充分性检查
  → PlannerAdapter（Mock / RuleBased / OpenAICompatible）
  → 严格 JSON 解析
  → TaskContract Schema 校验
  → 语义校验
  → 有限修复（最多 2 次）
  → 可信字段补齐
  → 持久化
  → 可选 EdgeGateway dispatch
```

## 模型不可信边界

模型不得决定：task_id、plan_version、command_seq、issued_at、valid_until、安全策略版本、云端请求 ID。

拒绝模型输出中的：joint_angles、motor_commands、PWM、servo_pulse、trajectory_points、disable_safety、bypass_safety、ignore_collision、force_execute、未注册技能。

## PlannerAdapter

- **MockPlannerAdapter**：确定性固定输出（CI 使用）
- **RuleBasedPlannerAdapter**：无 LLM，基于启发式规则构建契约
- **OpenAICompatiblePlannerAdapter**：调用 OpenAI 兼容 API（密钥从环境变量读取）

## 安全加固（Step 0）

- `RUNTIME_PROFILE=test|simulation|production`
- production 模式禁止自动使用 Mock providers
- Telemetry 无关节速度时使用 intent 保守默认
- post-check 使用真实 telemetry 速度/加速度

## 目录结构

```
src/cloud_edge_robot_arm/cloud/
├── api/           # FastAPI 端点和 schema
├── planning/      # 规划流水线、适配器、提示词注册表
├── gateway/       # EdgeGateway 协议和 InProcess 实现
└── repositories/  # 云侧持久化（InMemory）
```
