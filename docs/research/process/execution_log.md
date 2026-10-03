# 执行日志

本日志只记已发生的授权和可核对的执行；最新任务状态见[阶段进度](phase_progress.md)。时间缺少可靠记录时不补造时分秒。

| 日期 | 事件 | 实际状态与证据 |
|---|---|---|
| 2026-10-03 | 用户授权分阶段启动代码实施，并重建全过程文档；首批 P1=T1/T2。本轮不提交、不推送、不启动真实硬件。 | 范围与原因见[决策记录](decisions_and_risks.md)。 |
| 2026-10-03 | 现有工作区预检和基线记录已完成。 | [初始 Git 状态](../../../artifacts/research/process/20261003-phase1/initial-git-status.txt)、[初始 HEAD](../../../artifacts/research/process/20261003-phase1/initial-head.txt)、[来源哈希](../../../artifacts/research/process/20261003-phase1/initial-source-hashes.json)、[环境](../../../artifacts/research/process/20261003-phase1/environment.json)。基线结果见下文。 |
| 2026-10-03 | 创建本过程文档入口及进度、验证、决策、变更、交接文档。 | 文档工作；不构成 T1/T2 软件或真实采集验收。 |

后续逐项追加：任务与状态、实际命令/退出码/关键结果、产物路径及哈希、SOFTWARE/REAL_CAPTURE/REAL_VLM/PHYSICS 层级、失败和阻塞理由、复核人或复核结论。T1 应记录来源审计及 verifier 回归；T2 应记录同状态 RGB/depth/mask、标定误差、session 释放和 MuJoCo 原始采集。若只完成单元测试，真实采集栏保持未验证。

未来运行产物目录（均待生成或待核实）：`artifacts/research/model-probe/`、`artifacts/research/visual-smoke/`、`artifacts/research/pilot-foundation/`、`artifacts/research/protocol-final/`、`artifacts/research/formal/`、`artifacts/research/release/`。实际名称和内容以任务落盘为准。

## P1 已执行记录

- 初始合并基线在受限环境停于 TestClient，人工中断退出 130；有界诊断 75 秒退出 124。主机对照单测退出 0，1 passed / 1 依赖弃用警告。保留 [挂起堆栈](../../../artifacts/research/process/20261003-phase1/runtime-hang-diagnostic.log)与[主机对照](../../../artifacts/research/process/20261003-phase1/runtime-host-diagnostic.log)。
- 主机基线：`MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_phase11_1_simulation_runtime.py tests/test_rgbd_observations.py tests/test_rgbd_planning.py tests/test_rgbd_runtime.py`，退出 0，35 passed / 1 Starlette 弃用警告，41.11 秒；[原始日志](../../../artifacts/research/process/20261003-phase1/baseline-host-tests.log)。
- T1 首轮实现：12 个审计测试通过，含缺失/重复阶段及重复 ID 的初步检查；[根代理单测日志](../../../artifacts/research/process/20261003-phase1/t1-provenance-tests.log)。此轮测试通过没有替代独立审查。
- T1 首轮独立审查：发现重复 ID 后续记录漏报泄露、缺阶段覆盖率分母偏小、空白 hash 被当真实来源三项问题，返回实施者修正；当时未予验收。

- T1 修复轮1完成：三项新增反例先失败，修正后新审计测试 15 passed；主机合并回归 35 passed / 1 依赖弃用警告（35.36秒），ruff/mypy通过；[实施报告](../../../artifacts/research/process/20261003-phase1/task-1-report.md)、[独立复审](../../../artifacts/research/process/20261003-phase1/task-1-review.md)。三项发现全部关闭，T1 DONE，T2已放行进入实施。

## T2 与 P1 合并验证

