# Phase 8.2 实验敏感性

Phase 8.2 把指标接回运行时机制，去掉之前过于平坦的 benchmark 行为。

## 网络机制

- PCSC tick 决策作为云到边消息发送。
- 网络中断恢复使用 reconnect 和 heartbeat delivery 回调。
- 云不可用场景会安排真实 timeout 事件。
- 丢包可以丢弃监督决策或恢复心跳消息，从而触发重试事件。
- jitter 和乱序由 `NetworkSimulator` 按配置 seed 采样。

## 模式机制

- PCSC 周期性调用云端监督。
- ETEAC 不产生周期 tick，只在本地执行需要云端帮助时上传失败/重规划摘要。
- AUTO 记录风险和缓存信号，准备切换，并且只在安全边界提交。

## 有效性视图

批量输出包含：

- `mode_by_scenario`
- `network_by_scenario`
- `mode_by_network`
- `seed_variability`
- `validity_guard`

守卫会检查 mode、network 和 seed 不全都相同，并确认故障检测延迟不是始终为 0。
