# Phase 8.1 基线报告

本基线总结 Phase 8.1 runtime-harness 实验运行。仓库只保存小体积可复现 artifact，原始 `raw_runs.jsonl` 和 `events.jsonl` 文件有意不纳入版本控制。

## 已执行套件

| 套件 | 运行次数 | 成功任务数 | 成功率 |
| --- | ---: | ---: | ---: |
| smoke | 45 | 33 | 0.733333 |
| validation | 675 | 495 | 0.733333 |
| full | 2250 | 1650 | 0.733333 |

## Full Benchmark 范围

- 场景：S01-S15
- 模式：PCSC、ETEAC、AUTO
- 网络：GOOD、NORMAL、DEGRADED、POOR、SEVERE
- Seed：0 到 9
- 总运行次数：2250

## 证据边界

Phase 8.1 通过 `RuntimeExperimentHarness` 驱动接近生产形态的 mock runtime chain：contract validation、`SafetyShield`、`TaskExecutor`、`MockRobotAdapter`、command ACK classification、PCSC supervision、ETEAC replan/CAS path、mode transition lifecycle 和 restart recovery。指标来自结构化 runtime event 和 repository。

这些仍是 Mock/仿真实验，不代表真实机械臂性能、真实相机性能、ROS 2/MoveIt 2 集成或生产 LLM 行为。仿真零碰撞不能证明物理硬件安全。硬件验证仍然需要 Phase 9 及后续流程。
