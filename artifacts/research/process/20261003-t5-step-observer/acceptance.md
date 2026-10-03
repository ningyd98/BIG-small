# T5 逐物理步只读观察接口验收（2026-10-03）

资产：`assets/robots/franka_panda/scene.xml`，SHA-256 `182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08`。本接口只在显式订阅时为独立评价器构建快照；控制器不接收快照。

## 契约

- `current_physics_observation()` 返回 reset 后的 step 0 或当前步的不可变、脱离 `MjData` 的 `PhysicsStepObservation`。字段含 episode、步数、仿真时钟、对象及目标区域几何、对象线/角速度、TCP、关节与双指的原始位置/速度/限位、当前接触对和急停状态。
- `with backend.observe_physics_steps(callback)` 在每个 `mj_step`、累计步数增加、当前接触更新后同步回调一次；只允许一个观察者。回调重入 `step`、`reset`、驱动或急停会被拒绝。异常、reset 和 shutdown 清除订阅，不跨 episode 留存。
- 未订阅时 `step(steps=N)` 不构建快照，不执行几何距离计算，批量末尾只扫描一次接触；后端不持续积累样本历史。
- `self_collision_distances_m` 是 MuJoCo `mj_geomDistance` 的原始有符号距离，覆盖非邻接 arm chain 21 对及双指各对 base–link5 共 12 对。排除相邻 link、finger–link6、finger–hand、左右双指这些有意接近/重叠的几何。安全距离阈值由独立评价器设定；快照本身不宣称全身无碰撞。

## 红绿与回归

先写 `tests/test_rgbd_step_observer.py`：初始运行 `4 failed, 1 passed`，失败于缺失 hook/step0 接口；增加自碰撞覆盖要求时再次得到 `1 failed`（实际只有 21 对，期望 33 对）。实现后目标测试 `8 passed`。最终命令：

```bash
MUJOCO_GL=egl .venv/bin/python -m pytest -q \
  tests/test_rgbd_step_observer.py tests/test_rgbd_physical_skills.py \
  tests/test_phase9_mujoco_load.py tests/test_phase9_mujoco_physics_step.py \
  tests/test_sim2real_deep_pipeline.py tests/test_rgbd_observations.py \
  tests/test_phase9_joint_control.py tests/test_phase9_emergency_stop.py \
  tests/test_phase9_no_pose_teleport.py tests/test_phase9_sim_time.py \
  tests/test_phase9_ground_truth_isolation.py
# 66 passed in 1.41s

.venv/bin/ruff check src/cloud_edge_robot_arm/simulation/mujoco/backend.py tests/test_rgbd_step_observer.py
# All checks passed!
.venv/bin/mypy src/cloud_edge_robot_arm/simulation/mujoco/backend.py
# Success: no issues found in 1 source file
git diff --check -- src/cloud_edge_robot_arm/simulation/mujoco/backend.py tests/test_rgbd_step_observer.py
# no output, exit 0
```

独立真实 MuJoCo S01、seed 31、完整抓放及释放后 1 秒保持，共观察 4158 个物理步。7 个 T4 动作均返回成功；33 对白名单在该轨迹中的最小距离是 `0.0332746107 m`（`link5`–`hand`），没有因扩展到指端对而出现正常轨迹误报。此数值仅验证该固定轨迹和资产，不代替 T5 对 20 个 episode 的独立安全判定。

另测观察初始角的独立 scratch 状态：`joint1=-0.8 rad` 时 TCP 为 `(0.463310,-0.477042,0.460000) m`；`-0.6 rad` 时为 `(0.548848,-0.375487,0.460000) m`。两者在 64×64 真 RGB-D 中均有 16 个目标实例像素、14 个红色像素，在 320×240 中均为 196/195 个。研究随后决定按机械臂基座工作空间修订 TCP 安全界限，因此本接口没有改动已验收的 `-0.8 rad` 观察初始姿态。

固定教师首例的 PLACE 末端双指接触存在边界风险：对象触桌后右指接触可能间歇消失，单看末态会产生 `GRASP_LOST`。本接口只提供逐步接触证据；该技能语义待 20 批实际频率与独立评价结果再审，不在本次修改。
