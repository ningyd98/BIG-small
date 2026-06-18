# 项目状态

当前权威状态：Phase 11 仿真工作台已实现，目标验收状态为 `PHASE11_SIMULATION_WORKBENCH_ACCEPTED`。Phase 10 仍保持 `PHASE10_MOVEIT_DRY_RUN_ACCEPTED`、`PHASE10_2B_CONSOLE_ACCEPTED` 和 `PHASE10_LEVEL0_FRAMEWORK_ACCEPTED`；这些状态都没有发送真实硬件执行命令。

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
| 真实机械臂只读 | framework 已验收，真实设备未开始 | `scripts/verify_phase10_2c_level0.py --fake` | `artifacts/phase10/level0` | fake 模式 CI 可运行，hardware 模式现场专用 | 尚未声明真实只读验证 |
| 真实机械臂运动 | 未开始 | 无 | 无 | 现场设备 | 尚未声明运动验证 |

## 历史状态说明

Phase 9.1 当时的结果是 `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`，原因是 Isaac 和跨后端验证受环境限制。Phase 9.2 后续补齐 Isaac smoke、benchmark 和跨后端验证，形成 `PHASE9_2_ACCEPTED`。

Phase 10.2A 不改变 Phase 9.2 的结论，只补强 dry-run 证据和仓库治理。Phase 10.2B 增加控制台，Phase 10.2C 只完成 Level 0 fake/framework。真实机械臂验证仍是 `NOT_STARTED`。

Phase 11 从真实机械臂接入转向仿真工作台。`scenario_registry()` 和 `ExperimentConfig` 成为前后端实验配置的权威来源，Dashboard 不直接连接 MuJoCo、Isaac、ROS、MoveIt 或真实控制器。

## 当前阻塞项

- 仓库内没有已授权的真实控制器配置。
- 还没有读取过现场急停或控制器状态。
- Level 0 真实硬件验收没有真实设备证据。
- 没有做过任何物理运动测试。

## 下一阶段

Phase 11 是仿真工作台，不是浏览器遥控器。它只能通过后端 API 展示 capability、场景、运行状态、指标、对比和 artifact，不能绕过后端直接控制硬件。真机相关开发在 Phase 11 冻结。
