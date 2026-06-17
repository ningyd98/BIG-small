# Phase 8.2 报告

## 范围

Phase 8.2 仍处在虚拟时钟和 mock 实验环境内，不包含 ROS 2、MoveIt 2、真实传感器或真实机械臂硬件。

## 实现概要

- PCSC supervision 改为按虚拟时钟周期运行。
- PCSC tick 会与原子任务步骤交错执行，并观察动态场景和网络状态。
- 故障注入不再直接记录检测结果。
- 故障检测延迟由真实检测事件计算。
- AUTO mode transition 先 prepare/defer，只能在步骤安全边界后 commit。
- S15 restart recovery 覆盖 9 个崩溃点。
- 实验 summary 增加 mode、network、scenario 和 seed sensitivity 视图。

## 数据

Phase 8.2 基线 artifact 写入 `experiments/baselines/phase8_2/`。

已执行套件：

- Smoke：45 次运行，33 个任务成功。
- Validation：675 次运行，495 个任务成功。
- Full benchmark：2250 次运行，1650 个任务成功。

阅读报告时使用：

- `summary.csv`：逐 run 指标。
- `summary.json`：分组指标和 validity guard。
- `report.md`：生成的实验说明。
- `events.jsonl`：tick、detection、recovery、transition 和 crash-point 时间线。

## 时序证据

代表性的 PCSC target-moved run：

- 步骤开始：`step-home` 在 0 ms，`step-move-above` 在 100 ms，`step-approach` 在 200 ms，`step-grasp` 在 300 ms，`step-lift` 在 400 ms，`step-move-region` 在 500 ms。
- PCSC tick：301 ms、601 ms、901 ms。
- 故障注入：`TARGET_MOVED` 在 700 ms。
- 故障检测：`PeriodicSupervisorService` 在 901 ms 检测到 `TARGET_MOVED`。
- 检测延迟：201 ms。

S15 recovery 覆盖全部 9 个崩溃点，最终状态为 `SUCCESS`；已完成步骤重复执行计数为 0。

## Full Benchmark 敏感性

按 mode 统计的平均云端调用次数：

- AUTO：0.0
- ETEAC：0.0667
- PCSC：2.8667

按 network 统计的平均完成时间：

- GOOD：1539.4 ms
- NORMAL：1576.96 ms
- DEGRADED：1649.18 ms
- POOR：1733.64 ms
- SEVERE：1889.2 ms

full aggregate 中，seed variability 没有改变平均完成时间，但改变了网络敏感指标。不同 seed 下平均通信字节数范围为 143.90 到 195.38，平均恢复延迟范围为 605.98 ms 到 657.03 ms。

full benchmark 的 `validity_guard` 全部通过：mode、network 和 seed 不完全相同；fault detection latency 不是全零；PCSC 包含多 tick 任务。

## 已支持的判断

- PCSC 动态 supervision 会产生多次 tick，并能观察注入后的场景状态。
- PCSC 与 ETEAC 的云端调用机制不同。
- network profile 会影响 completion、recovery 和 communication 指标。
- 不同 seed 会在网络敏感指标上产生可复现差异。
- 多崩溃点 restart recovery 可以在不重复已完成步骤的情况下到达合法终态。

## 尚不支持的判断

- 本 benchmark 中聚合完成时间没有随 seed 变化；seed 影响主要体现在通信和恢复指标。
- Phase 8.2 数据不支持任何真实硬件安全或性能结论。
