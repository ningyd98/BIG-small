# T4 物理技能 v2 与控制器因果复验

资产为 `assets/robots/franka_panda/scene.xml`，SHA-256 `182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08`。所有位移、接触和物体状态来自 MuJoCo 3.3.7 的真实 `mj_step`；机器人控制继续只下发关节与夹爪执行器目标，不写入 live 物体位姿。`acceptance.json` 与 `causal-probe.json` 均包含本次后端、控制器、技能及各自脚本的源码 SHA-256。

## 成功运动的残余目标

`causal-probe.json` 对随机场景 index 5、seed 20261008 做单变量实验：两次均执行同一 MOVE_ABOVE、APPROACH 和 239 个真实闭爪物理步，诊断基线仅屏蔽 APPROACH 返回时的 `hold_current_joints()`。基线的 joint2、joint3、joint5 待执行目标分别高于实测角度 0.17240、0.03313、0.08168 rad；闭爪期间 TCP 又移动 **79.32 mm**，终点 z 为 −8.50 mm。保留成功后持位时，待执行差值为零，同样闭爪期间 TCP 移动 **8.45 mm**，终点 z 为 +36.78 mm，双指各 4 个接触。此对照没有模拟接触或替换物理引擎，只改变返回时是否锁存当前关节目标。

## 载荷下跟踪

同一固定 S01、seed 31 抓举目标 `(0.45, 0, 0.145) m`，旧版无补偿控制器先前实测超时于 **10.77 mm** 位置误差、1.47° 姿态误差；该历史数值单独标为 `historical_before_compensation`，当前脚本没有重放旧源码。当前控制器在轨迹接近目标、关节速度稳定后，通过执行器目标施加一次每轴最多 **0.03 rad** 的补偿：本次实际最大值 **0.01468 rad**，以 **4.66 mm / 0.612°** 达到原有 5 mm / 5° 标准，随后 0.5 s 对象仍实际抬升 **81.66 mm**、双指各 4 个接触。无载 HOME 对照补偿为 **0 rad**，位置误差 4.62 mm。原速度、加速度、超时边界和成功后持位均保留。`MotionResult.max_load_compensation_rad` 也透传至运动类 `ActionResult.details`，供教师数据逐动作审计；夹爪动作字段为空。

## 六类验收与放置边界

v2 `acceptance.json` 对正向抓放、无接触抓取、不可达目标、超时后持位、急停后持位、空手放置共 **6/6 PASS**。正例经额外 0.5 s post-lift 物理持位后再搬运，共 4358 步；对象抬升 85.41 mm，释放后 1 s 稳定在 `(0.20734, 0.25465, 0.03497) m`，双指接触均为零。这个新增持位是 **v2 正例动作协议的显式变化**；旧 T4 验收和 `acceptance-no-dwell.json` 均保留，不将无额外持位的轨迹称为通过。

无额外持位的对照中，其余 5 类通过，但正例 PLACE 返回 `GRASP_LOST`。逐步只读接触复演显示：PLACE 从 step 3010 开始，物体于 step 3317 首次触桌（两指仍接触），右指首次间歇失接触于 step 3321；末态对象已在目标区、物体与桌面接触，但右指为零。故该轨迹的失败来自触桌后的末态双指判据，而非搬运途中失夹。本轮保留在线 PLACE 判据及独立评价标准，不以最终物体位置真值回流给技能；T5 仍须独立判定完整 episode 成功。

复现命令（仓库根目录）：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/probe_rgbd_motion_causality.py --output artifacts/research/process/20261003-t4-physical-skills-v2/causal-probe.json
MUJOCO_GL=egl .venv/bin/python scripts/verify_rgbd_physical_skills.py --output artifacts/research/process/20261003-t4-physical-skills-v2/acceptance.json
MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_trajectory_dataset.py tests/test_rgbd_teacher_smoke.py tests/test_rgbd_motion_success_hold.py tests/test_rgbd_physical_skills.py tests/test_rgbd_backend_contact_policy.py tests/test_rgbd_step_observer.py tests/test_phase9_illegal_collision.py tests/test_phase9_mujoco_load.py tests/test_phase9_mujoco_physics_step.py tests/test_sim2real_deep_pipeline.py tests/test_rgbd_observations.py
```

本轮合并回归输出 `105 passed`，覆盖 T4 正反路径、T5 固定正反例、observer 和相关 Phase9 兼容性。无额外持位的对照文件是失败原件，复跑正式验收脚本会使用 v2 的显式持位协议。
