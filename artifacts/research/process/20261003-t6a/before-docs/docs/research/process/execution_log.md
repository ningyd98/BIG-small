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