- T2 新增行为首轮 RED 为 5 failed / 10 passed；新增原始文件保存及时间/来源篡改断言也先确认失败再实现。实施者局部回归 25 passed / 1 依赖弃用警告，详见[实施报告](../../../artifacts/research/process/20261003-phase1/task-2-report.md)。
- 实际采集命令：`MUJOCO_GL=egl .venv/bin/python scripts/verify_rgbd_capture.py`；退出 0。[RGB 图](../../../artifacts/research/process/20261003-phase1/capture/rgb.png)、[观测元数据](../../../artifacts/research/process/20261003-phase1/capture/observation.json)、[测量](../../../artifacts/research/process/20261003-phase1/capture/measurement.json)及[原始输出](../../../artifacts/research/process/20261003-phase1/capture/capture-run.log)已保存。320×240 RGB/depth/geom 分割三 pass 状态 hash 一致；36,300 个有效桌面像素中抽取 100 点，相对独立 z=0 m 桌面最大高度误差 2.728 mm，平均 0.794 mm，门槛 5 mm；退出后 Renderer 已关闭。此项仅验收采集与该平面几何，不代表完整定位 G1 或抓放成功。
- 根代理独立核对了 RGB 图，以及六个原始文件的 SHA-256、76,800 个深度/掩码/实例元素、有限非负米制深度和掩码对应关系，全部相符；[复核记录](../../../artifacts/research/process/20261003-phase1/capture-independent-check.json)。
- 首次阶段合并回归退出 0：**65 passed / 1 warning，39.16 秒**；覆盖新来源审计、RGB-D 观测/会话/规划/运行时/Isaac 传输，以及 Phase9 MuJoCo 载入/步进/关节/夹爪和 Phase11.1 运行时。[合并原始日志](../../../artifacts/research/process/20261003-phase1/phase1-combined-tests.log)。唯一警告仍为已有 Starlette/AnyIO 别名弃用。
- 根代理对 P1 变更范围运行 [Ruff](../../../artifacts/research/process/20261003-phase1/phase1-ruff.log) 和 [mypy](../../../artifacts/research/process/20261003-phase1/phase1-mypy.log)，均退出 0；mypy 明确检查 10 个 source 文件。整个 vision 包的既有 planner 类型问题未在本阶段修复，不能称全仓检查通过。
- 开题报告 Word 与 Markdown 的 SHA-256 与上次最终版本一致；[保留核对](../../../artifacts/research/process/20261003-phase1/proposal-preservation.json)。本轮重建的是开发过程文档。

合并回归命令：

```bash
MUJOCO_GL=egl .venv/bin/python -m pytest -q \
  tests/test_research_provenance.py \
  tests/test_rgbd_observations.py tests/test_rgbd_capture_session.py \
  tests/test_rgbd_planning.py tests/test_rgbd_runtime.py tests/test_rgbd_isaac_transport.py \
  tests/test_phase9_mujoco_load.py tests/test_phase9_mujoco_physics_step.py \
  tests/test_phase9_joint_control.py tests/test_phase9_gripper_contact.py \
  tests/test_phase11_1_simulation_runtime.py
```

## 阶段关闭

T2 独立审查结论为 ready，未发现 Critical、Important 或实质 Minor；审查者单独重算 6 份产物摘要、观测 checksum、裁剪几何、历史 JSON 往返和 100 点平面误差，未重复 GPU/整套回归。详见[审查报告](../../../artifacts/research/process/20261003-phase1/task-2-review.md)。T1 首轮三项问题均已修复并复审关闭；P1 的 T1/T2 标为 DONE。下一就绪队列为 T6a、T3、T4，均尚未开始。

[本轮实施补丁](../../../artifacts/research/process/20261003-phase1/implementation.patch)相对任务前镜像生成，[源码摘要](../../../artifacts/research/process/20261003-phase1/source-manifest.json)仅覆盖本阶段代码、测试和明确依赖，不冒称整个工作区为干净提交。[机器可读验收报告](../../../artifacts/research/process/20261003-phase1/phase1-report.json)记录完成项、证据范围和下一入口。

## 最终源码一致性补验

最后比对源码摘要时发现观测、相机及两份测试有并发变化；原实施者确认冻结后未写入，编写来源未确认。本轮保留这些变化，不覆盖或归因给原实施者。新增边界包括：SensorFrame 缺实际采集时刻拒绝、在图像编码前检查尺寸和载荷、采集开始时计时、跨 pass 检查相机位置/旋转/FOV。见[并发差异记录](../../../artifacts/research/process/20261003-phase1/post-freeze-changes.patch)。

