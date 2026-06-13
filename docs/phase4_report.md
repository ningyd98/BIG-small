# Phase 4 阶段报告

## 1. 本阶段完成摘要

Phase 4 实现了"云端初始任务规划服务、结构化规划器适配层与安全任务契约生成"。

## 2. Step 0 安全加固

- `RUNTIME_PROFILE=test|simulation|production`
- production 模式禁止 MockTelemetryProvider 和 MockSceneStateProvider 自动创建
- Telemetry 无关节速度时使用 intent.requested_joint_velocity 作为保守样本
- post-check 使用 telemetry.tcp_velocity 和 telemetry.acceleration（非固定 0）
- 14 项 Step 0 测试

## 3. 云端规划架构

```
InitialPlanningRequest
  → 请求校验（幂等、冲突检测）
  → 场景充分性检查
  → PlannerAdapter
  → JSON 解析
  → Schema 校验
  → 语义校验
  → 有限修复（最多 2 次）
  → 可信字段补齐
  → 持久化
  → 可选 EdgeGateway dispatch
```

## 4. API 清单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /health | 健康检查 |
| GET | /api/v1/planning/capabilities | 支持技能和控制模式 |
| GET | /api/v1/planning/schemas/task-contract | TaskContract JSON Schema |
| POST | /api/v1/plans | 创建规划 |
| GET | /api/v1/plans/{id} | 查询规划结果 |
| POST | /api/v1/plans/{id}/dispatch | 下发到边缘 |

## 5. PlannerAdapter 实现

- MockPlannerAdapter：确定性固定输出（CI 使用）
- RuleBasedPlannerAdapter：启发式无 LLM 规划器
- OpenAICompatiblePlannerAdapter：OpenAI 兼容 API（超时、重试、熔断）
- CI 只使用 Mock 和 RuleBased

## 6. Schema 和语义校验

- 所有技能必须注册
- 目标对象/区域必须存在于场景中
- 技能顺序约束（LIFT 前必须 GRASP）
- 安全约束不能放宽边缘限制
- 禁止低层控制字段（joint_angles、PWM、motor_commands）
- 禁止安全绕过字段（disable_safety、bypass_safety）

## 7. 修复机制

- 最多 2 次修复
- timeout < duration → timeout = duration * 2
- 缺失 success_conditions → 添加泛用条件
- 云端尝试放宽边缘速度 → 钳制到边缘硬限制
- 禁止字段 → 去除（不可修复）
- 修复失败 → REQUEST_MORE_OBSERVATION 或 PLANNER_FAILED

## 8. 幂等和版本控制

- 相同 request_id + 相同 payload → 返回缓存结果
- 相同 request_id + 不同 payload → REQUEST_ID_CONFLICT
- task_id 服务端生成（task-YYYYMMDD-XXXXXXXX）
- plan_version=1、command_seq=1、issued_at/valid_until 服务端设定

## 9. Prompt 版本追踪

- PromptRegistry 保存 prompt_name、version、hash、system_prompt、user_template
- 每次模型调用记录 planner_name、model_name、prompt_version、temperature、latency_ms、raw_output_hash

## 10. EdgeGateway 链路

- InProcessEdgeGateway 提交已验证契约到 TaskExecutor
- 必须经过 SafetyShield（不可绕过）
- 云端不得把"生成成功"等同于"执行成功"

## 11. 新增和修改文件

新增：
- `src/cloud_edge_robot_arm/cloud/__init__.py`
- `src/cloud_edge_robot_arm/cloud/api/__init__.py`
- `src/cloud_edge_robot_arm/cloud/api/app.py`
- `src/cloud_edge_robot_arm/cloud/api/schemas.py`
- `src/cloud_edge_robot_arm/cloud/planning/__init__.py`
- `src/cloud_edge_robot_arm/cloud/planning/models.py`
- `src/cloud_edge_robot_arm/cloud/planning/adapter.py`
- `src/cloud_edge_robot_arm/cloud/planning/pipeline.py`
- `src/cloud_edge_robot_arm/cloud/planning/prompt_registry.py`
- `src/cloud_edge_robot_arm/cloud/gateway/__init__.py`
- `src/cloud_edge_robot_arm/cloud/gateway/edge_gateway.py`
- `src/cloud_edge_robot_arm/cloud/repositories/__init__.py`
- `src/cloud_edge_robot_arm/cloud/repositories/base.py`
- `src/cloud_edge_robot_arm/cloud/repositories/memory.py`
- `tests/test_phase4_step0_safety_hardening.py`
- `tests/test_phase4_cloud_planning.py`
- `scripts/run_phase4_api_smoke.py`
- `scripts/run_phase4_mock_plan.py`
- `scripts/run_phase4_rule_based_plan.py`
- `scripts/run_phase4_request_more_observation.py`
- `scripts/run_phase4_malformed_output_repair.py`
- `scripts/run_phase4_idempotency.py`
- `scripts/run_phase4_edge_dispatch.py`
- `scripts/verify_phase4.py`
- `docs/phase4_design.md`
- `docs/phase4_acceptance.md`
- `docs/phase4_report.md`
- `docs/cloud_planning_api.md`
- `docs/planner_adapter.md`
- `docs/prompt_registry.md`

修改：
- `src/cloud_edge_robot_arm/config.py` — 添加 RUNTIME_PROFILE
- `src/cloud_edge_robot_arm/edge/runtime/task_executor.py` — runtime_profile 参数和 production 校验
- `src/cloud_edge_robot_arm/edge/safety/safety_skill_executor.py` — 关节速度回退和 post-check 真实遥测
- `src/cloud_edge_robot_arm/edge/runtime/condition_evaluator.py` — 新增条件支持

## 12. 所有测试及真实结果

```text
ruff format --check . → 108 files already formatted
ruff check . → All checks passed!
mypy src/ → Success: no issues found in 65 source files
pytest -q → 168 passed
python scripts/verify_phase3.py → success=true
python scripts/verify_phase3_1.py → success=true
python scripts/verify_phase3_2.py → success=true
python scripts/verify_phase4.py → success=true (7/7)
```

## 13. 尚未解决的问题

- MQTT、周期云端监督、事件触发重规划、局部重规划、技能缓存仍在阶段边界外
- PathCollision / Acceleration 规则为通过检查（需更复杂路径规划/传感器）
- RuleBasedPlannerAdapter 使用简单关键词匹配（NLP 增强待 Phase 5+）
- SQLite cloud repository 未实现（InMemory 已就绪）

## 14. 是否满足进入 Phase 5 的条件

**是**。Phase 4 已完成：
- 168 项测试全部通过（35 项 Phase 4 新增）
- 7 个验收脚本全部通过
- Phase 3/3.1/3.2 无回归
- ruff format/check、mypy 通过
- 模型不可信边界强制
- 幂等性和冲突检测
- 场景充分性检查
- 语义校验和修复机制
- Prompt 版本追踪
- 安全绕过字段硬拒绝
