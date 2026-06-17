# AUTO 模式选择

AUTO 不是第三套执行引擎。它只在已有两种模式之间做选择：

- `PERIODIC_CLOUD_SUPERVISION`
- `EVENT_TRIGGERED_EDGE_AUTONOMY`

AUTO 也可以保持当前模式、请求更多观测、暂停或安全停止。它不能绕过 `TaskContract`、`ContractValidator`、`SafetyShield`、`TaskExecutor`、checkpoint 恢复、CAS、幂等处理或完成证据。

## 决策输入

`AutoModeSelector` 使用当前模式状态、active contract 完整性、checkpoint 持久化状态、`RiskSnapshot`、Skill Cache 查询结果、事件自治就绪状态、监督服务可用性、原子步骤状态和切换历史。

## 选择规则

事件自治只有在以下条件同时满足时才可选：风险为 LOW 或允许的 MEDIUM，场景稳定，契约和 checkpoint 完整，边缘自治就绪，缓存可信或无需缓存，感知新鲜，并且没有高风险事件等待处理。

周期监督在以下情况优先：云端监督可用，场景动态变化适合云端观察，并且风险没有越过暂停或停止阈值。

出现 CRITICAL 风险、安全拒绝、急停、缺少安全证据、契约/checkpoint 不完整、场景过期，或云端不可用且边缘自治未就绪时，暂停或安全停止优先。

## 防抖

选择器会执行最小驻留时间、切换冷却、单任务最大切换次数、原子步骤安全边界和 CRITICAL 风险立即升级规则，避免模式来回抖动。
