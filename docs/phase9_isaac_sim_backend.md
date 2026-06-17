# Phase 9 Isaac Sim 后端

Isaac Sim 集成被设计成独立进程后端边界。核心模块包括 `simulation.isaac.client`、`protocol`、`stage_builder`、`robot_controller`、`sensor_bridge` 和 `fault_bridge`。

当前主机的 Isaac 验证状态是 `BLOCKED_BY_ENV`：`ISAAC_SIM_ROOT` 未设置，`vulkaninfo` 也不可用。因此不声明 Isaac smoke 通过。

兼容主机上的命令：

```bash
ISAAC_SIM_ROOT=/path/to/isaac-sim python scripts/verify_phase9.py
```
