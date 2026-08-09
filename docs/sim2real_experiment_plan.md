# Sim2Real 实验方案与可视化工作台

## 1. 目标与边界

本工作包用于把 BIG-small 从“多仿真后端验证”进一步推进到可审计的 Sim2Real 实验设计。当前目标不是直接开放真实机械臂运动，而是建立从系统辨识、域随机化、跨后端复核到真机 promotion gate 的完整证据链。

当前必须保持以下事实边界：

```text
real_robot_validation=NOT_STARTED
real_controller_contacted=false
hardware_motion_observed=false
hardware_write_operations=[]
highest_real_hardware_acceptance_level=NONE
```

`dashboard/src/simulation/pages/Sim2RealWorkbenchPage.tsx` 只允许提交现有 MuJoCo 仿真 Batch，并导出 Sim2Real 方案 JSON；真实控制器连接、servo enable、brake release、trajectory、MoveIt execute 均不由该页面提供。

## 2. 核心研究问题

- **S2R-RQ1：** 真实标定参数是否落在当前仿真域随机化包络内？
- **S2R-RQ2：** 随机化强度从 MILD → MODERATE → SEVERE 时，PCSC / ETEAC / AUTO 的鲁棒性退化曲线是否不同？
- **S2R-RQ3：** MuJoCo 与 Isaac Sim 的 paired result 差异是否小于“真实世界不确定性包络”，还是存在 simulator-specific bias？
- **S2R-RQ4：** 在不改变高层 TaskContract 的前提下，真实系统辨识参数回填后，仿真结果能否更接近真实 shadow/replay 数据？
- **S2R-RQ5：** 哪些指标满足 promotion gate，足以进入 Level 0 只读采集；哪些指标必须阻止真机运动？

## 3. 实验阶段

### S0：系统辨识 / calibration

首批只标定当前随机化配置已经具备的四个变量：

| 参数 | 当前 nominal | full envelope | 推荐真实测量 |
|---|---:|---:|---|
| object_mass_kg | 0.08 kg | 0.04–0.28 kg | 电子秤，至少 5 次重复 |
| friction_coefficient | 0.8 | 0.08–1.2 | 斜面/拉力法或等效拟合，多材质重复 |
| actuator_delay_ms | 0 ms | 0–120 ms | command timestamp → state response timestamp，报告 p50/p95 |
| camera_depth_noise_m | 0.002 m | 0–0.035 m | 固定平面多距离采样，报告 RMSE/STD |

这些数值进入界面后只用于计算“测量值是否被随机化包络覆盖”，不被当成真实任务成功率证据。

### S1：域随机化鲁棒性实验

现有 `configs/phase9/domain_randomization.yaml` 和 `DomainRandomizationPolicy` 已经支持 deterministic seed，并由 MuJoCo worker 使用 `domain_randomization.level` 执行，因此本轮不另造 runner。

建议矩阵：

- backend：MuJoCo
- mode：PCSC / ETEAC / AUTO
- level：NONE / MILD / MODERATE / SEVERE
- seed：首轮 5，正式实验建议 20+
- repetitions：首轮 2，正式实验建议 5+
- scenario：至少覆盖 normal、scene change、perception、network、safety、recovery 六类

S1 重点输出：成功率、完成时间、安全介入次数、局部恢复/重规划次数、通信次数、云端调用次数、最终位姿误差（若后端可提供）、失败类型和随机化样本参数。

### S2：跨仿真后端 paired validation

使用同一 scenario / mode / seed / randomization profile 在 MuJoCo 和 Isaac Sim 上做 paired comparison，目的是发现 simulator-specific bias，而不是把 Isaac 当真实世界。

应至少比较：

- task success delta
- completion time delta
- trajectory / endpoint error delta
- safety intervention delta
- collision/contact outcome consistency
- recovery/replanning decision consistency

若 Isaac 环境可升级到 Isaac Lab，可通过 EventManager 将 mass、friction、sensor corruption、external disturbances 等随机化事件按 reset/interval 等模式结构化管理。

### S3：真实机械臂只读 shadow（未来，当前锁定）

只有在单独完成 Level 0 安全审批后，才允许采集：

- joint state
- end-effector pose
- camera/depth timestamp 与观测
- controller state
- network / planner timing

该阶段不得发送运动命令。真实记录与对应仿真 replay 使用相同 task/scenario ID、时间戳语义和 evidence bundle，以支持逐帧/逐事件对齐。

