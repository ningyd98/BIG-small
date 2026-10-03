# 当前交接

**截至 2026-10-03：P1 已完成；P2 的 T6a 为 `IN_PROGRESS`，T3/T4 为 `READY`。** T6a 已完成真实 100 组及 generate/validate/export/replay，1000 组仍在生成，尚未满足全部验收。T1 来源审计及 T2 同步 RGB-D 的原验收继续保留；本轮无真实 VLM 验收、研究物理抓放或新正式实验结果。历史 `PHASE12_REJECTED`、旧 5,580 行排除边界与权威论文运行数 0 保持不变。

## 先读

- [机器可读阶段报告](../../../artifacts/research/process/20261003-phase1/phase1-report.json)：完成项、88 项回归、2.728 mm 平面误差、审查和剩余边界。
- [执行计划](../../superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)：按依赖和验收推进，不按十二周排代理工作。
- [执行日志](execution_log.md)、[验证矩阵](validation_matrix.md)、[决策风险](decisions_and_risks.md)、[变更记录](change_record.md)：实际命令、原始证据和责任范围。
- [本轮补丁](../../../artifacts/research/process/20261003-phase1/implementation.patch)及[源码摘要](../../../artifacts/research/process/20261003-phase1/source-manifest.json)：区分本批改动与已有未提交原型。
- [T6a 当前进展](../../../artifacts/research/process/20261003-t6a/acceptance-progress.json)、[冻结源码摘要](../../../artifacts/research/process/20261003-t6a/frozen-source-hashes.json)及[独立代码审查](../../../artifacts/research/process/20261003-t6a/final-review.md)：100 组通过，1000 组生成中，T6a 尚未关闭。

## 下一批按依赖执行

1. **T6a 静态数据工厂**：共享 SceneSpec、随机化、离线标签、原子落盘、组划分和导出已实现；100 组已通过，继续等待正在运行的 1000 组生成，并完成对应 validate/export/replay 和资源核对。该任务不依赖 VLM。全部验收前保持 `IN_PROGRESS`。
2. **T3 真实视觉模型**：双图输入、严格输出、像素映射、模型快照及本机延迟/显存。候选模型尚未验收，不可用记 BLOCKED；同时处理已知 planner.py 类型检查问题。保持在线模型与离线实例/真值隔离。
3. **T4 物理技能**：IK、关节与夹爪驱动、接触抓放；动作必须产生 actuator/step 记录和独立可检查结果。先自由空间，再接触；无成功证据不能用脚本完成代替。

上述任务可以按文件责任并行；共享 backend.py 单写者，GPU/渲染任务串行。T6a 创建的 SceneSpec 由后续 T5 消费；T5 等待 T4/T6a，T7 等待 T3/T5/T6a，T8 等待 T6a/T7。模型受阻时继续独立物理/数据分支。

## 本次路线优化的交接要求

2026-10-03 用户要求修改当前路线图，本轮已将前一轮评估纳入研究设计和执行计划，未执行新的产品任务。继续实施前读取更新后的 T7、T10—T13：

- T7 共享相机/动作 backend 与 episode，定义在线三值条件和基础事件；成功、失败及最终验收均重新观察/路由。旧一次性捕获不能用来实现动作后反馈。
- T10 绑定决策身份/版本/候选hash与有效期；T11复用T7事件，保留B0独立周期；T12先交付规则/成本候选选择与provider契约。
- T13 将最终验证失败接回恢复，验证后解决事件；持久化预算与无进展限制；修复候选、接受ACK、激活、实际启动分别记录。完成动作不可重放。
- T8/T15—T17 记录在线与独立判断分歧、全部远程判断成本和恢复时间线。Jev接入仅为可选对照，当前没有相关实现或实验结果。

G0—G5、B0—B5和正式样本规则不变；该次路线修订时 T1/T2 为 DONE、T6a/T3/T4 为 READY。路线修订与原 P1 实施补丁及后续 T6a 实施分别登记，不能把新文档归入旧验收产物。

## 继续工作边界

