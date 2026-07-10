# 第八章 实验设计

## 8.1 RQ1-RQ8

- RQ1：与 PCSC 相比，ETEAC 是否能在保证成功率和安全性的前提下降低云端调用和通信开销？
- RQ2：AUTO 是否能在不同网络和故障条件下获得更优综合性能？
- RQ3：边缘本地恢复和局部重规划是否能降低任务失败率和云端完整重规划次数？
- RQ4：SafetyShield 和 HardwareExecutionGate 是否能保持 fail-closed？
- RQ5：MuJoCo 和 Isaac Sim 的实验趋势是否一致，gap 来自哪些指标？
- RQ6：不同 planner/provider 是否影响规划成功率、延迟、修复次数和契约有效率？
- RQ7：技能缓存、风险评估、AUTO 选择器和局部恢复分别贡献什么？
- RQ8：与 LLM-Only Decision Baseline 相比，云边协同架构能否在成功率、时延、鲁棒性、通信、安全、恢复和复现性方面取得更好的综合表现？当前 RQ8 是待真实模型运行补充的假设。

## 8.2 F01-F20

- F01_PC_SC_BASELINE：{'SUCCESS': 12}
- F02_ETEAC_BASELINE：{'SUCCESS': 12}
- F03_AUTO_BASELINE：{'SUCCESS': 12}
- F04_NETWORK_LATENCY：{'SUCCESS': 36}
- F05_NETWORK_JITTER：{'SUCCESS': 18}
- F06_PACKET_LOSS：{'SUCCESS': 36}
- F07_CLOUD_INTERRUPTION：{'SUCCESS': 18}
- F08_TARGET_MOVEMENT：{'SUCCESS': 36}
- F09_OBSTACLE_CHANGE：{'SUCCESS': 36}
- F10_LOCAL_RECOVERY：{'SUCCESS': 12}
- F11_LOCAL_REPLANNING：{'FAILED': 18, 'SUCCESS': 18}
- F12_SAFETY_REJECTION：{'BLOCKED_BY_ENV': 36, 'SAFETY_STOPPED': 36}
- F13_SKILL_CACHE：{'SUCCESS': 24}
- F14_AUTO_POLICY：{'SUCCESS': 18}
- F15_MUJOCO_ISAAC_PAIRED：{'BLOCKED_BY_ENV': 18, 'SAFETY_STOPPED': 6, 'SUCCESS': 12}
- F16_PLANNER_PROVIDER_COMPARISON：{'BLOCKED_BY_ENV': 20, 'SUCCESS': 16}
- F17_ABLATION_RECOVERY：{'SUCCESS': 12}
- F18_ABLATION_REPLANNING：{'FAILED': 12, 'SUCCESS': 12}
- F19_ABLATION_SAFETY：{'FAILED': 18, 'SAFETY_STOPPED': 18}
- F20_STRESS_AND_RECOVERY：{'SUCCESS': 18}

## 8.3 LLM-Only 补充实验 B01-B03

- B01_LLM_ONLY_ONESHOT：一次模型调用生成完整 TaskContract，异常时失败或整体重试。
- B02_LLM_ONLY_REACTIVE：每一步或异常后调用模型生成下一动作，仍经过契约校验和 SafetyShield。
- B03_PROPOSED_ARCHITECTURE_PAIRED_COMPARISON：LLM-only one-shot、reactive、PCSC、ETEAC、AUTO 在相同场景、seed、后端和安全策略下配对比较。

LLM-Only Decision Baseline 不是底层物理设备控制方案。为保证安全边界和控制变量一致性，LLM-only 基线仍使用相同 TaskContract、SafetyShield 和 HardwareExecutionGate。对照变量是智能决策机制和云边协同方式，而不是是否保留基本安全保护。

