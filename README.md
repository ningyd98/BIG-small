# 面向边缘智能场景的小型机械臂云边协同控制系统

本仓库实现“云端智能规划、边缘安全执行”的小型机械臂云边协同控制系统。当前版本完成 Phase 0 和 Phase 1：仓库初始化、配置、核心数据契约、结构化错误、结构化日志、MockRobotAdapter，以及固定原子技能注册表和技能执行器。

## 仓库现状

初始化审查时仓库仅包含：

- `docs/plan.md`：系统总体规划。
- `docs/面向边缘智能场景的小型机械臂云边协同控制系统的设计.docx`：设计文档。

当前新增了可运行 Python 包、测试、配置、脚本和阶段报告。该目录尚不是 Git 仓库，后续如需版本管理可以执行 `git init`。

## 当前能力

- 统一消息追踪字段：`task_id`、`plan_version`、`command_seq`、`timestamp`。
- Pydantic 数据模型：`TaskContract`、`Telemetry`、`CloudCommand`、`CommandAck`、`EdgeEvent`、`FailureSummary`、`SkillTemplate`。
- 边缘契约校验器：支持 schema 校验、过期检查、计划版本检查、命令序号去重和未知技能拒绝。
- Phase 1 Mock 机械臂：支持 home、观测、定位、移动、抓取、搬运、放置、释放、撤退、结果验证和安全停止。
- 固定技能注册表：13 个原子技能均通过 `SkillName` 枚举注册，不通过字符串动态执行任意函数。
- 结构化 JSON 日志工具和 `.env.example`。

## 目录结构

```text
.
├── configs/                  # 可复现实验和本地运行配置
├── data/                     # SQLite 等本地运行数据目录
├── docs/                     # 设计文档、阶段报告和差距分析
├── scripts/                  # 一键检查和 Phase 1 demo 脚本
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

## 阶段状态

- Phase 0：已完成，见 `docs/phase0_report.md`。
- Phase 1：已完成，见 `docs/phase1_report.md`。
- Phase 2-9：尚未实现，见 `docs/repository_gap_analysis.md`。
