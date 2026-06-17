# 变更记录

本项目按里程碑记录变更，不在这里声明版本号。

## 未发布

- 整理仓库文档架构。
- 增加文档一致性检查和统一验证 profile。

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
