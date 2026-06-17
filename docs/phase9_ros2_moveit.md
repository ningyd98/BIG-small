# Phase 9 ROS 2 和 MoveIt 2

Phase 9 在 `simulation.ros2` 中定义了明确的 ROS 名称和 QoS profile。传感器流使用 best-effort 语义；命令和 emergency stop 使用 reliable 语义。

MoveIt 2 仍然只是规划边界。`command_requires_safety_approval("follow_joint_trajectory")` 这条规则用于说明和测试：轨迹在执行前必须经过 BIG-small 的安全审批。

当前主机的 ROS 验证状态是 `BLOCKED_BY_ENV`，因为 `rclpy`、ROS 2 Jazzy、`colcon`、`rosdep` 和 MoveIt 2 都不可用。
