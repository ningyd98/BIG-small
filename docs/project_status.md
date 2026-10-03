# 项目状态

当前权威状态入口为 [current_authoritative_status.md](current_authoritative_status.md)。Phase 11 仿真工作台已接受，Phase 11.1 异步运行时已接受，Phase 11.2 Model Control Center 和 Simulation AI Console 已接受。Phase 12 是最终实验评估、论文证据整理和项目软件/仿真封板阶段。Phase 10 仍保持 `PHASE10_MOVEIT_DRY_RUN_ACCEPTED`、`PHASE10_2B_CONSOLE_ACCEPTED` 和 `PHASE10_LEVEL0_FRAMEWORK_ACCEPTED`；这些状态都没有发送真实硬件执行命令。

## 2026-10-04 分阶段开发状态

当前按 [RGB-D 代理执行计划](superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)完成 T1/T2/T3/T6a/T4/T5：100/1000组静态数据、当前资产6/6类真实 MuJoCo 物理技能、20例离线教师各有独立验收。T3 的本地 Qwen3-VL 4B 经归一化坐标协议和顶抓几何适配，固定场景4/4通过并冻结；独立开发场景及拒答失败见[T3 验收](../artifacts/research/process/20261003-t3-small-model-optimization/acceptance.md)，不代表在线抓取成功。T7 为 `DONE`：同 episode 真实闭环、三值验证、预算和独立数据作业已实现，v2 同 20 assignments 全保留，2 成功/18 失败/0 blocked/0 false completion（正常 2/12，全分配 10%）。[独立复算](../artifacts/research/process/20261003-t7-visual-closed-loop/smoke-20-v2-validation.json)核对 34,353 样本、154 帧、52 动作，valid/accepted 均为 true；只限当前 MuJoCo 直立有色方块的开发 smoke，不是正式 G1。最终454项回归及30个源文件Ruff/mypy通过；T8/T17a 为 `READY`，T6b 保持 `TODO`。最新进度、变更、验证和交接见[过程文档](research/process/README.md)。目前没有新正式研究结果。

下表保留历史能力口径；MuJoCo 环境或旧运行时验收不能替代新 RGB-D 物理抓放验收。历史 full 已运行且 `PHASE12_REJECTED`，当前权威论文运行数为 0。

## 历史能力总表

| 能力域 | 状态 | 验证入口 | 证据 | 运行环境 | 硬件声明 |
| --- | --- | --- | --- | --- | --- |
| 核心运行时 | 已验收 | `scripts/verify_phase6_2.py` | Phase 6.2 报告 | CI 可运行 | 不涉及硬件 |
| PCSC / ETEAC / AUTO | 已验收 | `scripts/verify_phase8_2.py` | Phase 8.2 产物 | CI 可运行 | 不涉及硬件 |
| MuJoCo | 已验收 | `scripts/verify_phase9.py` | `artifacts/phase9` | 本地仿真 | 不涉及硬件 |
| ROS 2 / MoveIt safety | 已验收 | `scripts/verify_phase9_1.py` | `artifacts/phase9_1` | ROS 2 / MoveIt 主机 | 不涉及硬件 |
| Isaac Sim | 已验收 | `scripts/verify_phase9_2.py` | `artifacts/phase9_2` | Isaac 主机 | 不涉及硬件 |
| 跨后端对比 | 已验收 | `scripts/run_phase9_2_cross_backend.py` | `artifacts/phase9_2/cross_backend` | MuJoCo + Isaac | 不涉及硬件 |
| Synthetic Dry-Run | 已验收 | `scripts/verify_phase10_1.py` | `artifacts/phase10/phase10_1` | CI 可运行 | 不涉及硬件 |
| MoveIt Runtime Dry-Run | 已验收 | `scripts/verify_phase10_moveit_dry_run.py` | `artifacts/phase10/moveit_dry_run` | ROS 2 / MoveIt 主机 | 不涉及硬件 |
| 仓库文档治理 | Phase 10.2A-R 后已验收 | `scripts/check_docs.py` | 文档和 CI 检查 | CI 可运行 | 不涉及硬件 |
| Simulation Workbench | Phase 11 已实现 | `scripts/verify_phase11_simulation_workbench.py` | `artifacts/phase11/verification` | CI 可运行，完整 E2E 需浏览器 | 不涉及硬件 |
| Simulation Runtime | Phase 11.1 已实现 | `scripts/verify_phase11_1_simulation_runtime.py --ci` / `--mujoco` / `--full` | `artifacts/phase11_1/verification` 和 `artifacts/phase11_1/runtime` | CI 跑 Mock 异步和恢复；MuJoCo runtime 需仿真环境 | 不涉及硬件 |
| Model Control Center | Phase 11.2 已接受 | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | CI 使用 fake provider/fake Ollama | 不涉及硬件 |
| Simulation AI Console | Phase 11.2 已接受 | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | planner dry-run，`dispatch=false` | 不涉及硬件 |
| Local Model Runtime | 尚未接受 | `scripts/verify_phase11_2_model_control.py --ollama` | 无 accepted evidence | 需要本地 Ollama 和已安装模型 | 不涉及硬件 |
| Phase 12 Final Evaluation | smoke pipeline ready；Phase 12.2 clean validation accepted；Ubuntu full 已运行但 PHASE12_REJECTED | `scripts/verify_phase12.py --smoke|--validation|--full` | `artifacts/phase12`、`artifacts/phase12_1/validation`、`artifacts/phase12_2/validation`、`artifacts/phase12_2_clean/validation`；完整新快照见权威状态 | 旧软件运行与公平物理评测分别验收 | 不涉及硬件 |
| 真实机械臂只读 | framework 已验收，真实设备未开始 | `scripts/verify_phase10_2c_level0.py --fake` | `artifacts/phase10/level0` | fake 模式 CI 可运行，hardware 模式现场专用 | 尚未声明真实只读验证 |
| 真实机械臂运动 | 未开始 | 无 | 无 | 现场设备 | 尚未声明运动验证 |

