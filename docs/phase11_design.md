# Phase 11 Design

Phase 11 将 Dashboard 的基础实验页面升级为 BIG-small Simulation Workbench。核心目标是把场景浏览、实验配置、Batch、Sweep、多 seed、模式比较、跨后端比较、实时监控、指标分析、复现和导出放进统一工具链。

## 设计原则

- `scenario_registry()` 是场景权威来源。
- `ExperimentConfig` 是实验配置权威模型。
- React 页面不再硬编码场景列表、实验类型或 control mode。
- 所有实验通过 FastAPI 和固定 allowlist runner。
- Mock、MuJoCo、Isaac 和 MoveIt Dry-Run 结果严格区分。
- Isaac 不可用返回 `BLOCKED_BY_ENV`。
- 大型 JSONL 和 metrics 通过 worker 处理。
- 真机模块冻结，仅保留回归测试。

## Safety Boundary

Phase 11 始终保持：

- `real_controller_contacted=false`
- `hardware_motion_observed=false`
- `hardware_write_operations=[]`

不开发真实机械臂 adapter，不运行 Level 0 hardware verifier，不发送 MoveIt execute，不连接真实控制器。

