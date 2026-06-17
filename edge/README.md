# Edge 工作区

边缘运行时代码位于 `src/cloud_edge_robot_arm/edge`。

Phase 1 包含：

- `RobotAdapter` 统一接口。
- 固定 pick-and-place runner。
- skill registry 和 executor。

Phase 2+ 的边缘自治、状态机、命令订阅、telemetry 发布和安全盾都不放在这个顶层说明目录内。