独立审查已补查四文件并确认无实质问题。根代理重新执行同范围合并回归、实际采集、Ruff 和 mypy，全部退出 0，当前合并结果为 **83 passed / 1 warning，53.55 秒**。[当前回归日志](../../../artifacts/research/process/20261003-phase1/phase1-current-tests.log)、[全部命令及源码稳定性记录](../../../artifacts/research/process/20261003-phase1/current-verification-commands.json)确认运行前后源码完全一致。旧 65 项结果保留为第一次运行记录，最终验收采用本次 83 项结果。

当前代码的原始采集保存在[新测量](../../../artifacts/research/process/20261003-phase1/capture-current/measurement.json)同目录，最大平面高度误差仍为 2.728 mm；[独立文件复核](../../../artifacts/research/process/20261003-phase1/capture-current-independent-check.json)确认摘要、数据尺寸和掩码一致，RGB 与已查看的首轮图相同。机器报告、源码摘要、补丁和交接数字已同步当前版本。

### 最后一次相机参数增量复验

相机深度转换涉及的 znear/zfar/extent 三个参数也纳入跨 pass 变化拒绝；相关并发差异已保留并经同一审查者局部复核。最终整组合并回归 **88 passed / 1 warning，50.67 秒**，重新实际采集、Ruff、mypy 均退出 0；[最终命令及源码稳定性](../../../artifacts/research/process/20261003-phase1/final-verification-commands.json)、[最终测试日志](../../../artifacts/research/process/20261003-phase1/phase1-final-tests.log)、[最终采集测量](../../../artifacts/research/process/20261003-phase1/capture-final/measurement.json)和[文件复核](../../../artifacts/research/process/20261003-phase1/capture-final-independent-check.json)均已保存。当前报告与交接采用这次结果；先前65项、83项记录保留为过程历史。所有本阶段源码及测试另存持久前/后快照，见source-manifest.json。

七份过程文档的链接及内容模式检查通过，没有新增全仓文档错误。全仓仍有29处待实现脚本引用和1处历史报告内容模式提示；详见[文档检查摘要](../../../artifacts/research/process/20261003-phase1/docs-check-summary.json)，未将全仓检查声明为通过。

## 2026-10-03 T2 增补验收

继续开发时核查并修复采集输入、时效与标定边界，详见[增补验收报告](../../../artifacts/research/process/20261003-phase1/t2-resume/acceptance.json)、[独立复审](../../../artifacts/research/process/20261003-phase1/t2-resume/task-2-rereview.md)和[本轮差异](../../../artifacts/research/process/20261003-phase1/t2-resume/continuation.patch)。本节保留原 P1 关闭记录，单独对应增补后的源码。

- 拒绝未知采集时刻与不符尺寸的 RGB/depth；保留历史时间；相机记录采集开始时刻。跨 pass 复核位姿、视场角及 znear/zfar/extent，检测变化即拒绝。真实渲染覆盖 1280×720，较大缓冲区不被缩小。
- 新反例先失败后修复：首次边界 12 个失败、相机 4 个失败；复审后最大分辨率与深度参数 4 个失败，均已转绿。T2 定向 42 项通过；最终合并 123 项通过/1 条既有 Starlette 弃用警告，41.08 秒。最终命令和日志见[123项结果](../../../artifacts/research/process/20261003-phase1/t2-resume/final-acceptance-tests.log)；测试文件为 observations、capture_session、MuJoCo load/physics_step、asset_registry、research_provenance、rgbd planning/runtime/isaac_transport、Phase11.1 runtime 和 Chinese comment checker。
- [最终实采](../../../artifacts/research/process/20261003-phase1/t2-resume/final-capture/measurement.json)：320×240，100 个平面样点、36,300 个有效桌面像素；最大 2.728 mm、均值 0.794 mm，小于 5 mm。三 pass 状态哈希相同，会话已释放；[六个文件校验和与载荷检查](../../../artifacts/research/process/20261003-phase1/t2-resume/final-capture-integrity.json)通过。
- 定向 Ruff 通过，mypy 7 文件通过。较大回归排除两组耗时较长的 Phase12 运行器文件后为 773 通过/1 资产哈希失败；检查发现既有场景仅新增相机和光源，更新 manifest 到 phase9.reference.v2 及实际 SHA256，该失败已由最终 123 项复测关闭。另补齐既有 visual_planner 中文说明。
- 完整 pytest 曾因处理中复审修复而主动中断（exit 2，164 通过/1 已修复的注释失败）；不声明完整套件通过。两组 Phase12 长测试未完成。文档检查仍有 30 项既有问题、无新增；[对比](../../../artifacts/research/process/20261003-phase1/t2-resume/docs-comparison.json)。
- 未提交或推送，开题报告保持原内容；T6a/T3/T4 就绪，尚未执行。该验收仅为 SOFTWARE 和 REAL_CAPTURE。

