# BIG-small

BIG-small 是一个面向边缘智能场景的小型机械臂云边协同控制系统，采用“云端智能规划、边缘安全执行”架构。当前版本完成 Phase 0、Phase 1、Phase 1.1 和 Phase 2：仓库初始化、配置、核心数据契约、结构化错误、结构化日志、MockRobotAdapter、固定原子技能注册表、Phase 1.1 安全收口，以及任务契约驱动的边缘执行运行时与可追溯状态机。

## 仓库现状

初始化审查时仓库仅包含：

- `docs/plan.md`：系统总体规划。
- `docs/面向边缘智能场景的小型机械臂云边协同控制系统的设计.docx`：设计文档。

当前新增了可运行 Python 包、测试、配置、脚本和阶段报告，并已同步到 GitHub 仓库 `ningyd98/BIG-small.git`。

## 当前能力

- 统一消息追踪字段：`task_id`、`plan_version`、`command_seq`、`timestamp`。
- Pydantic 数据模型：`TaskContract`、`Telemetry`、`CloudCommand`、`CommandAck`、`EdgeEvent`、`FailureSummary`、`SkillTemplate`。
- JSON Schema 由 Pydantic `model_json_schema()` 导出，并通过契约示例测试验证。
- 边缘契约校验器：支持 schema 校验、过期检查、计划版本检查、命令序号去重和未知技能拒绝。
- Phase 1 Mock 机械臂：支持统一 `RobotAdapter` 接口、动作耗时模拟、超时、故障注入和状态查询。
- 固定技能注册表：13 个原子技能均通过 `SkillName` 枚举注册，不通过字符串动态执行任意函数。
- Phase 1.1 固定流程安全收口：首个失败后短路、记录 `failed_step_id` 和 `skipped_steps`，并触发停机动作。
- Phase 2 边缘运行时：`TaskContract -> EdgeContractValidator -> TaskStateMachine -> TaskRuntimeContext -> SkillRegistry -> SkillExecutor -> RobotAdapter -> Repository -> AuditLog`。
- Repository：提供 `InMemoryRepository` 和 `SQLiteRepository`，持久化任务、状态转换、步骤执行、动作执行、已接受命令和审计事件。
- 防重放：持久化 `plan_version`、`command_seq` 和 payload hash；支持重启后 replay 拒绝和相同序号不同负载冲突检测。
- 崩溃恢复：进程重启后处于 `EXECUTING` 的任务会被标记为 `PAUSED`，并写入 `RUNTIME_RECOVERY_REQUIRED`。
- 结构化 JSON 日志工具和 `.env.example`。

## 目录结构

```text
.
├── configs/                  # 可复现实验和本地运行配置
├── contracts/                # 契约 JSON 示例与 schema 说明
├── data/                     # SQLite 等本地运行数据目录
├── docs/                     # 设计文档、阶段报告和差距分析
├── edge/                     # 边缘模块顶层说明
├── scripts/                  # 一键检查和 Phase 1 demo 脚本
├── shared/                   # Phase 0/1 冻结路线说明
├── simulation/               # 仿真模块顶层说明
├── src/cloud_edge_robot_arm/
│   ├── cloud/                # 云端规划、监督、重规划模块目录
│   ├── contracts/            # 任务契约和消息模型
│   ├── edge/                 # 边缘校验、技能注册表、技能执行器
│   ├── experiments/          # 实验指标、批运行和导出模块目录
│   └── simulation/           # MockRobotAdapter 和后续故障注入
└── tests/                    # Phase 0/1 单元测试
```

## 本地运行

推荐使用一键脚本：

```bash
./scripts/start_phase1_demo.sh
```

该脚本会创建 `.venv`、安装开发依赖、运行测试，并执行一次 Mock pick-and-place 技能序列。

单独运行检查：

```bash
./scripts/run_checks.sh
```

手动命令：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m ruff format --check .
python -m ruff check .
python -m mypy src
python -m pytest -q
```

阶段验收命令：

```bash
ruff check .
mypy .
pytest -q
python scripts/validate_contract_examples.py
python scripts/run_fixed_pick_place.py --adapter mock
python scripts/run_fixed_pick_place.py --adapter mock --repeat 20
python scripts/run_fault_injection_suite.py
python scripts/run_phase2_task.py --repository sqlite
python scripts/run_phase2_failure_case.py --fault GRASP_FAILED
python scripts/run_phase2_replay_test.py
python scripts/run_phase2_restart_recovery_test.py
python scripts/verify_phase2.py
```

## 阶段状态

- Phase 0：已完成，见 `docs/phase0_acceptance.md`。
- Phase 1：已完成，见 `docs/phase1_acceptance.md`。
- Phase 1.1：已完成，见 `docs/phase1_1_report.md`。
- Phase 2：已完成，见 `docs/phase2_design.md`、`docs/phase2_acceptance.md` 和 `docs/phase2_report.md`。
- Phase 3-9：尚未实现，见 `docs/repository_gap_analysis.md`。
