# Skill Cache

Phase 7 增加了高层技能模板和执行统计的持久化缓存。

缓存从不保存关节角序列、PWM、电机命令、舵机脉冲、原始低层轨迹，或任何可以绕过 `SafetyShield` 的结果。命中缓存只表示系统可以复用一个高层 `SkillName` 和参数模板。真正执行前，系统仍必须构建或更新 `TaskContract`，执行契约校验，运行 `SafetyShield`，并根据当前场景、机器人状态和安全策略解析参数。

## 关键模型

`SkillCacheKey` 包含技能名、机器人型号、末端执行器、对象类别、任务意图、工作空间、参数 schema 版本、机器人能力哈希、安全策略哈希和标定版本。单独的 `skill_name` 永远不够。

`SkillTemplate` 初始状态是 `CANDIDATE`，之后可以变成 `TRUSTED`、`QUARANTINED`、`INVALIDATED` 或 `EXPIRED`。

`SkillExecutionRecord` 保存经过审计的执行结果、安全决策、耗时、重试次数、场景置信度、网络质量和证据哈希。

`SkillStatistics` 汇总执行总数、成功/失败次数、安全拒绝、超时、平均耗时、近期成功率、置信分、连续失败次数和最近一次成功/失败时间。

## 状态流转

模板创建时是 `CANDIDATE`。配置好的晋升策略只有在足够多次成功、证据完整、没有安全拒绝、没有连续失败时，才可以把模板晋升为 `TRUSTED`。

安全拒绝、急停、重复失败、无效证据，或当前安全/能力/标定状态不兼容，都会把模板隔离或作废。TTL 到期后模板变成 `EXPIRED`。

repository 支持 InMemory 和 SQLite 实现，包含 CAS 模板更新、执行幂等、冲突检测、审计事件和重启恢复。
