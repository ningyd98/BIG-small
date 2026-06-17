# Phase 8.1 报告

Phase 8.1 用运行时框架替换了剩余的合成实验行为，让实验驱动真正的 Phase 3-7 链路。

## 已实现

- 通过 `TaskExecutor` 提交真实契约。
- 通过 `SafetyShield` 执行真实安全检查。
- 真实命令入口和 ACK 分类。
- 真实 PCSC 监督 tick。
- 真实 ETEAC 重试预算、失败摘要、重规划和 CAS 路径。
- 真实 AUTO prepare/commit/abort 切换。
- SQLite 对 prepared state、checkpoint 和 outbox 的重启恢复。
- 从正式记录里采集事件驱动的指标。

## 运行摘要

- Smoke：45 / 33
- Validation：675 / 495
- Full：2250 / 1650

## 生成的基线

- `experiments/baselines/phase8_1/run_manifest.json`
- `experiments/baselines/phase8_1/summary.json`
- `experiments/baselines/phase8_1/summary.csv`
- `experiments/baselines/phase8_1/report.md`
- `experiments/baselines/phase8_1/result_hashes.txt`

## 限制

- 这仍是一组 mock/simulation 实验。
- 没有使用真实机械臂、真实相机、ROS 2、MoveIt 2 或生产 LLM。
- 模拟零碰撞结果不能当成硬件安全证明。
- 真实硬件验证仍然需要 Phase 9。
