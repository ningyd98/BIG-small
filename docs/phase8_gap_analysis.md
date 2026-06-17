# Phase 8 差距分析

Phase 8 要在稳定的 Phase 3-7 控制面上搭建实验系统。它不重新设计 `TaskContract`、`SafetyShield`、`TaskExecutor`、事件自治、重规划、Skill Cache、`RiskEvaluator`、`AutoModeSelector` 或 `ModeTransitionService`。

## 可复用模块

- `contracts.models`：`TaskContract`、`CloudCommand`、`CommandAck`、`EdgeEvent`、`CompletionSummary`、`RiskSnapshot`、`AutoModeDecision`、transition enum 和共享控制模式。
- `edge.runtime.TaskExecutor`：受 `SafetyShield` 保护的标准 `TaskContract` 执行路径。
- `edge.safety`：`SafetyShield`、安全决策、安全 provider 和 stop 语义。
- `cloud.supervision`：PCSC 概念、周期 supervisor、decision 和 supervision 持久化。
- `edge.event_mode`、`edge.recovery`、`cloud.replanning`：ETEAC 事件、重试预算、失败摘要、本地重规划、CAS apply 和重启恢复。
- `skill_cache`：高层模板缓存、执行记录、promotion、quarantine、invalidation、幂等和 SQLite 重启恢复。
- `risk`：带版本的确定性 `RiskEvaluator` 和 fail-closed `RiskPolicy`。
- `auto_mode`：在 PCSC/ETEAC 之上做 AUTO 选择，并持久化模式切换。
- `repositories`：任务、事件自治、技能缓存和自动模式的 InMemory/SQLite repository。
- `simulation.mock_robot`：用于 CI 的确定性 `MockRobotAdapter` 和故障注入 hook。

## 缺失的实验基础设施

- 还没有 Phase 8 专用实验领域模型和 schema 版本。
- 还没有带 priority 和插入顺序的确定性离散事件虚拟时钟。
- 还没有由 seed 驱动的网络模拟器，覆盖 latency、jitter、loss、duplication、reordering、outage、bandwidth accounting、timeout 和 cloud unavailable。
- 还没有 15 个必需场景的统一 registry。
- 还没有统一 runner 同时跑 PCSC、ETEAC 和 AUTO 实验。
- 还没有 batch runner、smoke/full suite 矩阵和命令行入口。
- 还没有 metrics/statistics 层来产出原始 run 指标、Wilson 置信区间、确定性 bootstrap、CSV/JSON summary 和 Markdown report。
- 还没有忽略 wall-clock 字段的复现 hash。
- 还没有 artifact writer，用于 manifest、JSONL event/run、summary 文件和生成报告。

## 数据模型扩展

Phase 8 应增加实验本地模型，不修改 Phase 3-7 的持久化模型：

- `ExperimentConfig`、`ScenarioDefinition`、`FaultEvent`、`ExperimentRun`、`ExperimentResult`、`MetricSummary` 和 artifact manifest。
- 明确的实验 enum，覆盖 mode alias、scenario id、network profile、fault type、cache policy、ablation、result status、event type 和 metric unit。
- `ExperimentResult` 需要包含观测指标、派生指标、反事实指标、复现 hash 和 metadata。

现有 Phase 3-7 的序列化模型不需要为 Phase 8 调整。

## 必要测试

- config 校验、重复 scenario id、mode 校验、seed 边界和 unit 校验。
- 虚拟时钟排序、同 timestamp 的 priority 排序、最大时长限制，以及不发生真实 sleep。
- 网络 profile 和确定性故障行为。
- 每个必需场景至少覆盖一个关键行为。
- PCSC、ETEAC、AUTO runner smoke 测试，以及 AUTO 只作为选择器的约束。
- 风险/模式切换中的 dwell、cooldown、switch limit、emergency stop 和 insufficient evidence 路径。
- Skill Cache 的 hit、miss、promotion、quarantine、invalidation 和 cache ablation。
- stale、duplicate、reordered、idempotency 和 CAS command handling 指标。
- 实验状态写入过程中的 SQLite restart。
- 同 config+seed 的复现 hash 相等，不同 seed 的受控差异可见。
- artifact 可解析，summary 列稳定。
- 通过 `scripts/verify_phase8.py` 覆盖 Phase 3-7 验收回归。

## 兼容性风险

- 现有 Phase 7 文档和测试都假定 AUTO 不是执行引擎；Phase 8 必须保留这个边界，只把 AUTO decision 记录为模式选择。
- 实验 timestamp 必须区分虚拟时间和 wall-clock metadata，避免复现 hash 漂移。
- 安全反事实只能作为 shadow metric 计算；不安全动作不能进入 `TaskExecutor`。
- SQLite restart 测试必须使用现有 repository 和幂等语义，不能另造一套持久化机制。
- 实验框架不能新增强制绘图库依赖，也不能要求网络访问、ROS 2、真实硬件、真实相机或生产 LLM。
