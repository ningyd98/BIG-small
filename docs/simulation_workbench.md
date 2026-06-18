# Simulation Workbench

BIG-small Simulation Workbench 是 Phase 11 的主线前端和 API。它用于仿真调试、实验配置、批量运行、参数扫描、模式对比、跨后端对比、实时监控、指标分析、复现实验和报告导出。

本工作台不控制真实机械臂。浏览器只提交高层 `ExperimentDraft`，后端再用 `ExperimentConfig` 和固定 runner allowlist 生成运行计划。

## 能力边界

- 场景来源：`scenario_registry()` 是 S01-S15 的权威来源。
- 配置来源：`ExperimentConfig` 是实验配置权威模型。
- 类型来源：前端类型由 FastAPI OpenAPI 生成。
- 运行入口：`/api/v1/simulation`。
- 实验 runner：只允许固定枚举，不接受 shell、脚本路径、模块名、环境变量或 executable。
- 硬件声明：`real_controller_contacted=false`，`hardware_motion_observed=false`，`hardware_write_operations=[]`。

## 页面

- Simulation Workbench：实验草稿、参数编辑、backend readiness、运行队列。
- Scenario Library：动态展示 S01-S15、故障、invariants 和 backend support。
- Batch Experiment：多场景、多 seed、多模式和 sweep。
- Live Run：状态、事件时间线、SafetyShield 事件和 rolling metrics。
- Result Analysis：指标卡片、图表和 artifact。
- Mode Comparison：PCSC、ETEAC、AUTO 对比。
- Cross Backend Comparison：MuJoCo 和 Isaac paired comparison。

## 后端

API 前缀为 `/api/v1/simulation`，包括 capabilities、scenarios、parameter schema、validate、runs、batches、comparisons、exports 和 WebSocket stream。Isaac 不可用时返回 `BLOCKED_BY_ENV`，不会回退到 Mock 后声称 Isaac 成功。

