# Phase 10.2A-R 仓库文档审计

## 基线

- Repository：`ningyd98/BIG-small`
- HEAD：`5dce1b0b491e41ad821fc4c4ca5c798e56eff552`
- `origin/main`：`5dce1b0b491e41ad821fc4c4ca5c798e56eff552`
- 审计开始时 worktree：干净
- 当前已接受状态：`PHASE10_MOVEIT_DRY_RUN_ACCEPTED`
- 真实机械臂验证：`NOT_STARTED`
- 最高真实硬件验收级别：`NONE`

## 当前仓库信息架构

- 权威 Python 源码位于 `src/cloud_edge_robot_arm`。
- 顶层 `contracts`、`edge`、`shared` 和 `simulation` 是说明性或 schema-facing 目录；运行时代码在 `src` 下。
- `configs` 包含 safety、Phase 9 和 real robot 示例配置。`configs/real_robot` 不能包含真实现场 IP、serial 或 credential。
- `scripts` 包含大量分阶段 runner 和 verifier，以及 `run_checks.sh`；目前没有脚本索引或统一项目 verifier。
- `docs` 包含 architecture、phase report、acceptance note、safety doc 和历史计划文档，但缺少单一文档入口。
- `artifacts` 包含权威证据和生成的 run log。它不是源码，不应在文档治理中重新格式化。
- `data`、`experiments/results`、ROS build output 和 tool cache 都是本地/生成数据。

## README 问题

- 第一段是很长的阶段历史，不像项目入口。
- 当前状态准确，但在当前 Phase 9.2/10.2A 状态前塞入太多 Phase 9.1 历史阻塞。
- quick-start 命令混有大量阶段专用和环境专用 verifier，CI-safe、runtime-specific、real-hardware-only 命令不容易区分。
- 目录结构仍以 Phase 0/1 时代方式描述 tests，没有反映当前 Phase 10 package、Phase 9.2 evidence 或文档布局。
- safety boundary 虽然存在，但没有作为新用户容易看到的清晰声明。

## Docs 问题

- 没有 `docs/README.md` 索引，用户必须知道阶段编号才能找文档。
- 没有 `docs/project_status.md` 区分 Phase 9.1 历史状态和当前 Phase 9.2 最终状态。
- 没有 `docs/repository_structure.md` 解释源码目录、说明性顶层目录和 artifact 的边界。
- 没有 `docs/verification.md` 区分 CI-safe、environment-specific 和 real-hardware-only 命令。
- 没有 glossary、roadmap、changelog 或 contribution guide。
- `docs/architecture.md` 有价值，但仍像按时间记录的架构日志；它应转成当前权威文档，并带明确分层和图示。
- `docs/repository_gap_analysis.md` 等历史文档应保持历史性质，不应改写成当前状态。

## Scripts 问题

- 没有 `scripts/README.md` 按用途、环境需求、artifact 输出和硬件风险分组脚本。
- 没有统一的 `scripts/verify_project.py`，无法按 profile 安全编排 verifier。
- 原有 verifier 路径稳定，应保持兼容。
- 阶段脚本数量很多；现在移动它们风险大于收益。

## CI 问题

- `.github/workflows/ci.yml` 运行 compile、ruff、mypy、pytest 和 Phase 3-9 CI-safe checks。
- CI 没有运行 Phase 10 软件侧 verifier。
- CI 没有检查文档链接、README 脚本引用、Mermaid fence 或敏感路径/token 泄漏。
- 除非专用 runtime job 真正产出证据，CI 不得声明 Isaac runtime、MoveIt runtime 或真实机械臂验证通过。

## 命名和状态不一致

- README 重复出现 `PHASE9_1_CORE_ACCEPTED_WITH_ENV_BLOCK`，但没有清楚分开历史 Phase 9.1 语境和当前 Phase 9.2 final acceptance。
- 当前术语应统一为：
  - cloud intelligent planning：`云端智能规划`
  - edge safety execution：`边缘安全执行`
  - `PCSC`
  - `ETEAC`
  - `AUTO 双模式选择器`
  - `Synthetic Dry-Run`
  - `MoveIt Runtime Dry-Run`
  - `Real Robot Read-Only`
  - `Real Robot Motion`
  - `evidence`、`artifact`、`provenance`

## 建议修改范围

- 将 `README.md` 改写为简洁的项目入口。
- 增加文档入口、项目状态、仓库结构、验证、术语表、路线图、变更日志和贡献文档。
- 更新 architecture 和 Phase 10 文档，使其与 Phase 10.2A evidence 和边界一致。
- 增加 `scripts/README.md`、`scripts/check_docs.py` 和 `scripts/verify_project.py`。
- 更新 `scripts/run_checks.sh` 和 `.github/workflows/ci.yml`，加入文档检查和 Phase 10 软件检查。
- 为文档检查和统一 verifier profile 增加测试。

## 明确不做

- 不修改 `SafetyShield` 决策语义。
- 不放宽 `HardwareExecutionGate`。
- 不修改 `PCSC`、`ETEAC` 或 `AUTO` 核心行为。
- 不修改 Phase 8、9 或 10 的权威实验结果。
- 不删除已接受 artifact。
- 不连接或命令真实硬件。
- 不移动 Python 源码包，也不破坏现有 import path。
- 不移除既有 verifier 脚本路径。
- 不 rewrite、squash、amend、rebase 或 force-push 已推送的 `main` 历史。
