# Simulation Batch And Sweep

Phase 11 支持单次运行、场景批量、多 seed、模式比较、backend paired run、full matrix、smoke suite 和 validation suite。

## Sweep 维度

- scenario
- seed
- control mode
- latency
- jitter
- packet loss
- supervision period
- cache policy
- risk threshold

`SweepPlanBuilder` 计算 Cartesian product、总 run 数、非法组合、重复参数、backend 不支持项和最大并发。超过后端 `max_batch_runs` 时必须阻止提交。

## Batch manifest

`BatchPlanBuilder` 输出强类型 batch manifest，后端写入：

- `batch_manifest.json`
- `run_index.json`
- `summary.json`
- `summary.csv`
- `comparison.json`
- `report.md`

这些 artifact 只属于 `artifacts/phase11/`，不得覆盖 Phase 8/9 权威 artifact。

