# T5 脚本教师夹爪修复

2026-10-04，用户授权“修复”。当前源码实跑原20例：7成功提升至19成功，19个正常案例全部成功；无接触负控正确失败，安全违规0。另预先固定40个新随机场景，39成功、1搬运碰撞安全失败。旧数据、旧协议与原7/20验收完整保留。

## 原因与改动

原手指基座位于±40mm，每指几何半宽8mm，闭爪内间隙仍有64mm；教师采样方块宽60–70mm，小方块不能形成双侧夹持，稍宽方块也缺少稳定夹持余量。开爪目标恰好等于40mm硬限位，历史一例短暂超限约0.11mm。

- 将手指基座改为±9mm，闭爪内间隙2mm；滑动关节范围仍为0–40mm。
- backend及数据场景重置共用39mm开爪控制目标，距硬限位保留1mm；对应实际内开口80mm。
- 保持独立物理判据：抬升≥50mm、连续稳定夹持≥0.5s、释放后目标区稳定≥1s，安全事件仍使任务失败。未放宽评分、速度或运动精度。
- 新资产使用 `mujoco_upright_box_v2`。v1资产摘要保持原值；合同、模型冻结和场景汇总绑定各自profile与snapshot，拒绝混用。实际编译模型另检查手指位置、尺寸、旋转、slide轴、启用限位、参考位置、关节数量及TCP位置/旋转，避免XML覆盖绕过文件摘要。

新资产SHA-256：`66a0e27047e530a141259f1d74155d404d71a4d7cae4520f7e0c87140dbe87e2`。

## 当前源码物理验证

| 数据版本 | 已发布/预分配 | 正常案例成功 | 随机案例成功 | 无接触负控 | 安全失败 |
| --- | --- | --- | --- | --- | --- |
| 历史 `rgbd-teacher-smoke-v2` | 20/20 | 7/19 | 6/18 | 正确失败 | 1硬限位 |
| 修复 `rgbd-teacher-smoke-v3` | 20/20 | 19/19 | 18/18 | 正确失败 | 0 |
| 新 `rgbd-teacher-fresh-gripper-v3` | 42/42 | 40/41 | 39/40 | 正确失败 | 1非许可接触 |

原20例的index、case、seed、scene_source与全部scene_parameters逐例一致；仅资产及其派生身份改变。新批配置在运行前固定，为2个固定正负控加40个随机场景，随机seed为20261103–20261142，与原批互斥；未依据新批结果重调参数或剔除样本。

新批失败index=2、seed=20261103：目标与 `dataset_distractor_0_geom` 有9个物理步接触记录，独立评价为 `NONPERMITTED_CONTACT`。即使其抬升、保持、放置满足门槛，仍记 `SAFETY_VIOLATION`；负控失败也完整发布。

修复原批复核102,358个物理样本、172个动作帧；新批226,007个物理样本、370个动作帧。成功轨迹的最低抬升分别89.45/88.07mm、最低保持0.583/0.571s、最低放稳均2.146s。两批[原批独立校验](teacher-validation.json)、[新批独立校验](fresh-validation.json)均 `valid=true, accepted=true, errors=[]`；其中accepted表示数据与正负控验收，不表示每例任务成功。

[逐例审计](audit.json)确认原场景配对、固定分母、新seed互斥、旧manifest未变及当前教师源码指纹一致。历史manifest SHA仍为 `5d02ae37083a6772df4bbaca925baab10257a896ab5d89218331b936ee11dd34`。

## 回归与新标定配置

- 5个真实物理反例先复现3失败/2通过，修复后全部通过；见[修复前日志](regression-before.log)。旧技能测试允许控制器无需载荷补偿即成功，并将保持后的接触要求加强为双指接触。
- [大范围回归](regression-final.log)：661 passed，1项已有Starlette/anyio弃用警告。随后新增参考位置检查的[最终相关补测](calibration-final.log)：87 passed；两批测试有重叠，不能相加为独立测试总数。
- 定向Ruff通过；修改的9个生产/脚本文件[范围内mypy](mypy.log)通过。全包mypy仍有两个预存错误：`datasets/external/robomind.py:11`的h5py缺类型标记、`cloud/planning/pipeline.py:487`的可空字符串赋值，未改无关文件。
- 独立审查最终无开放Critical/Important，限定本次夹爪及标定身份边界；见[审查记录](review.md)。一次补测遗漏 `MUJOCO_GL=egl` 导致渲染启动中止，原日志保留；正确环境下上述87项通过。
- 新配置 [model_qwen3vl_4b_gripper_v2.yaml](../../../../configs/research/model_qwen3vl_4b_gripper_v2.yaml) 沿用已安装的Qwen3-VL 4B Q4_K_M及normalized_1000。真实本地双图探针4/4通过，[新冻结包](model-probe/model-frozen.json)及sidecar已生成，`--verify-frozen`返回VERIFIED。未更换权重或当前active profile。

## 复现命令

下列数据与探针输出目录已存在；重跑需使用新目录，不覆写本轮证据。

```bash
MUJOCO_GL=egl .venv/bin/python scripts/generate_rgbd_trajectories.py \
  --config configs/rgbd/trajectory_gripper_v3.yaml \
  --output datasets/rgbd-teacher-smoke-v3
MUJOCO_GL=egl .venv/bin/python scripts/generate_rgbd_trajectories.py \
  --config artifacts/research/process/20261004-t5-gripper-fix/fresh-config.yaml \
  --output datasets/rgbd-teacher-fresh-gripper-v3
.venv/bin/python scripts/validate_rgbd_trajectories.py \
  --dataset datasets/rgbd-teacher-smoke-v3
.venv/bin/python scripts/validate_rgbd_trajectories.py \
  --dataset datasets/rgbd-teacher-fresh-gripper-v3
.venv/bin/python artifacts/research/process/20261004-t5-gripper-fix/audit.py
.venv/bin/python scripts/probe_rgbd_model.py --verify-frozen \
  --output artifacts/research/process/20261004-t5-gripper-fix/model-probe
```

## 范围

教师仍为 `GROUND_TRUTH_TEACHER` 固定技能脚本，只在离线数据生产使用仿真真值。实测修复范围是当前MuJoCo资产与60–70mm直立刚性方块，未处理通用避障，保留新批1个搬运碰撞失败；开爪80mm，不证明名义感知评估中50–90mm方块均能物理抓取。新几何标定及4/4定位探针也不等于在线任务成功。

本轮没有重测T7/T8在线质量门，不升级正式G1、T6b全量数据或真实硬件结论。历史v1冻结不能用于当前v2资产；原冻结、数据、验收及隔离实验均保留。本次改动在含其他预存工作的大工作区中完成，源码快照按文件摘要归档，未commit/push。
