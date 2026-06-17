# Phase 8 报告

Phase 8 实现了可复现实验框架，用来比较 PCSC、ETEAC 和 AUTO 在确定性场景、网络 profile、seed、缓存策略和消融配置下的表现。

## 已实现

- 强类型实验模型和 schema 版本 `phase8.v1`。
- 确定性虚拟时钟和 seed 驱动的网络模拟器。
- 十五个场景定义：S01-S15。
- PCSC、ETEAC、AUTO 统一 runner，其中 AUTO 只在 PCSC 和 ETEAC 之间选择。
- 在实验边界集成 Skill Cache、RiskEvaluator 和 ModeTransitionService。
- auto-mode 与 event-autonomy repository 的 SQLite 重启 smoke 恢复。
- 指标、统计汇总、可复现哈希、artifact writer、batch runner、CLI 和验证器。
- smoke 矩阵和 full-suite 启动检查均已成功运行。

## 已执行样本

- Smoke 样本：21 次运行，18 次成功。
- Full-suite 启动样本：45 次运行，36 次成功。

## 限制

这仍是 Mock/仿真实验，不证明真实硬件安全或性能。网络行为和物理行为都是工程抽象。真实硬件验证仍要进入 Phase 9 之后的流程。