## 2026-10-03 执行决策闭环路线修订

用户要求“修改优化当前路线图”。本次修改研究设计、主执行计划、路线图入口及六份过程文档，保持 T1—T18、已完成复选项、G0—G5/B0—B5 与正式样本规则。保留同期 T2 增补验收记录，不把这些代码/测试成果归入路线修订。

- T7 增加共享 backend/episode、动作后新帧、PASS/FAIL/UNKNOWN 条件与基础验证路由；T11 消费同一事件，避免早期任务依赖尚未定义的后续接口。
- T10/T12 增加决策身份、候选/provider、拒答、提交复核及分开的概率语义；规则与校准风险驱动的成本选择先行，Jev/其他判断模型为可选独立对照。
- T13 增加验证后解决事件、持久化预算/无进展终止、候选/真实ACK/启动协调；T8/T15—T17补完整成本与误完成/回退等诊断。模拟云使用本机VLM仍计云请求。
- 验证：`python3 scripts/check_docs.py --json` 退出1，修改前后均为30项既有问题，无新增；针对九份文档的链接、Mermaid围栏、内容模式、空白与冲突标记检查通过。依赖图23个执行单元无环、18个任务编号连续，已完成复选项及目标/基线表保持不变；`git diff --check` 退出0。见[文档检查记录](../../../artifacts/research/process/20261003-roadmap-loop-review/documentation-check.json)。
- 本次只改文档并做文档验证，未运行产品测试、模型、训练或物理实验，未提交/推送。新接口和具名测试仍待实现；T1/T2仍DONE，下一就绪队列仍为T6a/T3/T4。

## 2026-10-03 T6a 实施与100组验收进展

本节保留100组阶段的产品实施记录及前述 P1/T2 各轮验收、Jev 路线文档修订历史。当时 T6a 为 `IN_PROGRESS`；[进展摘要](../../../artifacts/research/process/20261003-t6a/acceptance-progress.json)记录真实100组通过、1000组仍在生成。该阶段尚未声明 T6a 完成或生成10000组；最终结果见下节。

