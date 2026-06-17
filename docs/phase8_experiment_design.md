# Phase 8 实验设计

Phase 8 为 PCSC、ETEAC 和 AUTO 增加确定性、seed 可控的实验框架。AUTO 仍然只是 PCSC 与 ETEAC 之上的选择器，不是第三种执行器。

## 问题

- 在不同 network profile 下比较任务成功率、虚拟耗时、云端调用次数和通信成本。
- 比较目标移动、障碍插入、抓取失败、目标丢失、感知退化、断网、云端失败、命令乱序、cache 状态、振荡压力、急停和 SQLite 重启等场景下的故障检测与恢复。
- 检查 AUTO 是否会根据 risk、network、scene 和 cache 信号选择 PCSC 或 ETEAC。
- 度量 Skill Cache 的复用和 quarantine 行为。
- 验证同一 config 与 seed 的可复现性。

## 变量

- 自变量：scenario id、mode、seed、命名 network profile、cache policy、ablation list、supervision period 和 timeout。
- 因变量：success、completion time、retry、replan、safety decision、cloud call、bytes、mode switch、cache counter、recovery latency、invariant violation 和 reproducibility hash。
- 控制变量：mock robot 抽象、高层技能集、安全策略、task profile 和确定性虚拟时间。

## 场景

registry 包含 S01 到 S15，每个场景都有 initial condition、scheduled fault、invariant、allowed result、forbidden result 和 max virtual duration。

## 网络模型

profile 包括 GOOD、NORMAL、DEGRADED、POOR、SEVERE 和 INTERMITTENT。模拟器支持 latency、jitter、loss、duplication、reordering、outage、cloud availability 和 byte accounting。所有随机选择都使用实验 seed。

## 消融

A1-A7 会记录在 config/result metadata 中。safety ablation 只作为 shadow-only 指标；正式执行永远不能绕过 `SafetyShield`。
