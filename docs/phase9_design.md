# Phase 9 设计

Phase 9 在既有 `TaskExecutor`、`SafetyShield` 和技能注册表下方增加仿真边界：

```text
TaskContract -> EdgeContractValidator -> SafetyShield -> TaskExecutor -> SkillExecutor -> PhysicsRobotAdapter -> SimulatorBackend -> physics state / contacts / sensors
```

正式后端协议是 `cloud_edge_robot_arm.simulation.backend.SimulatorBackend`。MuJoCo 实现持有 `mujoco.MjModel`、`mujoco.MjData`、执行器目标、仿真时间、接触提取和传感器帧生成。adapter 把 13 个高层技能映射为后端命令，不把 MuJoCo 类型暴露给上层。

Isaac Sim 故意解耦。核心包只提供协议、client、stage、sensor、fault bridge 模块和环境检查；包导入时不导入 Isaac 私有模块。