### S4：受限真机运动（未来，当前锁定）

必须重新立项并完成现场安全条件后再做，包括隔离区、急停、速度/力矩限制、双人监督、初始姿态检查、轨迹白名单和 operator confirmation。本 Sim2Real Workbench 不包含该 dispatch 能力。

## 4. Sim2Real gap 计算

当前界面使用可解释的设计指标，而不是伪造一个“Sim2Real 总分”。对每个参数：

```text
normalized_gap = abs(real_measurement - nominal) /
                 max(abs(full_min - nominal), abs(full_max - nominal))
```

选定随机化等级通过现有 scale 生成对应包络：

```text
selected_min = nominal + (full_min - nominal) * level_scale
selected_max = nominal + (full_max - nominal) * level_scale
```

只有真实测量落入 `[selected_min, selected_max]` 时，界面才显示 `COVERED`。这只是“参数覆盖”判定，不代表策略已经完成 Sim2Real transfer。

## 5. Promotion gate 建议

下面阈值是待验证的工程门槛，不是当前项目验收结论：

1. 所有安全类场景保持 0 次 unsafe command execution。
2. NONE → MODERATE 的 task success 退化不超过预设阈值；正式阈值需由 Phase 12/Sim2Real 基线分布校准。
3. 随机化实测参数覆盖率达到 4/4，或明确记录未覆盖参数并扩展 domain envelope。
4. MuJoCo ↔ Isaac paired 差异有统计报告，不能仅比较平均值。
5. S3 前必须重新确认 `real_controller_contacted=false` 与 `hardware_write_operations=[]`，并通过独立 Level 0 只读安全审批。
6. 任何真实运动都必须由独立 hardware gate 触发，不能从浏览器自然语言或 Sim2Real 页面直接 dispatch。

## 6. 可视化工作台能力

新路由：`/simulation/sim2real`

当前页面支持：

- 编辑四项真实标定值；
- NONE / MILD / MODERATE / SEVERE 包络可视化；
- 自动计算每个参数是否被随机化范围覆盖；
- 选择 scenario、PCSC / ETEAC / AUTO、seed 数和重复数；
- 生成并预览实验矩阵；
- 通过现有 `useSubmitSimulationBatch` 提交 MuJoCo 域随机化批次；
- 导出 `sim2real_experiment_plan.json`；
- 显示 MuJoCo / Isaac readiness；
- 显示 S0–S4 promotion gate，并固定锁定真机写阶段。

## 7. 开源工具路线

### MuJoCo：当前主力

继续使用仓库现有 MuJoCo Python backend。MuJoCo 的 MjSpec / model editing API 可在后续将质量、摩擦、传感器和 actuator 参数从“运行时随机化配置”进一步升级为结构化模型编辑。

官方资料：
- https://mujoco.readthedocs.io/en/latest/programming/modeledit.html
- https://mujoco.readthedocs.io/en/latest/python.html

### Isaac Lab：第二仿真后端的域随机化增强

当前 Isaac Sim 已用于跨后端验证。后续若引入 Isaac Lab，优先使用 EventManager，而不是在仓库内重复实现一套随机化框架。

官方资料：
- https://isaac-sim.github.io/IsaacLab/main/_modules/isaaclab/managers/event_manager.html
- https://isaac-sim.github.io/IsaacLab/main/source/tutorials/03_envs/create_manager_base_env.html

### Rerun：可选的时空对齐可视化

真实 shadow/replay 阶段可选引入 Rerun，把相机、深度、关节、末端轨迹、事件和 metrics 按时间轴统一查看。Rerun 仅负责日志/可视化，不负责控制机械臂。

官方资料：
- https://rerun.io/docs/getting-started

当前第一版不新增 Rerun 依赖，避免把可选可视化工具变成 CI 强依赖。

## 8. 下一步验收

本分支第一阶段验收应限定为：

```text
SIM2REAL_WORKBENCH_IMPLEMENTED
SIM2REAL_MUJOCO_BATCH_DISPATCH_AVAILABLE
REAL_ROBOT_PROMOTION_LOCKED
```

不得升级为：

```text
SIM2REAL_VALIDATED
REAL_ROBOT_VALIDATED
BIGSMALL_REAL_ROBOT_PROJECT_ACCEPTED
```

只有未来真实 shadow/real evidence 完成后，才允许更新权威状态文件。
