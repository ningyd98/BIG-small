# T6a 交接文档更新草稿

日期：2026-10-03。本文件是待合并草稿，**不是 T6a 验收报告**。已只读核对七份过程文档、`docs/current_authoritative_status.md` 和主执行计划 Task 6；本轮未修改既有文档、源码或任务状态。

当前建议口径为 **T6a `IN_PROGRESS`**：静态数据工厂、四个 CLI 及软件回归已实施，正在处理最终资源预算边界并等待根代理执行冻结源码后的真实 100/1000 组验收。T6b 仍为 `TODO`，10000 组未运行；不得因配置文件存在而记为完成。最终测试数量、资源测量、数据路径、验收结论和下一步状态，待根代理提供实际 `acceptance.json` 后再据实填写。

## 一、拟加入交接的交付说明

T6a 新增不依赖视觉模型的 MuJoCo 静态 RGB-D 数据生产链路：共享 `SceneSpec`、有界场景采样、连续会话场景应用、同步采集与离线实例标签、深度扰动及原始观测保留、按 episode 原子发布、来源与载荷校验、分组划分、负例保留、受限导出和离线重建。

数据采用 `rgbd.dataset.v1`。每条记录保留 RGB、米制 float32 深度、有效掩码、语义实例图、相机/场景/标签和状态证据；深度有扰动时同时保留对应原始 RGB-D 与状态证据。存储边界验证主帧/原始帧均有三个相同且非空的 render-pass 状态 hash，并核对深度可视化与原始深度的像素映射。离线重建保留采集时间、标定和观测 checksum，不更新为新观测。

分组以基础物理场景、资产族及图像内容为依据，seed 不能代替来源去重；同组及重复/近重复关联样本不能跨集合。100 个独立组的目标划分为 train/calibration/selection/test = 80/5/5/10。可见像素或有效深度不足的研究负例仍保留，并显式要求重观测。SFT 用户输入仅含指令与两张图像路径，标签在 assistant 内容；test 集禁止导出。

生成器在持久日志中记录尝试和拒绝原因，跨恢复保持至多 `groups × max_attempt_multiplier` 次尝试，倍数不超过 5。取消、渲染阻塞、预算耗尽和未通过质量检查分别保留真实状态；已发布 episode 不因后续失败被删除。配置、源码、资产或已有输出不一致时拒绝直接续跑。生成必须通过保存后校验才可返回 `COMPLETE`。

这些数据只属于静态感知来源与几何标签，不是动作示范或物理任务成功记录。所有记录保持 `execution_verified=false`。该交付不包含真实 VLM 验收、基础 VLM 微调、视觉驱动物理抓放、Jev provider 实验或正式 G1—G5 结论。

## 二、CLI 使用草稿

以下命令是已实现入口的**用法示例**。示例输出目录不是验收证据链接，正式交接须替换为根代理实际使用并校验通过的目录。命令从仓库根目录运行；渲染串行执行。

### 100 组生成与校验

```bash
MUJOCO_GL=egl .venv/bin/python scripts/generate_rgbd_dataset.py \
  --config configs/rgbd/dataset_smoke.yaml \
  --output datasets/rgbd/example-smoke

.venv/bin/python scripts/validate_rgbd_dataset.py \
  --dataset datasets/rgbd/example-smoke
```

使用相同配置和输出目录再次调用 generate 即请求恢复；源码/资产/配置不兼容会被拒绝。不要通过清空尝试日志或删失败记录重置预算。

### 训练侧导出与单样本离线重建

```bash
.venv/bin/python scripts/export_rgbd_training.py \
  --dataset datasets/rgbd/example-smoke \
  --split train \
  --output artifacts/research/rgbd-exports/example-smoke-train.jsonl

.venv/bin/python scripts/replay_rgbd_sample.py \
  --dataset datasets/rgbd/example-smoke \
  --sample-id '<samples.jsonl 中实际存在的 sample_id>' \
  --output artifacts/research/rgbd-replay/example-smoke
```

`--sample-id` 示例是待替换占位符。export 只允许 `train`、`calibration`、`selection`；export/replay 输出必须位于原数据集目录之外。离线重建写出供检查的图像、深度与元数据，不触发模型、规划分发或机器人动作。

### 1000 组与后续 10000 组边界

仅在 100 组生成、校验、导出及重建通过后继续：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/generate_rgbd_dataset.py \
  --config configs/rgbd/dataset_validation.yaml \
  --output datasets/rgbd/example-validation

.venv/bin/python scripts/validate_rgbd_dataset.py \
  --dataset datasets/rgbd/example-validation
