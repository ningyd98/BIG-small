# 当前交接

**2026-10-05 当前第54步：** 第54步由用户指定Astra制定10项修复任务、48个执行步骤；V3两项软件P2独审关闭，90项CPU及未改六反例通过。唯一完整仿真采集session75370退出0，运行摘要记录4807次保存/0失败及9动作完成（915.765秒）；原件完整性与条件离线decoder session60356仍在运行，尚不报告连续证明。RESET/UTC先验证真实区间宽度能否满足原TTL，再决定至少9独立组；Max配置预检、固定Go工具链与设计独审已形成报告，活动R2代码未验收。主线T12/18、T13并行，native、INITIAL/METHOD/FINAL和正式研究未验收，边缘型号后置。 先读[本步报告](../../../artifacts/research/process/20261004-ced-development/report-step54.md)及[Git交付](git_delivery_20261005.md)。下文旧快照保留。

**当前持续研发入口：** [新总计划](../../superpowers/plans/2026-10-04-cloud-edge-device-research-roadmap.md)、[逐步阶段总结](continuation_20261004.md)、[复现说明](../reproduction.md)和[结果/限制](../results_and_limits.md)。多项云、边、端软件已通过独立审查，当前继续资源冻结、恢复消费者、Max局部修复及真实准入/方法接口。边缘模型型号后置；真实Max凭据、端侧校准/连续证据、完整机会/200故障和合格B0仍缺。不得重用旧模型probe或软件恢复状态解除实际准入。

最新独立运行组合检查为33份冻结hash/AST、125项相关回归及静态PASS，实际方法仍NOT_ADMITTED。4200条BLOCKED软件记录的CLI重建和只读页面导出已验证一致，physical/正式研究NOT_RUN。后续交接需先读局部报告的来源及软件范围；下文旧批次和READY队列保留历史时点，不能覆盖当前阶段总结。

**本轮接续入口：** [2026-10-04阶段总结](continuation_20261004.md)。T17a已DONE；T8修复后120场景已结束，5成功、静态4/40，独立物理/帧/成本复核一致。初次冻结退出3，当前候选未过质量门；机会快照与200恢复证据仍需研发，T8保持IN_PROGRESS。v1只作诊断，不改写原始失败。合并518回归及最后58项补测通过（有重叠），全仓检查未完整通过。用户提出Max／4B／OpenCV候选已评估，尚未切换主线；下一重点是端侧证据保持与在线效果验证。后文READY队列为此前快照。

**截至 2026-10-04：T1/T2/T6a/T3/T4/T5 均为 `DONE`；T7 为 `DONE`，最终454项回归通过；T8/T17a 为 `READY`，T6b 为 `TODO`。** T4 在当前资产与控制器 v2 下完成 6/6 类真实物理验收；T5 的20例离线教师为7成功、12失败、1安全违规，独立逐条重评通过。T3 沿用已安装的 Qwen3-VL 4B，320×240 normalized_1000 双图固定 S01 探针 4/4 通过并冻结，见[本轮验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)。这是协议与 RGB-D 几何优化，未训练、未更换更大模型、未下载新权重；模型仅经 localhost 直连调用且不走代理。T3 限当前资产中高5–10cm的竖直方块及显式 `mujoco_upright_box_v1` 顶抓配置，无物理动作执行，未配置抓取标定时默认拒绝规划；独立开发验证29/32符合各自判据（23/24有目标定位、6/8目标缺失时明确拒绝），`all_cases_pass=false`；两条缺失幻觉及一条有目标误拒绝均为0步契约，失败保留。本阶段无新正式实验结果；历史 `PHASE12_REJECTED`、旧5,580行排除边界与权威论文运行数0保持不变。

当前 T7 已跑完同一批 20 assignments 的 v2：2 正常成功、18 失败、0 blocked、0 false completion；正常 2/12，全分配 2/20（10%）。[独立复算](../../../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)核对 34,353 样本、154 帧、52 动作并返回 valid/accepted=true。v1 的 20 失败、34 份源码快照及 22,147 样本/105 帧/33 动作原样保留；diagnostic-03 已在线与物理双成功。开发 smoke 仅限当前 MuJoCo 直立有色方块，不能称正式 G1。95 runtime 与 277 prerequisite 只是阶段回归记录，最终合并回归为454 passed。

## 先读

- [机器可读阶段报告](../../../artifacts/research/process/20261003-phase1/phase1-report.json)：完成项、88 项回归、2.728 mm 平面误差、审查和剩余边界。
- [执行计划](../../superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)：按依赖和验收推进，不按十二周排代理工作。
- [执行日志](execution_log.md)、[验证矩阵](validation_matrix.md)、[决策风险](decisions_and_risks.md)、[变更记录](change_record.md)：实际命令、原始证据和责任范围。
- [本轮补丁](../../../artifacts/research/process/20261003-phase1/implementation.patch)及[源码摘要](../../../artifacts/research/process/20261003-phase1/source-manifest.json)：区分本批改动与已有未提交原型。
- [T6a最终验收](../../../artifacts/research/process/20261003-t6a/acceptance.json)、[冻结源码摘要](../../../artifacts/research/process/20261003-t6a/frozen-source-hashes.json)及[独立代码审查](../../../artifacts/research/process/20261003-t6a/final-review.md)：真实100/1000组与四入口全部通过，T6a已关闭，T6b未运行。
- [T4 控制器 v2 与真实物理验收](../../../artifacts/research/process/20261003-t4-physical-skills-v2/README.md)：6/6 类通过；保留无额外持位的失败对照。
- [T5 离线教师验收](../../../artifacts/research/process/20261003-t5-teacher-accepted/acceptance.md)及[只读逐条校验](../../../artifacts/research/process/20261003-t5-teacher-validation.json)：20例真实轨迹及全部安全/失败分母。
- [T3 小模型优化验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)、[固定S01探针](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/probe-report.json)、[冻结快照](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/model-frozen.json)和[冻结证据](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/model-frozen-evidence.json)：限定门槛已通过，独立场景的失败分母单列。
- [原Qwen3.5失败探测](../../../artifacts/research/model-probe/summary.md)和[原Qwen3-VL候选失败实测](../../../artifacts/research/process/20261003-t3-vl-candidate/acceptance.md)：历史0/4结果保留，未覆盖或追溯改写。