## 历史状态说明

Phase 9.1 当时的结果是 `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`，原因是 Isaac 和跨后端验证受环境限制。Phase 9.2 后续补齐 Isaac smoke、benchmark 和跨后端验证，形成 `PHASE9_2_ACCEPTED`。

Phase 10.2A 不改变 Phase 9.2 的结论，只补强 dry-run 证据和仓库治理。Phase 10.2B 增加控制台，Phase 10.2C 只完成 Level 0 fake/framework。真实机械臂验证仍是 `NOT_STARTED`。

Phase 11 从真实机械臂接入转向仿真工作台。`scenario_registry()` 和 `ExperimentConfig` 成为前后端实验配置的权威来源，Dashboard 不直接连接 MuJoCo、Isaac、ROS、MoveIt 或真实控制器。

Phase 11.1 解决 Phase 11 的同步运行限制：API 创建任务后立即返回 `QUEUED`，后台 worker 通过 SQLite lease 执行 allowlisted runner，并持久化 run、batch、event、metric、attempt、artifact 和 WebSocket replay sequence。MuJoCo READY 只表示环境可用；MuJoCo runtime accepted 必须通过 M11-01 至 M11-10。

Phase 11.2 增加模型控制中心和仿真 AI 控制台。OpenAI-compatible profile 和 Ollama 管理均通过安全后端 API；API key 不写入 artifact，真实 Ollama runtime 尚未接受，`installed_model_count=0`。

Phase 12 冻结 RQ1-RQ7 和 F01-F20，输出最终实验、统计、图表、表格、论文素材和答辩包。Baseline `7b4c9af` 的 90 条 smoke 记录是 `SYNTHETIC_PIPELINE_SAMPLE`，只能声明 `PHASE12_EXPERIMENT_SUITE_READY` 和 `PHASE12_THESIS_ASSET_PIPELINE_READY`，不能替代 validation 或 full。Phase 12.1 validation 从 actual software runners 产生 evidence；最早的 `artifacts/phase12_2/validation` provenance 为 `worktree_clean=false`，保留为 gap 证据。当前权威 validation evidence 是 `artifacts/phase12_2_clean/validation`：540 条 validation 记录中 466 条 runtime-completed，74 条在 runtime 前因 Isaac、MoveIt 或未配置模型环境阻塞，verifier 输出 `PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED` 和 `PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED`。只有 full profile 能声明 `PHASE12_FINAL_EVALUATION_ACCEPTED` 和 `PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED`。

## 当前阻塞项

- 仓库内没有已授权的真实控制器配置。
- 还没有读取过现场急停或控制器状态。
- Level 0 真实硬件验收没有真实设备证据。
- 没有做过真实机械臂运动测试；MuJoCo 的 T4/T5 物理仿真已单独验收。

## 下一阶段

T7 最终 runtime 竞态修复与454项回归已通过，T8/T17a 已 READY，下一步按依赖实施。现行模型使用 [T7 重探 4/4 后的新冻结目录](../artifacts/research/process/20261003-t7-visual-closed-loop/model-probe/)；历史 T3/T5 source freeze 不冒充现行源码，共享 capture 改动与 T5 12 份旧来源归档见 [preservation 清单](../artifacts/research/process/20261003-t7-visual-closed-loop/t5-prerequisite-preservation.json)。T8 先导、T6b 的 10000 组及教师整合尚未运行；95 runtime/277 prerequisite 测试只是阶段记录，最终合并回归为454 passed。随后开发两个优化方法并进行冻结评测。历史 Phase 12 保留为证据追溯。不得绕过后端直接控制硬件，也不能把仿真结论写成真实机械臂结论；真机相关开发保持冻结。


**T7 最终验收（2026-10-04）：DONE。** 最终 EGL 回归454 passed、1项已有依赖警告，30个源文件Ruff/mypy通过；独立runtime审查无开放P1/P2。真实worker复查1次模型调用、4动作后因抬升保持不足如实FAILED，归档无错误且终态一致。20场景仍为2成功/18失败，未扩大分母；非正式G1。T8/T17a为READY（未实施），T6b为TODO。详见[完整验收](../artifacts/research/process/20261003-t7-visual-closed-loop/acceptance.md)。