- 已交付共享场景/数据契约、真实场景应用与离线标签、raw扰动证据、episode原子发布、分组/近重复审计、预算/取消/恢复、四个CLI及对应配置。各模块按分工先跑失败反例再实现。软件fixture只用于边界验证，不冒充真实采集或动作示范。
- 跨模块审查发现并关闭：转动中的物体被误判稳定、旋转后的桌面边界计算、缺少/不足三pass证据、深度可视化与原始深度不一致、来源摘要遗漏运行时契约、最终落盘与拒绝日志可能越过预算。见[采集审查](../../../artifacts/research/process/20261003-t6a/capture-review.md)、[存储审查](../../../artifacts/research/process/20261003-t6a/storage-review.md)及[独立最终代码审查](../../../artifacts/research/process/20261003-t6a/final-review.md)。最终代码审查为PASS，无未关闭的范围内实质问题；该结论不替代真实数据运行。
- 数据测试命令：`MUJOCO_GL=egl .venv/bin/python -m pytest -q tests/test_rgbd_dataset_labels.py tests/test_rgbd_dataset_integrity.py tests/test_rgbd_dataset_splits.py tests/test_rgbd_dataset_generation.py tests/test_rgbd_dataset_export.py`。根代理[最终数据测试](../../../artifacts/research/process/20261003-t6a/dataset-acceptance-tests.log)为 **124 passed，103.63秒**；[旧路径回归](../../../artifacts/research/process/20261003-t6a/regression-123.log)为 **123 passed / 1条既有Starlette弃用警告，51.35秒**。不把两次运行混称为一次完整全仓回归。
- [定向Ruff](../../../artifacts/research/process/20261003-t6a/final-ruff.log)通过；[mypy](../../../artifacts/research/process/20261003-t6a/final-mypy.log)覆盖18个source文件通过，仅有既有unused override说明。[冻结源码摘要](../../../artifacts/research/process/20261003-t6a/frozen-source-hashes.json)与对应source-snapshot保存本次版本；不是干净Git提交。
- 实际100组命令：`MUJOCO_GL=egl .venv/bin/python scripts/generate_rgbd_dataset.py --config configs/rgbd/dataset_smoke.yaml --output datasets/rgbd-smoke-20261003`，退出0、状态COMPLETE。独立[validate](../../../artifacts/research/process/20261003-t6a/smoke-validate.json)确认100个独立组，35正例/65负例，train/calibration/selection/test=80/5/5/10，重复数0，无错误或警告。
- [export](../../../artifacts/research/process/20261003-t6a/smoke-export.json)导出80条train样本；[replay](../../../artifacts/research/process/20261003-t6a/smoke-replay.json)完成单样本重建。[CLI审计](../../../artifacts/research/process/20261003-t6a/smoke-cli-audit.json)核对其中55条训练负例、user只有instruction/images、重建时间戳保留且RGB/depth完全一致，`execution_verified=false`。
- [100组资源实测](../../../artifacts/research/process/20261003-t6a/smoke-resources.json)：CLI墙钟56.56秒，按该进程PID采样到的framebuffer显存峰值155 MiB（162,529,280字节）。配置采样间隔0.5秒，实际还受nvidia-smi命令耗时影响，可能漏过瞬时峰值；不将该数写成绝对显存上限。
- 当时根代理继续串行运行真实1000组；本阶段记录不填尚未生成的正负例、分组、耗时或质量结论，最终结果在下节追加。T6b等待T5/T8；T3/T4仍就绪，T5/T7/T8须等待各自全部前置条件。未提交或推送，未调用视觉模型、未启动真实硬件，未改变历史PHASE12拒绝与权威论文运行数0。

## 2026-10-03 T6a 最终验收

[最终验收报告](../../../artifacts/research/process/20261003-t6a/acceptance.json)将 T6a 标为 `DONE`。真实100与1000组均完成 generate/validate/export/replay 四入口；前述124项数据测试、123项旧路径回归、Ruff/mypy及独立审查通过，不声称完整全仓测试通过。

- 1000组数据位于 `datasets/rgbd-validation-20261003`，1000次尝试得到1000个独立组、301正例/699负例，train/calibration/selection/test=800/50/50/100。[独立校验](../../../artifacts/research/process/20261003-t6a/validation-validate.json)确认重复数0、无错误或警告。
- [CLI审计](../../../artifacts/research/process/20261003-t6a/validation-cli-audit.json)确认导出800条train样本，其中562条负例；离线重建保留原采集时刻，RGB/depth字节一致，保留原始证据，`execution_verified=false`。
- [1000组资源实测](../../../artifacts/research/process/20261003-t6a/validation-resources.json)：总计1,158,966,504字节，每组1,158,966.504字节；生成墙钟1331.885秒，CLI墙钟1332.669秒。按进程PID采样的显存观测峰值155 MiB（162,529,280字节）；0.5秒配置间隔加命令耗时可能漏过瞬时峰值，不作为连续峰值或绝对上限。
- 下一就绪任务仅为T3/T4。T6a满足T5/T7/T8的数据前置；T5仍等待T4，T7仍等待T3/T5，T8仍等待T7。T6b保持TODO，10000组与教师整合未运行，等待T5/T8。未提交/推送，未调用VLM、训练模型、验收正式物理任务或启动真实硬件。

## 2026-10-03 T4 控制器复验与 T5 离线教师验收

