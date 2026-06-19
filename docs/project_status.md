# 项目状态

当前权威状态入口为 [current_authoritative_status.md](current_authoritative_status.md)。Phase 11 仿真工作台已接受，Phase 11.1 异步运行时已接受，Phase 11.2 Model Control Center 和 Simulation AI Console 已接受。Phase 12 是最终实验评估、论文证据整理和项目软件/仿真封板阶段。Phase 10 仍保持 `PHASE10_MOVEIT_DRY_RUN_ACCEPTED`、`PHASE10_2B_CONSOLE_ACCEPTED` 和 `PHASE10_LEVEL0_FRAMEWORK_ACCEPTED`；这些状态都没有发送真实硬件执行命令。

## 状态总表

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
| Phase 12 Final Evaluation | smoke pipeline ready；Phase 12.2 validation 当前为 runtime evidence gaps | `scripts/verify_phase12.py --smoke|--validation|--full` | `artifacts/phase12`、`artifacts/phase12_1/validation`、`artifacts/phase12_2/validation` | smoke 可 CI；validation 调用 actual software runners；full 需资源 | 不涉及硬件 |
| 真实机械臂只读 | framework 已验收，真实设备未开始 | `scripts/verify_phase10_2c_level0.py --fake` | `artifacts/phase10/level0` | fake 模式 CI 可运行，hardware 模式现场专用 | 尚未声明真实只读验证 |
| 真实机械臂运动 | 未开始 | 无 | 无 | 现场设备 | 尚未声明运动验证 |

## 历史状态说明

Phase 9.1 当时的结果是 `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`，原因是 Isaac 和跨后端验证受环境限制。Phase 9.2 后续补齐 Isaac smoke、benchmark 和跨后端验证，形成 `PHASE9_2_ACCEPTED`。

Phase 10.2A 不改变 Phase 9.2 的结论，只补强 dry-run 证据和仓库治理。Phase 10.2B 增加控制台，Phase 10.2C 只完成 Level 0 fake/framework。真实机械臂验证仍是 `NOT_STARTED`。

Phase 11 从真实机械臂接入转向仿真工作台。`scenario_registry()` 和 `ExperimentConfig` 成为前后端实验配置的权威来源，Dashboard 不直接连接 MuJoCo、Isaac、ROS、MoveIt 或真实控制器。

Phase 11.1 解决 Phase 11 的同步运行限制：API 创建任务后立即返回 `QUEUED`，后台 worker 通过 SQLite lease 执行 allowlisted runner，并持久化 run、batch、event、metric、attempt、artifact 和 WebSocket replay sequence。MuJoCo READY 只表示环境可用；MuJoCo runtime accepted 必须通过 M11-01 至 M11-10。

Phase 11.2 增加模型控制中心和仿真 AI 控制台。OpenAI-compatible profile 和 Ollama 管理均通过安全后端 API；API key 不写入 artifact，真实 Ollama runtime 尚未接受，`installed_model_count=0`。

Phase 12 冻结 RQ1-RQ7 和 F01-F20，输出最终实验、统计、图表、表格、论文素材和答辩包。Baseline `7b4c9af` 的 90 条 smoke 记录是 `SYNTHETIC_PIPELINE_SAMPLE`，只能声明 `PHASE12_EXPERIMENT_SUITE_READY` 和 `PHASE12_THESIS_ASSET_PIPELINE_READY`，不能替代 validation 或 full。Phase 12.1 validation 从 actual software runners 产生 evidence，但 Phase 12.2 重新核验后发现当前 validation provenance 记录 `worktree_clean=false`，因此当前权威状态为 `PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS` 和 `THESIS_PACKAGE_INCOMPLETE`。只有重新生成 clean provenance 的 validation evidence 并通过 verifier 后，才能声明 `PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED` 和 `PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED`；只有 full profile 能声明 `PHASE12_FINAL_EVALUATION_ACCEPTED` 和 `PHASE12_THESIS_EVIDENCE_PACKAGE_ACCEPTED`。

## 当前阻塞项

- 仓库内没有已授权的真实控制器配置。
- 还没有读取过现场急停或控制器状态。
- Level 0 真实硬件验收没有真实设备证据。
- 没有做过任何物理运动测试。

## 下一阶段

Phase 12 是最终软件与仿真评估封板阶段，不是新功能扩展阶段。它不能绕过后端直接控制硬件，也不能把仿真结论写成真实机械臂结论。真机相关开发保持冻结。
