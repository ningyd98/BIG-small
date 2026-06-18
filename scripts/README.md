# 脚本索引

脚本按用途和硬件风险分组。已有 verifier 路径保持稳定。

## 核心检查

| 脚本 | 用途 | CI 安全 | Artifact | 硬件 |
| --- | --- | --- | --- | --- |
| `run_checks.sh` | 本地软件检查总入口 | 是 | 部分 verifier 会写 artifact | 否 |
| `check_docs.py` | 文档一致性检查 | 是 | 否 | 否 |
| `verify_project.py` | 按 profile 编排 verifier | 取决于 profile | Summary JSON | 默认不含硬件 profile |
| `validate_contract_examples.py` | 校验 contract 示例 | 是 | 否 | 否 |

## 边缘运行时示例

| 脚本 | 用途 | CI 安全 | Artifact | 硬件 |
| --- | --- | --- | --- | --- |
| `run_fixed_pick_place.py` | Mock 固定抓取放置流程 | 是 | 可选日志 | 否 |
| `run_fault_injection_suite.py` | Mock 故障注入场景 | 是 | 否 | 否 |
| `run_phase2_task.py` | Phase 2 任务运行时示例 | 是 | 可选本地数据库 | 否 |

## 安全验证

Phase 3 脚本使用 Mock/FakeSystem 跑 `SafetyShield` 和集成边缘安全路径。它们可以在 CI 中运行，不会联系硬件。

## 云端规划

Phase 4 脚本通过纯软件路径验证规划 adapter、异常输出修复、幂等和 edge dispatch。

## PCSC / ETEAC / AUTO

Phase 5-8 verifier 脚本验证 supervision、事件触发自治、Skill Cache、`RiskEvaluator`、AUTO 和实验事件证据。这些都是软件侧检查。

## 实验运行器

`run_phase8_experiments.py` 和 Phase 9 benchmark 脚本可能生成 artifact。除非文档化的 runtime profile 明确要求 Isaac 或 ROS 2 / MoveIt，否则它们不接触硬件。

## Phase 11 Simulation Workbench

| 脚本 | 用途 | CI 安全 | 硬件 |
| --- | --- | --- | --- |
| `verify_phase11_simulation_workbench.py --skip-e2e` | 后端、前端和 sample run 轻量检查 | 是 | 否 |
| `verify_phase11_simulation_workbench.py` | 完整 Phase 11 验收，含 Playwright | 本地/CI 浏览器环境 | 否 |

Phase 11 只运行仿真工作台验证。它不会连接真实控制器，也不会运行真实机械臂。真实机械臂模块在 Phase 11 冻结。

## Phase 11.1 Simulation Runtime

| 脚本 | 用途 | CI 安全 | 硬件 |
| --- | --- | --- | --- |
| `verify_phase11_1_simulation_runtime.py --ci` | SQLite repository、异步 worker、恢复、cancel、timeout、retry、前端和 Playwright | 是 | 否 |
| `verify_phase11_1_simulation_runtime.py --mujoco` | 实际运行 MuJoCo M11-01 至 M11-10 | 环境相关 | 否 |
| `verify_phase11_1_simulation_runtime.py --full` | CI 检查 + MuJoCo runtime acceptance | 环境相关 | 否 |
| `init_simulation_runtime_db.py` | 初始化本地 SQLite runtime DB | 是 | 否 |
| `inspect_simulation_runtime_db.py` | 只读查看 runtime DB | 是 | 否 |
| `recover_phase11_runtime.py --dry-run` | 扫描 artifacts 并生成恢复报告 | 是 | 否 |
| `recover_phase11_runtime.py --apply` | 将可恢复 artifacts 写回 DB | 本地维护 | 否 |

普通 CI 不运行 `--mujoco`。如果 MuJoCo 环境不可用，不能用 Mock 结果声明 MuJoCo runtime accepted。

## MuJoCo

Phase 9 MuJoCo 脚本运行本地仿真，不连接真实硬件。

## ROS 2 / MoveIt

| 脚本 | 用途 | CI 安全 | 硬件 |
| --- | --- | --- | --- |
| `phase9/activate_ros2_moveit_env.sh` | 激活 ROS 2 / MoveIt 环境 | 否 | 否 |
| `verify_phase9_1.py` | ROS 2 / MoveIt 验收汇总 | 环境相关 | 否 |
| `verify_phase10_moveit_dry_run.py` | MoveIt Runtime Dry-Run 规划证据 | 环境相关 | 否 |

MoveIt dry-run 不能调用 execute，也不能连接真实 controller。

## Isaac

Phase 9.2 Isaac 脚本需要兼容 Isaac Sim 6.0 的主机。它们生成 runtime artifact，但不生成真实硬件证据。

## 跨后端

`run_phase9_2_cross_backend.py` 按 scenario/seed 对比 MuJoCo 和 Isaac artifact。它会拒绝 Isaac fallback 和静态指标。

## Phase 10 Dry-Run

| 脚本 | 用途 | CI 安全 | 硬件 |
| --- | --- | --- | --- |
| `verify_phase10_0.py` | 配置、门禁和故障路径可执行检查 | 是 | 否 |
| `verify_phase10_1.py` | Synthetic framework dry-run | 是 | 否 |
| `verify_phase10_2a.py --skip-runtime` | CI-safe Phase 10.2A 汇总 | 是 | 否 |
| `verify_phase10_2a.py` | 在存在 MoveIt dry-run 证据时做正式汇总 | 环境相关 | 否 |
| `verify_phase10_2c_level0.py --fake` | Level 0 framework fake 验证 | 是 | 否 |

## 真实硬件验收

`run_phase10_acceptance_level.py` 只有在具备现场配置和操作员流程时才属于真实硬件脚本。CI 或 `all-available` profile 不能自动运行它。它只提供单级验收，不会批量运行 Level 1-6。

`verify_phase10_2c_level0.py --hardware` 是现场硬件命令，禁止加入 GitHub Actions、统一 verifier 或 Phase 11 自动化流程。