T4 与 T6a 前置完成后实施 T5。只读逐物理步观察接口把场景、接触、关节及登记的33对自碰撞距离作为不可变快照交给独立评价器；教师只用离线真值形成显式目标，在线技能没有评价结果输入。新增失败反例先复现，再修复正常干扰物-桌面接触误报、沉降前悬空约8mm的抬升基线、非有限自碰撞距离、恢复未绑定评分源码版本和异常时丢失部分逐步证据。原 `datasets/rgbd-teacher-smoke` 20例保留为旧规则诊断，未覆写或伪装为新版验收。

控制器单变量真实复现发现成功运动遗留目标使闭爪阶段 TCP 在同场景漂移79.32mm；成功后持位降至8.45mm。持物载荷下加入一次最多0.03rad的有界执行器目标补偿，实际最大0.01468rad，位置误差10.77→4.66mm；原5mm/5°及速度、加速度、超时门槛保持。T4 v2 正例显式增加0.5s post-lift稳定段，六类真实验收6/6 PASS、4358步；无额外持位的5/6失败轨迹另存。见[控制器因果复验](../../../artifacts/research/process/20261003-t4-physical-skills-v2/README.md)。触桌后自然失去右指末态接触的 PLACE 边界仍按原技能判据记录，不回流物体真值。

新版 `datasets/rgbd-teacher-smoke-v2` 用协议和源码 SHA 指纹独立生成20/20例，结果7 `SUCCESS`、12 `FAILED`、1 `SAFETY_VIOLATION`；固定正例成功、固定无接触负例失败，只有7例 `execution_verified=true`。其104个动作帧及56,994个连续物理样本由[只读验证报告](../../../artifacts/research/process/20261003-t5-teacher-validation.json)逐例校验SHA、RGB-D帧链和独立 outcome，`valid=true, accepted=true, errors=[]`。跨T2/T4/T5/T6a合并回归251项通过，Ruff/mypy和独立复审通过；见[T5验收](../../../artifacts/research/process/20261003-t5-teacher-accepted/acceptance.md)。唯一限位事件按当前保守口径保留，不事后调整阈值。T5现为 `DONE`，这批离线开发冒烟不构成正式G1/在线视觉成功率；T3仍 `BLOCKED`，T7真实闭环尚不能验收，T6b仍等待T8预算。未提交/推送，未启动真实硬件。

最终收尾再次运行只读轨迹验证器，20例均通过身份、散列、帧链和物理标签复算，结果仍为7/12/1、`errors=[]`；`tests/test_rgbd_teacher_validation.py` 与 `tests/test_rgbd_teacher_smoke.py` 合计17项通过（3.18秒）。12份入口/过程文档的211个本地链接均存在，`git diff --check` 通过。当前交接、项目状态与路线图已同步完成状态；历史日志保留原时点，不把 T3 阻塞改写为在线闭环成功。


## 2026-10-03 T3 4B模型协议诊断、限定冻结与独立扩展

在保留两候选原0/4失败报告的基础上，诊断确认同一Qwen3-VL 4B采用明确的normalized_1000坐标协议和简短完整的输出约束后可改善定位。本轮未训练、未更换更大模型、未下载新权重，推理仅经localhost直连且忽略代理。实现显式坐标回映、完整技能顺序、受限RGB-D顶抓TCP与批准资产校验；默认抓取配置unconfigured，未配置抓取标定时默认拒绝规划。离线实例检查只在真实输出之后用于评分，不向模型提供真值。

新增失败反例先验证再修复：重复技能、表面点/TCP语义混用、默认配置误启用资产校准、逐次GPU证据不足、有效长度但错误的提示/schema/图像SHA、冻结落盘异常残留PASS。实际请求按指令、观测、冻结快照及schema重建对照；sidecar保存完整角色文本、显式和继承参数以及源码/资产指纹。只读加载验证核对快照、sidecar、报告SHA和当前源码。

实际固定S01探针及只读复核命令：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/probe_rgbd_model.py \
  --config configs/research/model_qwen3vl_4b_normalized.yaml \
  --output artifacts/research/process/20261003-t3-small-model-optimization/probe
.venv/bin/python scripts/probe_rgbd_model.py --verify-frozen \
  --output artifacts/research/process/20261003-t3-small-model-optimization/probe
