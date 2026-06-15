# Phase 9 MuJoCo Backend

`MuJoCoPhysicsBackend` loads `assets/robots/franka_panda/scene.xml`, creates `mujoco.MjModel` and `mujoco.MjData`, calls `mj_forward` on reset and `mj_step` during execution, and reads joint state, TCP site pose, contacts, and sensor frame data from MuJoCo state.

The previous `MuJoCoRobotAdapter` pose-teleport path is not used for Phase 9 validation. `PhysicsRobotAdapter.move_to_pose` maps task-space intent to joint targets, applies actuator commands, and advances physics steps before returning an `ActionResult`.
