# 变更记录

本项目按里程碑记录变更，不在这里声明版本号。

## 未发布

- 增加 Phase 12.1：区分 `SYNTHETIC_PIPELINE_SAMPLE` 与 actual software runner evidence，修正 smoke thesis 状态，新增 actual runner adapters、validation source artifact hash 检查和 validation 级状态。
- 增加 Phase 12 Final Evaluation：RQ1-RQ7、F01-F20、smoke/validation/full profile、统计分析、图表、论文表格、论文素材、答辩包和 `scripts/verify_phase12.py`。
- 更新当前权威状态入口，明确 Phase 11.2 Model Control Center 和 Simulation AI Console 已接受，local model runtime 和真实机械臂验证尚未接受。
- 增加 Phase 11.2 Model Control Center：OpenAI-compatible profile、secret 安全、endpoint policy、Ollama 管理、planner dry-run 和 Simulation AI Console。
- 增加 Phase 11.1 Simulation Runtime：SQLite 持久 job repository、状态机、dispatcher、worker lease、cancel、timeout、retry、recovery、持久 WebSocket replay 和 MuJoCo runtime verifier。
- 新增 `scripts/verify_phase11_1_simulation_runtime.py`、runtime DB 工具、Phase 11.1 Playwright 运行时用例和 `artifacts/phase11_1/verification` 输出。
- 增加 Phase 11 Simulation Workbench 后端 API、前端工具集、Batch/Sweep、LiveRun、metrics、comparison、export 和 reproduction。
- 新增 `scripts/verify_phase11_simulation_workbench.py` 以及 Phase 11 backend、frontend 和 Playwright 验收覆盖。
- 明确 Phase 11 期间真实机械臂开发冻结；保持 `real_controller_contacted=false`、`hardware_motion_observed=false` 和 `hardware_write_operations=[]`。

## Phase 11

- 新增 `/api/v1/simulation` FastAPI router。
- 新增 `cloud_edge_robot_arm.simulation_workbench` domain models 和 service。
- 新增 `dashboard/src/simulation/` 前端工具目录。
- 将 `SimulationLabPage` 迁移为 Simulation Workbench 兼容入口。
- 将 comparison 页面迁移到新的 comparison service 和 ECharts 图表。
- 新增 `artifacts/phase11/verification` 验证产物输出。

## Phase 10.2A

- 区分 Synthetic Dry-Run 和 MoveIt Runtime Dry-Run。
- 为 Phase 10 evidence 增加 source tree provenance。
- 加固真实机械臂验收顺序和 operator confirmation。
- 最终状态：`PHASE10_MOVEIT_DRY_RUN_ACCEPTED`。

## Phase 10

- 增加真实机械臂配置模型、执行模式、硬件门、只读 adapter 边界、dry-run evidence、验收级别和安全文档。
- 真实机械臂验证仍为 `NOT_STARTED`。

## Phase 9.2

- 完成 Isaac Sim 6.0 smoke validation、Isaac benchmark 和 MuJoCo-Isaac 成对对比。
- 最终状态：`PHASE9_2_ACCEPTED`。

## Phase 9.1

- 验证 ROS 2 runtime 和 MoveIt 2 safety evidence。
- 加固汇总逻辑和 log-integrity 检查。

## Phase 9

- 增加 MuJoCo 物理仿真核心准备度、域随机化、指标溯源和受保护的 ROS/Isaac 集成。

## Phase 8

- 增加可复现实验平台、PCSC/ETEAC/AUTO 对比、崩溃恢复和敏感性守卫。

## Phase 7

- 增加 Skill Cache、确定性 `RiskEvaluator`、AUTO selector 和模式切换持久化。

## Phase 6

- 增加事件触发自治、本地恢复、本地重规划、CAS guarded plan update 和持久化 event repository。

## Phase 0-5

- 建立核心 contract、`MockRobotAdapter`、边缘 runtime、`SafetyShield`、云端规划和 supervision 基础。
