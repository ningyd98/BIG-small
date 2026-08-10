# Sim2Real 实验方案与可视化工作台

## 1. 目标与安全边界

本工作包把 BIG-small 的 Sim2Real 证据链推进为：

```text
per-parameter randomization sample
  -> MuJoCo MjSpec dynamic model
  -> Isaac Lab equivalent event plan
  -> aligned trajectory/sensor traces
  -> Rerun viewer + automatic gap report
```

所有功能仍然是仿真或离线证据处理，不开放真机运动。以下事实必须保持：

```text
real_robot_validation=NOT_STARTED
real_controller_contacted=false
hardware_motion_observed=false
hardware_write_operations=[]
real_motion_dispatch_enabled=false
```

`/simulation/sim2real` 可以提交现有仿真 Batch、上传只读 Sim/Real trace、生成报告和导出实验方案；它没有 servo enable、brake release、trajectory dispatch 或 MoveIt execute 入口。

## 2. 统一 per-parameter randomization contract

`configs/phase9/domain_randomization.yaml` 定义允许随机化的参数。API 对未知名称使用 allowlist 拒绝，避免把任意 model path 暴露为写入口。当前七个参数为：

| 参数 | 单位 | nominal | full envelope | MuJoCo | Isaac Lab 对等项 |
|---|---|---:|---:|---|---|
| object_mass_kg | kg | 0.08 | 0.04–0.28 | MjSpec geom mass | `randomize_rigid_body_mass` |
| friction_coefficient | — | 0.8 | 0.08–1.2 | MjSpec geom friction | `randomize_rigid_body_material` |
| joint_damping_scale | ratio | 1.0 | 0.6–1.6 | MjSpec joint damping | `randomize_actuator_gains` damping scale |
| actuator_gain_scale | ratio | 1.0 | 0.7–1.4 | MjSpec actuator gain/bias | `randomize_actuator_gains` |
| gravity_z_m_s2 | m/s² | -9.81 | [-10.1, -9.5] | MjSpec option gravity | `randomize_physics_scene_gravity` |
| actuator_delay_ms | ms | 0 | 0–120 | deterministic control queue | actuator command buffer |
| camera_depth_noise_m | m | 0.002 | 0–0.035 | deterministic observation noise | observation corruption term |

每个参数可以独立设置：

- `enabled`
- `distribution`: `UNIFORM` / `NORMAL` / `FIXED`
- `range_mode`: `LEVEL_SCALED` / `ABSOLUTE`
- `nominal`、`minimum`、`maximum`
- 正态分布可选 `mean`、`std`

参数 seed 由 `policy_version + run_seed + parameter_name` 派生，因此增加参数或调整 JSON 顺序不会改变其他参数的样本。一次采样后，同一份精确数值同时交给 MuJoCo 与 Isaac Lab 映射，不在各后端二次抽样。

## 3. MuJoCo MjSpec 动态落参

`simulation/mujoco/spec_randomization.py` 在每次 trial 初始化时：

1. 通过 `mujoco.MjSpec.from_file` 读取基准 MJCF；
2. 修改质量、摩擦、关节阻尼、执行器增益/偏置和重力；
3. 编译运行专属 `MjModel`；
4. 记录每个参数的 target、application stage、applied value；
5. 记录编译后 spec XML 的 SHA-256。

执行器延迟与深度噪声属于运行时 command/observation 参数，也记录在同一个 backend mapping evidence 中。项目的 MuJoCo 可选依赖最低版本为 3.3.7，以使用稳定的 MjSpec named accessors。

## 4. Isaac Lab 对等随机化

`simulation/isaac/lab_randomization.py` 把同一份 sample 转换成可序列化 plan。质量、摩擦、阻尼、增益和重力映射为 EventManager terms；执行器延迟和深度噪声分别映射为 `DelayedPDActuatorCfg` 与 `GaussianNoiseCfg`。该模块不要求核心 Python 环境安装 Isaac Lab；`scripts/phase9/isaac_lab_event_bridge.py` 在官方 Isaac Lab 运行时内实例化这些配置。

Isaac standalone JSONL 协议新增 `configure_domain_randomization`，先接收计划再 reset/run，并回传 `parity_values`。当前无 Isaac GPU runtime 的环境只能验证协议、映射和配置契约，不能声称完成真实 Isaac 物理运行。

## 5. Trace schema、时间对齐和 gap gate

`POST /api/v1/simulation/sim2real/gap-report` 接收两条只读 trace：

