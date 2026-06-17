# Phase 9 差距分析

Phase 8.2 已经闭合离散实验环路，包括 PCSC tick、真实故障检测时序、安全边界内的 AUTO 切换，以及多崩溃恢复。硬件接入前剩下的主要差距是物理保真度：上层云边栈必须跑在物理状态、接触和传感器时序之上，而不是只靠 `MockRobotAdapter` 改姿态。

Phase 9 用 MuJoCo 核心后端和受保护的 ROS 2 / MoveIt 2 / Isaac Sim 集成代码补这个差距。它不连接真实机械臂、不验证真实急停线路、不做物理相机标定，也不声明硬件性能。这些仍属于 Phase 10。

当前主机结果是 `CORE_READY`。ROS 2 Jazzy、MoveIt 2、Isaac Sim root 和 Vulkan 工具不可用时，Isaac 与 ROS 验证记录为 `BLOCKED_BY_ENV`。