- [T7 当前证据目录](../../../artifacts/research/process/20261003-t7-visual-closed-loop/)、[v2 复算](../../../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)、[执行源码审查](../../../artifacts/research/process/20261003-t7-visual-closed-loop/execution-final-review.md)及 [T7 使用说明](../../rgbd_visual_closed_loop.md)：最终454项回归、真实worker复查与验收汇总已完成。
- [T7 新冻结模型](../../../artifacts/research/process/20261003-t7-visual-closed-loop/model-probe/model-frozen.json)及 [T5 历史来源归档](../../../artifacts/research/process/20261003-t7-visual-closed-loop/t5-prerequisite-preservation.json)：共享 capture 更新使旧 T3/T5 绑定与现行源码不同；T5 其余 11 份源码和物理判据未变，12 份历史来源已保存，不改旧证据。

## 下一批按依赖执行

T6a 的静态数据与 T5 的离线教师是两个不同资产版本的数据入口：T6a 的旧资产哈希和 T4/T5 的新资产哈希均已记录，后续不得静默混用。

1. **T7 证据复用（DONE）**：取消/超时/租约与发布异常修复、454项回归和整体验收已完成。现行冻结复核使用 `scripts/probe_rgbd_model.py --verify-frozen --output artifacts/research/process/20261003-t7-visual-closed-loop/model-probe`；该目录已真实重探 4/4，旧 T3 包只用于其历史源码快照。保留 v1/v2 全分母与错误动作证据，不以两例成功掩盖剩余失败。
2. **T3 泛化与负例限制**：保留独立场景的显式拒绝与几何阻断两种计数。两批共有32个唯一scene/RGB，无error、missing或duplicate；两条缺失幻觉（首批含指向机器人hand的输出）均被几何校验阻断，一条有目标案例误拒绝，三条契约均为0步。不得把阻断或误拒绝记为定位成功，不调阈值掩盖失败；分批计数见本轮验收。任何协议/源码变化须重新验证冻结包。
3. **T8 先导与独立评价（READY）**：T7前置已满足，先记录成本、安全、失败分母和120场景基础先导；T6b 的全量数据预算再按 T8 结果决定。

共享 backend.py 保持单写者，GPU/渲染任务串行。T3/T4/T5 的限定验收已完成，T7已实施且为DONE；T8/T17a已READY，尚未实施，T6b等待T8预算。后续仍须维持在线输入与离线实例/真值隔离，不得把静态定位或离线教师样本计作在线物理结果。

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

这是 T2 增补完成时的快照；当时 T6a/T3/T4 的依赖与入口不变。此后 T6a/T4/T5 已另行验收，当前状态以上文为准。完整套件未完成，两组耗时较长的 Phase12 历史运行器测试留待后续全量质量门；文档检查仍有既有问题。单个采集会话保持单写者使用。

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

本次100组CLI墙钟为56.56秒，独立显存采样观测峰值155MiB（162,529,280字节）；采样配置间隔0.5秒，命令延迟与离散采样可能漏过瞬时峰值，见[资源记录](../../../artifacts/research/process/20261003-t6a/smoke-resources.json)。124项数据测试、123项旧路径回归、Ruff/mypy（18 source文件）和独立代码审查通过。

1000组位于 `datasets/rgbd-validation-20261003`，1000次尝试得到1000个独立组，301正例/699负例，划分800/50/50/100；独立校验无重复、错误或警告，见[1000组校验](../../../artifacts/research/process/20261003-t6a/validation-validate.json)。800条train导出含562条负例，回放字节与原采集时刻一致、raw证据保留，见[CLI审计](../../../artifacts/research/process/20261003-t6a/validation-cli-audit.json)。总大小1,158,966,504字节，每组1,158,966.504字节；生成器墙钟1331.885秒、CLI墙钟1332.669秒，显存采样观测峰值同为155MiB，测量限制同上。精确值见[最终验收](../../../artifacts/research/process/20261003-t6a/acceptance.json)和[1000组资源](../../../artifacts/research/process/20261003-t6a/validation-resources.json)。

T6b的10000组配置仅已交付，任务为TODO且未运行，仍须等待T8资源预算。T6a 的旧资产静态标签和源图像不作为 T5 动作示范或 G1—G5 的物理结果；T5 已用新资产独立验收20例教师，T3固定S01门槛已通过，T7当前为DONE且已完成开发smoke复算，T8已READY，尚未实施。Jev/provider可选边界保持原路线要求。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../../../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