当前功能分支保留大量先前未提交改动，本轮未提交、未推送。继续前读取工作区差异与[权威状态](../../current_authoritative_status.md)，禁止覆盖或统一暂存无关文件。TestClient 在受限环境曾挂起，同测主机通过；后续异步/EGL 回归使用本机验证路径并保留真实失败记录。

静态平面采集通过不能替代动态场景几何、G1 定位、物理任务成功或 G2—G5 研究结果。阶段定向 Ruff/mypy 与过程文档检查不代表全仓检查通过；旧文档检查和 planner 类型问题已在决策风险登记。本轮未改开题报告 Word/Markdown，也未启动真实硬件。

## T2 增补后的接续状态（2026-10-03）

继续开发时优先参考[增补验收报告](../../../artifacts/research/process/20261003-phase1/t2-resume/acceptance.json)和[最新源码摘要](../../../artifacts/research/process/20261003-phase1/t2-resume/final-source-hashes.json)：新增边界修复后，T2 定向 42 项、最终合并 123 项通过，独立复审关闭最大分辨率和深度标定两项发现。资产清单已同步现有 RGB-D 场景（phase9.reference.v2）。原 P1 报告保留作先前快照。

T6a/T3/T4 的依赖与入口不变。完整套件未完成，两组耗时较长的 Phase12 历史运行器测试留待后续全量质量门；文档检查仍为 30 项既有问题。单个采集会话保持单写者使用。

## T6a 当前数据入口（2026-10-03）

真实数据位于 `datasets/rgbd-smoke-20261003`：100 个独立组、35 正例/65 负例，分组为 80/5/5/10，质量校验无错误或警告；train 导出 80 条，其中 55 条为负例。单样本重建的原采集时刻、RGB 与深度均已核对一致，`execution_verified=false`。见[校验结果](../../../artifacts/research/process/20261003-t6a/smoke-validate.json)及[CLI 审计](../../../artifacts/research/process/20261003-t6a/smoke-cli-audit.json)。

已实现的调用方式如下；重复生成命令会按原配置/来源核对后请求恢复，不重置尝试预算：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/generate_rgbd_dataset.py \
  --config configs/rgbd/dataset_smoke.yaml --output datasets/rgbd-smoke-20261003
.venv/bin/python scripts/validate_rgbd_dataset.py --dataset datasets/rgbd-smoke-20261003
.venv/bin/python scripts/export_rgbd_training.py \
  --dataset datasets/rgbd-smoke-20261003 --split train \
  --output artifacts/research/process/20261003-t6a/smoke-train.jsonl
.venv/bin/python scripts/replay_rgbd_sample.py \
  --dataset datasets/rgbd-smoke-20261003 --sample-id s-dead1e56ae7a37a367c6694a8bd90d81 \
  --output artifacts/research/process/20261003-t6a/smoke-replay
```

export 仅允许 train/calibration/selection，禁止 test；export/replay 输出必须在原数据集外。生成器总尝试上限为目标组数的 5 倍，取消/磁盘不足保留已发布 episode，配置/源码/资产不兼容不静默续跑。生成退出码 0/2/3/4/130 分别表示完成、输入无效、环境阻塞、运行未完成或质量未通过、用户取消。

本次 100 组 CLI 墙钟为 56.56 秒，独立显存采样观测峰值 155 MiB（162,529,280 字节）；采样配置间隔 0.5 秒，命令延迟与离散采样可能漏过瞬时峰值，见[资源记录](../../../artifacts/research/process/20261003-t6a/smoke-resources.json)。124 项数据测试、123 项旧路径回归、Ruff/mypy（18 source 文件）和独立代码审查通过；这些结果不代替仍在生成的 1000 组验收。

T6b 的 10000 组配置仅已交付，未执行；必须等待 T5/T8。T5 仍等待 T4/T6a，T7 等待 T3/T5/T6a，T8 等待 T7/T6a。静态标签和源图像不作为动作示范或 G1—G5 的物理结果；Jev/provider 可选边界保持原路线要求。
