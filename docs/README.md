# BIG-small 文档入口

本页按主题整理文档。需要追溯阶段过程时再看 Phase 文档；日常查状态、架构和验证命令，优先从这里进入。

## 项目概览

- [项目入口](../README.md): 当前能力、快速开始和安全声明。
- [项目状态](project_status.md): 各能力域状态、验证入口、证据和硬件声明边界。
- [路线图](roadmap.md): Phase 10.2A-R 之后的计划。
- [术语表](glossary.md): PCSC、ETEAC、AUTO、证据、溯源等术语。

## 系统架构

- [架构总览](architecture.md): 当前权威分层、时序图和 Phase 10.2A 边界。
- [系统规划](plan.md): 历史总体规划，保留用于追溯。

## 数据契约

- [契约说明](contracts.md): TaskContract 和消息结构。
- [API 说明](api.md): 云端和边缘 API 入口。

## 云端规划与监督

- [失败摘要](failure_summary.md): 失败摘要和重规划输入。
- [本地恢复](local_recovery.md): 本地恢复策略。
- [局部重规划](local_replanning.md): 局部重规划流程。
- [网络退化](network_degradation.md): 网络退化与故障处理。

## 边缘运行时与安全

- [安全设计](safety_design.md): 安全盾设计。
- [安全策略](safety_policy.md): 安全策略。
- [安全规则](safety_rules.md): 规则清单。
- [真机安全边界](real_robot_safety.md): 真机接入前安全边界。

## PCSC / ETEAC / AUTO

- [事件触发边缘自治](event_triggered_autonomy.md): ETEAC 状态机。
- [AUTO 模式选择](auto_mode_selection.md): AUTO 双模式选择器。
- [模式切换](mode_transition.md): 模式切换生命周期。

## 技能缓存与风险策略

- [Skill Cache](skill_cache.md): 高层技能模板缓存。
- [风险策略](risk_policy.md): 风险分量和策略版本。

## 实验平台

- [Phase 8 指标](phase8_metrics.md): 实验指标。
- [Phase 8 可复现性](phase8_reproducibility.md): 可复现性。
- [Phase 8.2 恢复](phase8_2_recovery.md): 周期闭环和恢复。

## MuJoCo / Isaac / ROS 2 / MoveIt

- [Phase 9 仿真架构](phase9_simulator_architecture.md): 仿真后端结构。
- [MuJoCo 后端](phase9_mujoco_backend.md): MuJoCo 物理后端。
- [Isaac 后端](phase9_2_isaac_backend.md): Isaac Sim 6.0 运行时。
- [ROS 2 / MoveIt](phase9_ros2_moveit.md): ROS 2 与 MoveIt 集成说明。
- [Phase 9.2 跨后端对比](phase9_2_cross_backend.md): MuJoCo 与 Isaac 成对比较。

## 真实机械臂准备

- [Phase 10 设计](phase10_design.md): 真机接入前门禁设计。
- [Dry-run 验证](dry_run_validation.md): Synthetic 与 MoveIt dry-run 边界。
- [真实设备配置](real_robot_configuration.md): 真实设备配置规则。
- [真实硬件分级验收](real_robot_acceptance_levels.md): Level 0-6 分级验收。
- [操作员确认](operator_confirmation.md): 一次性操作员确认模型。
- [证据溯源](evidence_provenance.md): source tree hash 与 artifact 溯源。
- [Sim-to-real 评估](sim_to_real_evaluation.md): 后续 sim-to-real 指标。

## 阶段报告

阶段报告保留在 `docs/phase*_report.md` 和 `docs/phase*_acceptance.md`。平时建议先看 [项目状态](project_status.md)，再按需要打开具体 Phase 文档。

## 验证与部署

- [验证说明](verification.md): CI-safe、environment-specific 和 real-hardware-only 命令。
- [脚本索引](../scripts/README.md): 脚本用途和风险分类。
- [贡献说明](../CONTRIBUTING.md): 开发、提交和 artifact 规则。

## 历史审计和复盘

- [仓库审计](repository_audit.md): 初始仓库审计。
- [仓库差距分析](repository_gap_analysis.md): 早期差距分析。
- [复盘记录](reviews/phase5_retrospective_review.md): 历史 review 示例。
