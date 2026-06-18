# Phase 11 Acceptance

Phase 11 只有在以下条件全部满足时才可声明 `PHASE11_SIMULATION_WORKBENCH_ACCEPTED`。

## Backend

- scenario count 等于 15。
- `/api/v1/simulation/capabilities`、`/scenarios`、`/parameter-schema`、`/runs`、`/batches`、`/comparisons`、`/exports` 和 `/stream` 可用。
- `ExperimentDraft` 拒绝 extra 字段和 shell/path/env/module/executable 参数。
- Runner allowlist 固定为 `MOCK_SCENARIO`、`MUJOCO_SCENARIO`、`PHASE8_BATCH`、`PHASE8_SWEEP`、`PHASE9_MUJOCO_BENCHMARK`、`ISAAC_BENCHMARK` 和 `CROSS_BACKEND_PAIRED`。
- 不存在 hardware、controller 或 Level 1 simulation route。

## Frontend

- `SimulationLabPage` 保留兼容路由，但包装新的 `SimulationWorkbenchPage`。
- 前端无硬编码 S01/S14 场景列表。
- config、sweep、batch、run monitor、metrics、comparison、reproduction 和 export 工具类存在并通过测试。
- ECharts 动态导入，Vite manual chunks 已配置。

## E2E

Playwright 至少 15 个独立测试，并使用真实 FastAPI。不得全部使用 route mock。

## Hardware Boundary

`real_controller_contacted=false`，`hardware_motion_observed=false`，最高硬件验收级别仍为 `NONE`。

