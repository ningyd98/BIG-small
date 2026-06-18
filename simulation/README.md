# Simulation 工作区

仿真代码位于 `src/cloud_edge_robot_arm/simulation`。

Phase 1 包含：

- 确定性 `MockRobotAdapter`。
- 可选 `MuJoCoRobotAdapter` 依赖说明。

安装 MuJoCo 支持：

```bash
# 安装仿真可选依赖，只启用本地仿真后端，不连接真实控制器。
python -m pip install -e ".[sim]"
```
