# Phase 10 设计

Phase 10.2A-R 是仓库和文档治理阶段，不改 SafetyShield、HardwareExecutionGate、PCSC、ETEAC、AUTO、真实机械臂 adapter 行为，也不改已经接受的运行证据。

Phase 10 补的是接入物理机械臂前必须有的安全边界。默认不执行真实机械臂任务，也不声明真实机械臂验证完成。

## 架构边界

控制链仍然是：

```text
TaskContract -> EdgeContractValidator -> SafetyShield -> planner summary
  -> HardwareExecutionGate -> RealRobotAdapter
```

云端服务只产生高层任务契约和监督决策。每一个硬件动作最终执行还是拒绝，由边缘运行时决定。

## 目标状态

普通主机上的 Phase 10 结果按规划证据拆开：

- 只有合成 dry-run 时，结果是 `PHASE10_FRAMEWORK_DRY_RUN_ACCEPTED`。
- ROS 2 / MoveIt 真实规划可用、但不执行时，结果是 `PHASE10_MOVEIT_DRY_RUN_ACCEPTED`。

两者都必须保持 `hardware_motion_observed=false`。它们只说明软件链路和规划链路可用，不说明物理机械臂发生过运动。

## 实现边界

- `cloud_edge_robot_arm.real_robot.config` 负责真实设备配置和执行模式校验。
- `cloud_edge_robot_arm.real_robot.gate` 负责 fail-closed 的运动授权。
- `cloud_edge_robot_arm.real_robot.dry_run` 负责在不发送硬件命令的情况下校验契约，并消费 Synthetic 或 MoveIt dry-run planner。
- `cloud_edge_robot_arm.real_robot.acceptance` 负责持久化最高物理验收级别。
- `cloud_edge_robot_arm.real_robot.adapter` 提供只读 adapter 契约，以及环境阻塞实现。

真实硬件执行只有在现场配置、操作员确认、新鲜遥测、健康控制器、未触发急停、SafetyShield 正常、验收级别足够这些条件同时满足时才可能打开。任一条件缺失，都必须保持关闭。
