# Final Project Report

## 1. 项目背景

BIG-small 面向边缘智能场景的小型机械臂云边协同控制，研究云端规划和边缘安全执行的分工。

## 2. 研究目标

系统目标是比较 PCSC、ETEAC 和 AUTO，在仿真与 dry-run 范围内验证安全、恢复、重规划和可复现证据。

## 3. 系统架构

系统由云端规划、边缘运行时、安全盾、仿真后端、仿真工作台、异步运行时和模型控制中心组成。

## 4. 核心模块

核心模块包括 TaskContract、SafetyShield、TaskExecutor、Simulation Workbench、Simulation Runtime 和 Model Control Center。

## 5. PCSC / ETEAC / AUTO

PCSC 周期性请求云端监督；ETEAC 由边缘事件触发本地恢复和必要重规划；AUTO 只在两者之间受限切换。

## 6. SafetyShield

SafetyShield 对速度、工作空间、碰撞、急停、过期遥测和配置异常保持 fail-closed。

## 7. 仿真平台

MuJoCo 和 Isaac 用于仿真与跨后端比较；Isaac 环境不可用时记录 `BLOCKED_BY_ENV`。

## 8. Dashboard

Dashboard 提供状态、证据、Simulation Workbench 和 Model Control Center，不直接控制机器人。

## 9. Simulation Runtime

Simulation Runtime 提供异步队列、SQLite 持久化、worker lease、cancel、timeout、retry 和恢复。

## 10. Model Control Center

Model Control Center 支持 profile、安全 secret、endpoint policy、Ollama 管理和 planner dry-run。

## 11. 实验设计

Phase 12 冻结 RQ1-RQ7 和 F01-F20，支持 smoke、validation 和 full profile。

## 12. 实验结果

结果由 `artifacts/phase12` 自动生成，smoke 只验证管线，full 才可支撑最终统计结论。

## 13. 创新点

项目贡献在于云边协同模式、安全边界、事件触发自治、可复现仿真实验和证据化运行时。

## 14. 工程贡献

工程贡献包括前后端工作台、持久运行时、模型控制中心、verifier 和论文资产导出。

## 15. 局限性

当前没有真实机械臂实验；仿真结果不能直接等同真实控制效果。

## 16. 真实机械臂边界

真实机械臂验证为 `NOT_STARTED`，最高硬件验收级别为 `NONE`。

## 17. 后续工作

后续真实硬件路线需要单独安全审批、真实 Level 0 只读证据和 Level 1-6 分级验收。

## 18. 最终状态

最终封板状态只能是软件与仿真项目状态，不能声明真实机械臂项目 accepted。
