# Simulation Live Monitoring

Live Run 页面通过 `/api/v1/simulation/stream` 和 polling fallback 展示运行状态、事件时间线、SafetyShield 事件、网络状态、retry、replan、rolling metrics 和 artifact 创建事件。

## Stream 语义

- 使用 Dashboard 相同 auth policy。
- 支持 `last_sequence` replay。
- 发送 heartbeat。
- 限制消息大小。
- 前端检测 sequence gap、重复事件和 stale 状态。
- 断线后回退 polling。
- 不在 URL query 中传明文 token。

## 事件类型

事件时间线统一组装 experiment started、step started、step completed、fault injected、fault detected、network degraded、cloud call、supervision tick、local retry、local recovery、replan requested、replan applied、SafetyShield allow/reject、emergency stop、task completed 和 artifact created。

## 时间轴

时间线同时保留 virtual time 和 wall-clock time。过滤维度包括 source、severity 和 payload detail。