```

真实320×240双图调用4/4通过，冻结包发布成功，复核返回VERIFIED；见[探针报告](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/probe-report.json)、[模型快照](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/model-frozen.json)与[冻结证据](../../../artifacts/research/process/20261003-t3-small-model-optimization/probe/model-frozen-evidence.json)。225项相关回归和6个source文件mypy通过，独立审查无阻断项；最终检查结果、冷/热时延及显存以[本轮验收](../../../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)为准。T3按预先规定固定S01门槛记DONE，范围仅当前资产高5–10cm竖直方块，证据层级为SOFTWARE/REAL_CAPTURE/REAL_VLM，不包含物理动作执行或正式G1成功率。

独立开发场景扩展与固定探针分开记账。第1批15/16符合判据（12/12有目标定位、3/4目标缺失明确拒绝），第2批14/16（11/12有目标定位、3/4目标缺失明确拒绝），合计29/32：定位23/24、明确拒绝6/8。两条缺失幻觉均被几何校验阻断，首批包含把机器人hand当目标的输出；另有一条有目标误拒绝，三条contract_step_count均为0。32个唯一scene/RGB，无error、missing或duplicate，all_cases_pass=false。未调阈值，不把几何阻断记为模型明确拒绝，也不把误拒绝冒充定位成功；逐例证据见本轮验收。历史0/4报告保留原结论。该次T3验收时T7前置满足，状态READY但尚未实现/验收；T8/T6b保持TODO。本轮未提交/推送，未启动真实硬件，历史PHASE12拒绝及权威论文运行数0不变。


## 2026-10-04 T7 同 episode 在线闭环与收尾

用户授权继续T7，在当前功能分支dirty工作区实施，未commit/push。完成借用capture ownership、同episode动作后新帧、统一三值在线条件、事件与有界路由、SafetyShield前后门禁、模型请求取消/超时控制、三种scope及独立DATASET_GENERATION。HTTP/WS共factory；研究入口以新MODEL_CONTROL_DB空profile消费BIGSMALL_VLM_FROZEN_DIR，不覆盖用户active profile。模型在[T7 model-probe](../../../artifacts/research/process/20261003-t7-visual-closed-loop/model-probe/)真实重探4/4并冻结；旧T3包及历史来源独立保留。

共享vision/capture.py更新会影响旧T3/T5源码绑定，未追溯改写历史验收。[T5 preservation清单](../../../artifacts/research/process/20261003-t7-visual-closed-loop/t5-prerequisite-preservation.json)归档12份历史source，仅共享capture与现行不同，其余11份源码、控制器/教师/物理判据保持不变。

第一版smoke的20例全部失败，34份source snapshot、22,147物理样本、105帧、33动作原样保留；[v1只读复算](../../../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v1-validation.json)为valid=true、accepted=false。基于同一场景诊断修复时序色彩支持、遮挡深度边界、部分动作分母、初始急停和最短deadline，并增加0.6秒实际lift保持与新RGB-D稳定验证；diagnostic-03得到在线与独立物理成功。没有修改T4/T5物理判据来通过本批。

冻结v2后运行同一批20 assignments，命令入口为：

```bash
MUJOCO_GL=egl .venv/bin/python scripts/run_rgbd_smoke.py \
  --scope closed-loop --episodes 20 \
  --config configs/research/visual_smoke.yaml \
  --frozen-dir artifacts/research/process/20261003-t7-visual-closed-loop/model-probe \
  --output artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2
```

[v2摘要](../../../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2/summary.json)保留20/20：2正常成功、18失败、0blocked、0falsecompletion，正常2/12，全分配2/20（10%）。[独立复算](../../../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)覆盖34,353连续物理样本、154帧、52动作，valid=true、accepted=true、errors=[]。这是当前MuJoCo直立有色方块开发smoke，formal_g1=false；保留全部失败和未执行阶段，不能外推正式成功率。

独立数据job真实生成1组，COMPLETE/SUCCEEDED、model_calls=0、task_success=false。阶段运行时95项、前置277项测试通过是当时证据，不是最终总数。最终取消/超时/租约与发布异常修复和454项回归已通过，T7为DONE，T8/T17a为READY，T6b为TODO；根任务已发布acceptance.md。10000组、正式G1、真实硬件均未运行。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../../../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