```

1000 组仍需执行相同的 export/replay 检查并保留实际结果。`configs/rgbd/dataset_full.yaml` 对应 10000 组，只作为 T6b 配置交付；T5 轨迹和 T8 预算门槛满足前不运行，也不将其列为当前验收证据。

generate 的状态与退出码：0=`COMPLETE`，2=配置/输入无效，3=`BLOCKED`，4=未完成或运行/质量未通过，130=`CANCELLED`。validate 有效时返回 0，报告无效时返回 4，无法读取/解释输入时返回 2。export/replay 成功为 0，输入或文件错误为 2；所有结果以实际 JSON 与退出码共同判断。

## 三、已存在的过程证据与尚待补齐内容

本草稿确认下列文件已经存在；它们各自覆盖局部实现或审查，**不相加为一次完整最终测试数，也不代替 100/1000 组验收**：

- [生成器实施报告](generator-report.md)：首轮 19 项 CPU 生成/恢复/CLI 测试；后续预算修复有增量测试，最终数待根代理汇总。
- [存储实施报告](storage-report.md)、[存储交叉审查与修复](storage-review.md)：来源、原子发布、raw 对齐和离线读取；审查修复后的 [55 项结果](storage-review-green.log)。
- [分组、质量与导出报告](quality-report.md)：29 项专门回归及来源/质量边界；记录过期 CPU source fixture 的失败与修正通知。
- [采集/标签交叉审查](capture-review.md)：角速度稳定门槛与旋转后的桌面边界两项发现已复核关闭；几何朝向标签留待 T5/T6b 扩展。
- [独立最终审查](final-review.md)：当前仍需核对其最新关闭状态；已列出最终落盘预算及运行时 Pose 契约源码绑定发现，不能以存在报告即称验收通过。
- [旧路径 123 项回归](regression-123.log)：本轮实际重跑记录为 123 passed / 1 条既有警告、51.35 秒。保留 P1/T2 先前各次原始运行数字，不覆盖历史。

待根代理提供并核验：冻结后的最终源码清单/哈希；最终合并测试与定向静态检查；全部审查发现关闭记录；真实 100/1000 组 manifest、quality、splits、attempts、正负例与拒绝计数；generate/validate/export/replay 的实际命令和退出码；每组字节、生成墙钟时长、资源测量方式、GPU 采样间隔与观测峰值。生成器没有 GPU 采样时显示 `NOT_MEASURED`；独立采样结果必须说明是按间隔观测到的峰值，不将其写成无采样误差的绝对峰值。

开发用少量 pilot、CPU fixture、早期无 `state.json` 的数据集均不能替代最终 T6a 数据验收。当前不为尚未生成或未验证的 `acceptance.json`、100/1000 数据目录写可点击证据链接。

## 四、正式合并时逐文件核对范围

| 文件 | 计划更新点 | 必须保留 |
|---|---|---|
| `docs/research/process/README.md` | 在当前阶段概述中增加 T6a 真实状态及最终报告入口；声明静态数据证据层级 | P1 报告入口、SOFTWARE/REAL_CAPTURE/REAL_VLM/PHYSICS 区分、旧 5,580 与历史拒绝边界 |
| `docs/research/process/phase_progress.md` | P2 单独标 T6a 当前/最终状态，T3/T4 仍按实际 READY，T6b 单列未执行 | P1 DONE、T2 增补证据、六阶段依赖；Jev 闭环路线修订段 |
| `docs/research/process/handover.md` | 替换已过时的“数据工厂尚未执行”最新概述，增加实际 CLI/数据入口及剩余依赖 | 原 P1/T2 快照链接、同 episode/三值验证/ACK/启动要求、Jev 可选边界与工作区保留规则 |
| `docs/research/process/execution_log.md` | 追加 T6a 独立一节，按实际失败、修复、冻结、运行、审查与验收记录 | T1、T2、65→83→88、增补 123 各次历史日志；路线闭环修订为单独文档事件 |
| `docs/research/process/validation_matrix.md` | 将 T6a/b 合并行拆开；四个 CLI 改为已实现；填实际数据与最终验收结果 | T6b 10000/教师/预算前置；其余未来任务的 TODO 与可选 provider 行 |
| `docs/research/process/change_record.md` | 新增实际 T6a 文件清单和阶段差异/来源摘要，注明存储、采集和预算修复 | 原 P1/T2 改动、并发差异说明、Jev 文档修订记录；既有脏工作区不归入本次新增交付 |
| `docs/research/process/decisions_and_risks.md` | 更新静态数据泄露/磁盘/恢复风险已验证范围，保留尚未满足的物理和统计风险 | 真实模型未验收、硬件禁用、云边模拟、无弱基线收益主张、可选 Jev 与完整远程成本口径 |
| `docs/current_authoritative_status.md` | 只在 2026-10-03 段新增 T6a 最新证据版本与范围 | Ubuntu/Phase 历史表、`PHASE12_REJECTED`、权威论文运行数 0、硬件状态 |
| 主执行计划 Task 6 / 状态摘要 | 仅根代理授权且证据齐备时勾选已完成 T6a 步骤，追加实际验收说明；T6b 保持未完成 | Task 编号、G/B 编号、正式样本规则和 T7/T10—T13 的 Jev/闭环修订 |

拟登记的产品文件范围已核对存在：`datasets/rgbd/{models,scene_sampler,capture,labels,writer,quality,splitter,generator,exporters}.py` 及包入口、`vision/offline_reader.py`、连续采集会话和 MuJoCo backend 的相关增量、四个脚本、三个 YAML 与五份 dataset 测试。最终“本批新增/修改”仍须对照根代理保存的 T6a before 镜像和源码差异，不能拿相对 Git HEAD 的全部脏工作区当本轮补丁。

## 五、下一步与状态条件

当前只准备草稿，未把 T6a 写为 DONE。根代理完成最终预算修复、独立复核和真实 100/1000 组四入口验收并提供 `acceptance.json` 后，才合并以上文案并填入确定数字和真实证据链接。

T6a 完成只满足后续任务的一个前置条件：T5 还等待 T4，T7 还等待 T3/T5，T8 还等待 T7；不能把这些任务自动升级为 READY。T3/T4 可继续按既定独立分支执行。Jev/其他判断模型仍为后续可选对照，不因数据工厂交付而改变 G0—G5、B0—B5 或正式样本规则。
