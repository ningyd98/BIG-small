# Phase 9 指标

Phase 9 增加了物理执行、感知、仿真性能和云边恢复相关指标。证据来源由 `simulation.evaluation.provenance.metric_provenance` 记录。

示例：

- `joint_tracking_rmse`：物理状态。
- `illegal_collision_count`：MuJoCo 接触。
- `sensor_latency_ms`：传感器帧。
- `fault_detection_latency_ms`：审计事件。
- `cloud_invocation_count`：网络/监督事件。

这些指标只用于仿真和准备度评估，不代表真实机械臂安全或性能结论。
