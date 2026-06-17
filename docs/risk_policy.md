# 风险策略

Phase 7 的风险评估是确定性的规则评估，不使用黑盒机器学习。

`RiskPolicy` 带版本，定义各风险分量权重、LOW/MEDIUM/HIGH/CRITICAL 阈值、数据过期阈值、关键输入缺失惩罚、场景移动惩罚和缓存未命中惩罚。

## 风险分量

`RiskSnapshot` 会把以下分量归一到 0-100：

- `task_risk`：技能、任务类型、契约完整性、已持久化剩余步骤、边缘能力。
- `scene_dynamics_risk`：目标移动、障碍物数量和变化率、场景新鲜度、场景置信度。
- `perception_risk`：场景置信度、目标置信度、目标丢失。
- `network_risk`：延迟、抖动、丢包、断连时长、心跳新鲜度、云端可用性。
- `execution_risk`：失败、超时、重规划、缓存置信度/未命中、安全拒绝历史。
- `safety_risk`：最近一次 `SafetyShield` 决策、安全拒绝、暂停/拒绝/急停。

## Fail-Closed 规则

关键输入缺失时不能得到 LOW 风险。评估器会把总风险抬到配置的缺失输入惩罚值，并返回 `INSUFFICIENT_EVIDENCE`。

安全风险不能被平均掉。`EMERGENCY_STOP` 会硬覆盖所有分量，直接返回 `CRITICAL`，分数为 100。

每个 `RiskSnapshot` 都记录分量分数、总分、风险等级、新鲜度、缺失输入、原因码、策略版本、时间戳和确定性输入哈希。