```json
{
  "simulation": {
    "trace_id": "sim-run-001",
    "source": "SIM",
    "clock": "simulation_time",
    "parameters": {"object_mass_kg": 0.08},
    "samples": [
      {
        "elapsed_s": 0.02,
        "joint_positions_rad": [0.0, 0.1],
        "tcp_position_m": [0.4, 0.0, 0.3],
        "sensor_latency_ms": 8.0,
        "depth_mean_m": 0.6
      },
      {
        "elapsed_s": 0.04,
        "joint_positions_rad": [0.01, 0.11],
        "tcp_position_m": [0.41, 0.0, 0.3],
        "sensor_latency_ms": 8.5,
        "depth_mean_m": 0.61
      }
    ]
  },
  "real": {
    "trace_id": "shadow-001",
    "source": "REAL",
    "clock": "ros_time",
    "parameters": {"object_mass_kg": 0.081},
    "samples": [
      {"elapsed_s": 0.02, "joint_positions_rad": [0.0, 0.1]},
      {"elapsed_s": 0.04, "joint_positions_rad": [0.01, 0.11]}
    ]
  },
  "alignment_tolerance_ms": 25
}
```

报告以 real trace 的 `elapsed_s` 为锚点做最近邻匹配，只接受 tolerance 内的样本。自动计算：

- alignment ratio
- timestamp skew p95
- TCP position RMSE
- joint position RMSE
- sensor latency RMSE
- depth mean RMSE
- 参数绝对差和缺失状态

gate 输出 `PASS` / `WARN` / `FAIL`，并同时返回机器可读 JSON 和 Markdown。默认阈值是工程起点，不是项目验收结论，应由后续 shadow 数据重新标定。

## 6. Rerun trajectory/sensor Viewer

安装 `BIG-small[sim-observability]` 后可生成 `.rrd`：

```bash
python scripts/generate_sim2real_gap_report.py \
  trace_pair.json \
  --output artifacts/sim2real/gap-report \
  --rerun
```

Rerun recording 使用两个 timeline：`aligned_sample` sequence 与 `elapsed` duration。Viewer 同时记录：

- Sim/Real 3D TCP trajectory 与当前 TCP 点；
- joint position 对齐序列；
- timestamp skew；
- sensor latency；
- depth mean；
- gap report summary。

Rerun 只读取 trace 并写 recording，不包含任何硬件控制功能。

## 7. Workbench 与 evidence artifacts

新路由：`/simulation/sim2real`。页面支持七个参数逐项启停、分布与范围编辑，展示两个后端的映射目标，提交 MuJoCo batch，上传 Sim/Real JSON trace，调用 gap report API，并下载 Markdown 报告。

每个仿真 run 的 evidence bundle 新增：

- `randomization_sample.json`
- `backend_parameter_mapping.json`
- `trajectory.json`
- `sensor_stream.json`
- `sim_trace.json`
- `rerun_viewer_manifest.json`
- `sim_real_gap_report.json`

在尚未提供真实 shadow trace 时，最后一个 artifact 明确标记 `WAITING_FOR_REAL_TRACE`，绝不自动填充或伪造真实数据。

## 8. 实验阶段与 promotion gate

- **S0 calibration：** 测量七个参数，确认实测值是否被随机化 envelope 覆盖。
- **S1 MuJoCo robustness：** mode × level × seed × repetition 批量运行，保留精确 sample 和模型落参证据。
- **S2 paired simulation：** 同 scenario/mode/seed/sample 比较 MuJoCo 与 Isaac Lab，分析 simulator-specific bias。
- **S3 real shadow：** 未来在独立 Level 0 只读审批后采集，不发送运动命令。
- **S4 restricted motion：** 未来重新立项；本工作台不具备 dispatch 能力。

进入 S3 前至少要求：安全场景无 unsafe execution、随机化实测覆盖结果完整、跨后端差异有统计报告、时间同步方案固定，并再次确认全部硬件安全事实字段。任何真实运动必须经过独立 hardware gate。

## 9. 当前验收语义

允许声明：

```text
SIM2REAL_RANDOMIZATION_V2_IMPLEMENTED
MUJOCO_MJSPEC_PARAMETERIZATION_IMPLEMENTED
ISAAC_LAB_PARITY_PLAN_IMPLEMENTED
SIM2REAL_OFFLINE_ALIGNMENT_AND_REPORT_IMPLEMENTED
REAL_ROBOT_PROMOTION_LOCKED
```

不得声明：

```text
ISAAC_LAB_RUNTIME_VALIDATED
SIM2REAL_VALIDATED
REAL_ROBOT_VALIDATED
BIGSMALL_REAL_ROBOT_PROJECT_ACCEPTED
```

只有未来真实 shadow/real evidence 完成后，才允许更新权威状态文件。

## 10. 官方参考

- MuJoCo MjSpec model editing: https://mujoco.readthedocs.io/en/stable/programming/modeledit.html
- MuJoCo XML reference: https://mujoco.readthedocs.io/en/stable/XMLreference.html
- Isaac Lab randomization API: https://isaac-sim.github.io/IsaacLab/main/source/api/lab/isaaclab.envs.mdp.html
- Rerun timelines: https://rerun.io/docs/concepts/logging-and-ingestion/timelines
