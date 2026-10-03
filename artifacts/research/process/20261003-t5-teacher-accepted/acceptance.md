# T5 离线物理教师：20 例真实轨迹验收

2026-10-03 的冻结批次位于 `datasets/rgbd-teacher-smoke-v2/`。其 `manifest.json` 的 SHA-256 为 `5d02ae37083a6772df4bbaca925baab10257a896ab5d89218331b936ee11dd34`，教师和独立评分协议指纹为 `339a702ff8ceed50993da2f64d57cf38e57ebf0773310eeb62342bf28c58a4ae`。20/20 例均已发布，共 104 个真实动作帧和 56,994 个逐物理步样本，压缩 episode 文件合计 9,089,388 字节。

只读验证器从全部 `episode.json.gz` 重放物理评分，检查 manifest/episode SHA、冻结协议与资产、预定场景身份、RGB-D 帧链、逐步证据连续性和结果标签；结果为 `valid=true, accepted=true, errors=[]`。固定 S01 正控成功，物体实测抬升 0.0946 m、稳定保持 0.7167 s；固定无接触负控失败。真实分母为 7 `SUCCESS`、12 `FAILED`、1 `SAFETY_VIOLATION`，`execution_verified=7/20`。18 个随机场景中有 6 个成功；其余失败均保留，没有挑选成示范成功集。

唯一安全事件是 episode 8 的 `HARD_JOINT_LIMIT`：首次发生于 `APPROACH` 的 physics step 749、仿真时间 3.120833 s，连续 5 个样本被标记。按现行保守口径保留该失败。首个失败动作合计为 9 次 `GRASP:NO_GRASP_CONTACT`（含预注册负控）和 4 次 `LIFT:GRASP_LOST`；独立结果的失败原因是 11 次 `LIFT_BELOW_THRESHOLD`、1 次 `HOLD_TOO_SHORT`、1 次物理安全违规。这表明当前教师对随机场景的可靠性仍有限，7/20 是本批观察值，不能外推为广泛场景成功率。

复现命令：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/generate_rgbd_trajectories.py --config configs/rgbd/trajectory_smoke.yaml --output datasets/rgbd-teacher-smoke-v2
.venv/bin/python scripts/validate_rgbd_trajectories.py --dataset datasets/rgbd-teacher-smoke-v2 --output artifacts/research/process/20261003-t5-teacher-diagnostic/new-batch-validation.json
```

生成命令在已发布目录上只执行来源/散列恢复校验；如需重新生成物理数据，应指定全新输出目录。验收明细见 `artifacts/research/process/20261003-t5-teacher-diagnostic/new-batch-validation.json` 和 `new-batch-episode-audit.json`。原 `datasets/rgbd-teacher-smoke/` 是旧评分协议的首批诊断，仅作失败对照，不属于此次验收，也不能以恢复机制混入新版。

T5 定向回归 17 项通过，完整 Ruff 与 mypy 通过；根代理报告跨本阶段合并回归 251 项通过。
