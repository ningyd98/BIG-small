# Shared 工作区

Phase 0/1 共享常量位于 `src/cloud_edge_robot_arm/shared`。

Phase 0/1 冻结路线：

- 异步运行时：Python `asyncio`
- 确定性测试：`MockRobotAdapter`
- 物理仿真目标：MuJoCo
- 云模型调用：禁用
- MQTT：禁用
- 真实机械臂控制：禁用
