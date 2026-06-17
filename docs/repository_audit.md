# 仓库审计

## 目录结构

仓库现在已经有这些预期工作区：

- `contracts/`：JSON 示例和契约相关资产。
- `shared/`：Phase 0/1 的共享说明。
- `edge/`：顶层说明目录；真实边缘运行时代码在 `src/cloud_edge_robot_arm/edge`。
- `simulation/`：顶层说明目录；真实仿真代码在 `src/cloud_edge_robot_arm/simulation`。
- `scripts/`：验证和验收脚本。
- `tests/`：单元测试和验收测试。
- `docs/`：架构、安全、阶段报告和项目文档。

## 状态矩阵

| 领域 | 状态 | 说明 |
| --- | --- | --- |
| Phase 0 路由冻结 | 完成 | Python/asyncio 兼容包、Mock 测试、MuJoCo 目标，不含云模型或真实机械臂 |
| Pydantic 数据模型 | 完成 | 必需模型已实现 |
| JSON Schema | 完成 | 由 Pydantic 导出，并有测试覆盖 |
| 契约示例 | 完成 | 五个有效示例、五个无效示例 |
| 示例验证器 | 完成 | `scripts/validate_contract_examples.py` |
| 项目配置 | 完成 | `pyproject.toml`、Ruff、MyPy、Pytest、`.env.example` |
| 结构化日志 | 完成 | `build_json_log_record` |
| RobotAdapter 接口 | 完成 | `connect`、`disconnect`、`home`、`move_to_pose`、`open_gripper`、`close_gripper`、`get_state`、`stop`、`emergency_stop` |
| MockRobotAdapter | 完成 | 确定性状态、时长模拟、超时和故障注入 |
| MuJoCo adapter | 部分完成 | 接口兼容，物理执行仍依赖可选依赖和 Phase 8+ 场景 |
| 固定抓放流程 | 完成 | `HOME -> MOVE_ABOVE -> APPROACH -> GRASP -> LIFT -> MOVE_TO_REGION -> PLACE -> RELEASE -> RETREAT -> HOME` |
| 故障注入 | 完成 | 已覆盖所需的 Phase 1 故障 |
| 云端规划 | 阻塞 | 在 Phase 2 就绪前明确不在范围内 |
| MQTT | 阻塞 | 明确不在范围内 |
| 真实机械臂控制 | 阻塞 | 在 Phase 9 之前不在范围内 |
