# Thesis Research Questions

## RQ1

与 PCSC 相比，ETEAC 是否能够在保证任务成功率和安全性的前提下，降低云端调用和通信开销？

- 自变量：控制模式 PCSC/ETEAC。
- 因变量：任务成功率、云端调用次数、通信次数、总耗时、安全干预次数。
- 控制变量：场景、seed、网络配置、任务契约、backend。
- 场景：S01、S07、S08、S09。
- seed：full profile 至少 30 个 baseline seed。
- repetitions：full profile 至少 3 次。
- 统计检验：配对差异优先，非正态使用非参数检验。
- 接受标准：ETEAC 云端调用和通信显著降低，且成功率和 unsafe_command_execution_count 不劣化。
- 不能推出：不能推出真实机械臂通信成本或真实控制性能。

## RQ2

AUTO 是否能够在不同网络和故障条件下，在 PCSC 与 ETEAC 之间获得更优的综合性能？

- 自变量：控制模式 PCSC/ETEAC/AUTO，网络延迟、抖动、丢包。
- 因变量：成功率、总耗时、mode switch、通信次数、恢复成功。
- 控制变量：场景、seed、backend、任务契约和风险策略版本。
- 场景：S07、S08、S13。
- seed：关键网络条件每档至少 20 个 seed。
- repetitions：full profile 至少 3 次。
- 统计检验：多组比较并控制多重检验。
- 接受标准：AUTO 在综合指标上不劣于两种固定模式，并在至少一个故障条件下改善效果量。
- 不能推出：不能推出 AUTO 在真实机器人现场一定更优。

## RQ3

边缘本地恢复和局部重规划是否能够降低任务失败率和云端完整重规划次数？

- 自变量：本地恢复开关、局部重规划开关、retry budget。
- 因变量：失败率、本地恢复成功数、replan count、cloud fallback count。
- 控制变量：任务、网络、seed、backend、cache policy。
- 场景：S02、S03、S04、S09、S15。
- seed：故障实验每个条件至少 20 次。
- repetitions：full profile 至少 3 次。
- 统计检验：配对成功率差异和 effect size。
- 接受标准：恢复或局部重规划降低失败率或完整云端重规划次数。
- 不能推出：不能推出真实夹爪或真实传感器恢复能力。

## RQ4

SafetyShield 和 HardwareExecutionGate 是否能够在危险请求、过期遥测、控制器不可用和配置异常情况下保持 fail-closed？

- 自变量：危险请求类型和环境异常类型。
- 因变量：rejected_action_count、unsafe_command_execution_count、emergency_stop_event。
- 控制变量：任务契约、安全策略版本、dry-run backend。
- 场景：S06、S14 和 Phase 10 dry-run fault cases。
- seed：每类故障至少 20 次。
- repetitions：full profile 至少 3 次。
- 统计检验：计数审计和零容忍断言。
- 接受标准：unsafe_command_execution_count 必须为 0。
- 不能推出：不能推出真实控制器急停链路已验证。

## RQ5

MuJoCo 和 Isaac Sim 的实验结果是否具有一致趋势？主要 sim-to-sim gap 来自哪些指标？

- 自变量：backend MuJoCo/Isaac。
- 因变量：paired_success_agreement、completion_time_delta、trajectory/path/safety delta。
- 控制变量：TaskContract、seed、网络条件、场景。
- 场景：S01、S07、S14。
- seed：每个任务至少 20 对。
- repetitions：full profile 至少 3 次。
- 统计检验：paired difference、置信区间和 disagreement rate。
- 接受标准：趋势一致且 disagreement 可解释。
- 不能推出：不能推出 sim-to-real gap。

## RQ6

不同规划器或模型 provider 是否影响规划成功率、延迟、修复次数和契约有效率？

- 自变量：MOCK、RULE_BASED、OPENAI_COMPATIBLE、OLLAMA。
- 因变量：planner_success、valid_contract_rate、repair_count、response_latency_ms。
- 控制变量：任务指令、场景、控制模式、dispatch=false。
- 场景：S01、S07。
- seed：每个 provider 至少 20 次有效调用。
- repetitions：full profile 至少 3 次。
- 统计检验：多组比较和置信区间。
- 接受标准：provider 能生成有效 contract，且不触发硬件执行。
- 不能推出：未配置真实云 API 或 Ollama 时不能推出真实模型能力。

## RQ7

技能缓存、风险评估、AUTO 选择器和局部恢复各自对系统性能有何贡献？

- 自变量：cache、risk policy、AUTO、local recovery、local replanning 开关。
- 因变量：成功率、通信次数、云端调用、恢复成功、安全干预。
- 控制变量：场景、seed、网络和 backend。
- 场景：S11、S12、S13、S04、S02、S03。
- seed：每个消融条件至少 20 次。
- repetitions：full profile 至少 3 次。
- 统计检验：配对消融差异、effect size 和 CI。
- 接受标准：各模块至少在目标指标上有可解释贡献。
- 不能推出：不能用 simulation ablation 证明真实硬件安全盾可关闭。
