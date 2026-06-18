# Simulation Metrics And Charts

Phase 11 统一 `SimulationMetric` 模型，每条指标包含 name、value、unit、source、aggregation、sample_count、backend、scenario、seed 和 control_mode。

## 指标

- task success
- completion time
- planning time
- execution time
- cloud calls
- communication count
- local retries
- local recovery
- replan count
- safety interventions
- mode switches
- cache hits
- recovery time
- latency
- packet loss
- CPU
- memory
- collision count
- final pose error
- reproducibility hash

## 图表

前端使用 ECharts，并通过动态 import 加载图表库。支持 bar、line、stacked bar、timeline、distribution、box plot、paired delta 和 safety timeline。图表必须有单位、tooltip、legend、data zoom、空状态和 `BLOCKED_BY_ENV` 状态。

Vite 使用 `manualChunks` 拆分 `react`、`antd` 和 `echarts`，不通过提高 chunk warning limit 隐藏问题。

