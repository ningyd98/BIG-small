# Phase 9 MuJoCo 后端

`MuJoCoPhysicsBackend` 加载 `assets/robots/franka_panda/scene.xml`，创建 `mujoco.MjModel` 和 `mujoco.MjData`，reset 时调用 `mj_forward`，执行时调用 `mj_step`，并从 MuJoCo 状态读取关节状态、TCP site 位姿、接触和传感器帧数据。

Phase 9 验证不再使用旧的 `MuJoCoRobotAdapter` 姿态瞬移路径。`PhysicsRobotAdapter.move_to_pose` 会把任务空间意图映射成关节目标，施加执行器命令，推进物理步，然后返回 `ActionResult`。
