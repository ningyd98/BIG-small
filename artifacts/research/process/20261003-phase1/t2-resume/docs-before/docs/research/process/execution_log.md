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
- 阶段合并回归退出 0：**65 passed / 1 warning，39.16 秒**；覆盖新来源审计、RGB-D 观测/会话/规划/运行时/Isaac 传输，以及 Phase9 MuJoCo 载入/步进/关节/夹爪和 Phase11.1 运行时。[合并原始日志](../../../artifacts/research/process/20261003-phase1/phase1-combined-tests.log)。唯一警告仍为已有 Starlette/AnyIO 别名弃用。
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
