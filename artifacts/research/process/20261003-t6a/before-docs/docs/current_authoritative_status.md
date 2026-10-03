# Current Authoritative Status

本文件记录当前实施状态与历史分支基线；论文、答辩和 README 必须同时说明证据版本与验收范围。

## 2026-10-03 RGB-D 分阶段改造

用户已授权按[代理执行计划](superpowers/plans/2026-10-03-rgbd-evidence-research-roadmap.md)启动实施并重建过程文档。当前首批 P1 的 T1 来源审计、T2 同步 RGB-D 采集均已完成并通过独立审查；88 项合并回归通过，真实采集 100 个桌面点的最大高度反投影误差为 2.728 mm（门槛 5 mm）；尚未接受真实 VLM、视觉驱动物理抓放或新正式实验结果。

本轮过程记录统一位于 `docs/research/process/`，启动基线位于 `artifacts/research/process/20261003-phase1/`。历史 Phase 验收保留，以下 Ubuntu 快照不自动升级为新研究方法的验收。软件契约通过、真实图像采集、真实模型调用和物理任务成功分别记账。

## 2026-10-02 Ubuntu 当前快照

项目全部按 Sim2Real 模拟设备路线开展，真实设备阶段禁用。部署与证据索引见 [Ubuntu 交接报告](handover/ubuntu_deployment_report.md)。Core、Dashboard、MuJoCo、ROS2、MoveIt 的本机验收 PASS；Isaac 和 Sim2Real 为 WARN（实际仿真已运行，全参数应用和严格配对未接受）；Phase13 真实模型 BLOCKED；Phase12 full 和 Thesis 为 WARN。

干净 `d571e1b0` full 原始实验保留 5,580 行、5,040 runtime-completed、540 blocked-before-runtime，验收为 PHASE12_REJECTED。360 条 MoveIt 阻塞来自 Phase12 adapter 当前固定禁用，180 条模型阻塞来自未配置真实服务；原摘要的固定环境标签不能用于判断本机是否安装了 Isaac。`da299bd9` 修复了 repetition 丢失，并在独立目录重分析；180 对中 120 对满足旧标量统计规则、60 对含安全停止，full 仍拒绝，verifier-gated authoritative thesis run count 为 0。该统计不满足公平物理配对条件，不形成跨引擎性能结论。

`b35e5390` 的正式工作台验收为 PHASE11_1_SIMULATION_RUNTIME_ACCEPTED / PHASE11_2_SIMULATION_AI_CONSOLE_ACCEPTED，37 E2E 包括实际 MuJoCo；local_model_runtime_accepted=false。原论文历史 466/74 与 35 references / 28 figures 可复现，和新 full 数据分别保存。

## 历史分支基线（保留原验收口径）

下表是此前分支的 verifier 状态，并不将其自动升级为当前 Ubuntu 的全物理 DR、公平配对或真实模型验收。

| Capability | Status | Verifier | Evidence | Hardware Claim |
|---|---|---|---|---|
| PCSC / ETEAC / AUTO | ACCEPTED | `scripts/verify_phase8_2.py` | Phase 8 artifacts | 不涉及真实硬件 |
| MuJoCo simulation | ACCEPTED | `scripts/verify_phase9.py` | `artifacts/phase9` | 不涉及真实硬件 |
| Isaac / cross-backend | `PHASE9_2_ACCEPTED` | `scripts/verify_phase9_2.py` | `artifacts/phase9_2` | 不涉及真实硬件 |
| MoveIt Runtime Dry-Run | `PHASE10_MOVEIT_DRY_RUN_ACCEPTED` | `scripts/verify_phase10_2a.py` | `artifacts/phase10` | `sent_to_hardware=false` |
| Dashboard Console | `PHASE10_2B_CONSOLE_ACCEPTED` | `scripts/verify_phase10_2b.py` | `artifacts/phase10/phase10_2b` | 不涉及真实硬件 |
| Level 0 framework | `PHASE10_LEVEL0_FRAMEWORK_ACCEPTED` | `scripts/verify_phase10_2c_level0.py --fake` | `artifacts/phase10/level0` | fake/framework；真实 Level 0 未开始 |
| Simulation Workbench | `PHASE11_SIMULATION_WORKBENCH_ACCEPTED` | `scripts/verify_phase11_simulation_workbench.py` | `artifacts/phase11/verification` | 不涉及真实硬件 |
| Simulation Runtime | `PHASE11_1_SIMULATION_RUNTIME_ACCEPTED` | `scripts/verify_phase11_1_simulation_runtime.py` | `artifacts/phase11_1/verification` | 不涉及真实硬件 |
| Model Control Center | `PHASE11_2_MODEL_CONTROL_CENTER_ACCEPTED` | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | 不涉及真实硬件 |
| Simulation AI Console | `PHASE11_2_SIMULATION_AI_CONSOLE_ACCEPTED` | `scripts/verify_phase11_2_model_control.py --ci` | `artifacts/phase11_2/verification` | `dispatch=false` 的 planner dry-run |
| Local model runtime | NOT_ACCEPTED | `scripts/verify_phase11_2_model_control.py --ollama` | 无真实本地模型 accepted evidence | installed_model_count=0 |
| Ollama runtime | NOT_ACCEPTED | `scripts/verify_phase11_2_model_control.py --ollama` | `ollama_runtime_status=SKIPPED` | 不涉及真实硬件 |
| Phase 12 smoke suite | `PHASE12_EXPERIMENT_SUITE_READY` + `PHASE12_THESIS_ASSET_PIPELINE_READY` | `scripts/verify_phase12.py --smoke` | `artifacts/phase12` smoke artifacts plus `artifacts/phase12/verification_phase12_1/phase12_smoke_status_correction.json` | 90 rows at `7b4c9af` are `SYNTHETIC_PIPELINE_SAMPLE`; original smoke summary retained and superseded；不涉及真实硬件 |
| Phase 12 validation suite | `PHASE12_VALIDATION_EXPERIMENTS_ACCEPTED` + `PHASE12_VALIDATION_ANALYSIS_PACKAGE_ACCEPTED` | `scripts/verify_phase12.py --validation --artifact-root artifacts/phase12_2_clean/validation` | `artifacts/phase12_2_clean/validation` | clean provenance；540 rows，466 runtime-completed rows，74 rows blocked before runtime；不涉及真实硬件 |
| Phase 12 full final evaluation | NOT_ACCEPTED | `scripts/verify_phase12.py --full` | 无 full accepted artifact | full profile required before final thesis conclusions |
| Real robot validation | NOT_STARTED | 无 | 无 | `highest_real_hardware_acceptance_level=NONE` |

硬件边界：

- `real_controller_contacted=false`
- `hardware_motion_observed=false`
- `hardware_write_operations=[]`
- `real_robot_validation=NOT_STARTED`
- `highest_real_hardware_acceptance_level=NONE`

禁止声明：

- `BIGSMALL_REAL_ROBOT_PROJECT_ACCEPTED`
- 真实机械臂运动实验完成
- Level 1-6 验收完成
