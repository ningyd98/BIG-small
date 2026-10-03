# T4 MuJoCo 物理技能验收（2026-10-03）

状态：`T4_PHYSICAL_SKILLS_ACCEPTED`，范围为单个刚性方块、当前 Franka-like MJCF、固定离线位姿 fixture。无真实硬件或模型视觉定位结论；T5 的独立逐步结果评价与 20 episode 教师集成尚待完成。

## 实现与来源边界

- `motion_controller.py` 在独立的 MuJoCo scratch `MjData` 上用阻尼 Jacobian IK 求 6D TCP 目标，只复制机器人关节位置；执行时只下发 `JointCommand`，经位置执行器和 `mj_step` 改变真实机械臂状态。关节目标按模型限位裁剪，命令轨迹限制速度/加速度，仿真时间限制动作步数；超时或不可达清除延迟队列并持位。
- `skill_robot.py` 实现 `RuntimeSkillRobot` 的高层入口。世界位姿运动要求显式 `resolved_target`；在线缺目标直接拒绝，不读取对象真值推断位置。夹持需要左右手指分别与 `object_geom` 产生真实接触；LIFT 要求目标/实际 TCP 垂直位移至少 50 mm，额外 0.5 s 双侧接触保持。空手 MOVE_TO_REGION/PLACE 拒绝。物体抬升和最终落区真值仅在本离线验收脚本读取，不回流到在线控制器。
- backend 的急停拒绝新命令、清排队目标并用执行器主动持位。纯 `ctrl=0` 会在重力下造成二次运动，故不作为此模型的安全停止实现。重置阶段初始化物体与手指位置；执行阶段没有写入 live object qpos 或 TCP 位姿。
- 资产修正前 SHA-256：`6a7938709366801ed6e36c7c504da64a48b7b16bbc02adda2a31417c7ad5b1d1`；修正后：`182fb2bc068ba44de394622f819ae444eb7fbe51df5c5311591a8abb97bf6a08`。每个手指相对中心线的偏置由 45 mm 改为 40 mm，手指执行器 `kp` 由 25 改为 250，接触摩擦设为 1.5；臂执行器 `kp` 由 12 改为 20，并在控制时补偿测得的重力/科氏负载。原手指闭合后与 70 mm 宽方块每侧相隔约 2 mm，不能产生接触；原臂执行器在重力下自由空间 TCP 误差可达约 0.85 m。

## 实际物理证据

执行：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/verify_rgbd_physical_skills.py --output artifacts/research/process/20261003-t4-physical-skills/acceptance.json
MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_physical_skills.py tests/test_phase9_emergency_stop.py tests/test_phase9_ground_truth_isolation.py tests/test_phase9_joint_control.py tests/test_phase9_gripper_contact.py tests/test_phase9_mujoco_load.py tests/test_phase9_mujoco_physics_step.py tests/test_phase9_no_pose_teleport.py tests/test_phase9_sim_time.py tests/test_rgbd_dataset_labels.py tests/test_rgbd_observations.py tests/test_sim2real_deep_pipeline.py
```

原始结果见 [`acceptance.json`](acceptance.json)：MuJoCo 3.3.7，固定场景 `S01_NORMAL_STATIC`、seed 31，6/6 路径通过。正例合计 4158 个真实物理步：抓取时左右各 4 个接触；LIFT 的 0.5 s 保持结束后，方块中心从 z=0.035 m 到 z=0.1204 m，实际抬升 85.39 mm；搬至目标区后松开，额外静置 1 s，最终中心 `(0.21735, 0.25523, 0.03497)` m，落在预定区域内，手指接触为 0。无接触抓取返回 `NO_GRASP_CONTACT`；远不可达目标返回 `UNREACHABLE`；空手 PLACE 无物理步并返回 `NO_GRASP_CONTACT`。

审查发现的运动残留已实际复现并修复：0.5 s 超时后再推进 120 步，无新命令时 TCP 漂移从 53.5 mm 降至 0.239 mm；已完成自由运动后急停再推进 120 步，TCP 漂移从 215 mm 降至 0.971 mm，新运动被拒且不推进。10 mm 的显式 LIFT 目标、0/负数夹爪超时也在测试中先复现错误，后无步拒绝。

相关物理、RGB-D 观测和资产回归最终为 **65 passed**（1.88 s）；新增控制器和技能模块 mypy 通过，T4 文件 Ruff 通过。仓库全量测试不能判为通过：`.venv` 在收集 `test_external_rgbd_robomind.py` 时缺 `h5py`，排除该文件的全量运行又受其他数据依赖缺失及既有中文注释审计失败影响，并在资源协调时中断。该记录不将那些独立失败归为 T4 验收通过。

## 当前适用范围

此资产上，方块可见顶部约 z=0.070 m，TCP 顶抓接触 fixture 为 z=0.045 m（相对可见表面约 −25 mm）。实测表面 +15 mm 的 TCP z=0.085 m 虽产生闭合接触，抬升时物体仍留在桌上；故该偏移只供当前固定资产标定，不能套用到未知 RGB-D 物体。动作返回的 LIFT/PLACE 成功表示 TCP 与本体/接触条件通过，不是独立物理任务成功；对象真实升高、目标区稳定和全 episode 成功由 T5 只读评价器确认。
