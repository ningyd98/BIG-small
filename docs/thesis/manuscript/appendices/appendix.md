# 附录

## 附录 A TaskContract 示例

TaskContract 包含 task_id、steps、skill、parameters、preconditions、timeout、safety_constraints 和 version 等字段；所有候选动作必须通过 schema、语义校验和 SafetyShield。

## 附录 B 状态机

边缘任务状态机覆盖 CREATED、RUNNING、PAUSED、RECOVERING、COMPLETED、FAILED 和 SAFETY_STOPPED；Simulation Runtime job 状态机覆盖 QUEUED、LEASED、RUNNING、FINALIZING、SUCCEEDED、FAILED、CANCELLED、TIMED_OUT、INTERRUPTED 和 RECOVERY_PENDING。

## 附录 C F01-F20 与 B01-B03

{{ experiment_status }}

- B01_LLM_ONLY_ONESHOT：一次模型调用生成完整 TaskContract，异常时失败或整体重试。
- B02_LLM_ONLY_REACTIVE：每一步或异常后调用模型生成下一动作，仍经过契约校验和 SafetyShield。
- B03_PIPELINE_ONLY_PAIRED_DESIGN：fake-provider 仅用于验证配对对比管线，不进入正式模型性能结论。
- B03_REAL_RUNTIME_PAIRED_COMPARISON：仅在 REAL_LLM_RUNTIME 或 LOCAL_LLM_RUNTIME accepted 后，用于 LLM-only one-shot、reactive、PCSC、ETEAC、AUTO 的相同场景、seed、后端和安全策略配对比较。

## 附录 D 图表索引

{{ figures }}

## 附录 E 表格索引

{{ tables }}

## 附录 F 证据追踪矩阵

{{ trace_table }}

## 附录 G 文献缺口

正式参考文献只纳入已核验条目。当前需要继续补充云边协同机器人、快慢双系统、事件触发控制、LLM for robotics、LLM-only agent control、机器人安全、Sim2Real、MuJoCo、Isaac Sim、ROS 2、MoveIt、边缘自治和工程证据链相关文献。
