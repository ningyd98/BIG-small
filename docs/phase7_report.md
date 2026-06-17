# Phase 7 报告

Phase 7 实现了 Skill Cache、确定性风险评估、AUTO 模式选择、模式切换记录、持久化、API 入口、生产配置门禁、测试和验收验证。

AUTO 仍然只是对两套既有引擎做选择。它不执行技能，不回放低层控制，不绕过安全或完成证据。

## 已实现

- `skill_cache`：数据模型、InMemory repository、SQLite repository、晋升/隔离/作废/过期、CAS、幂等、统计。
- `risk`：带版本的 `RiskPolicy`、确定性 `RiskEvaluator`、关键输入缺失 fail-closed、安全硬覆盖。
- `auto_mode`：选择策略、持久化状态/决策/切换、InMemory/SQLite repository、切换服务。
- 能力查询、风险评估/最新结果、auto 决策/状态、模式切换、Skill Cache 模板/统计等 API。
- 生产配置要求显式提供 durable repositories 和 risk policy，否则 AUTO 不可用。
- `scripts/verify_phase7.py` 和 Phase 7 单元测试。

## 当前限制

仍然没有真实机器人 SDK、ROS 2/MoveIt 2 集成、真实相机模型、生产 LLM CI 或真实硬件实验。Phase 8 批量对比实验尚未开始。
