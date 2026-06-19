# Phase 12 Report

Phase 12 新增最终实验评估框架、F01-F20 注册表、统计分析、图表导出、论文表格、论文素材和答辩包。

当前 baseline `7b4c9af` 的 smoke profile 生成 90 条 `SYNTHETIC_PIPELINE_SAMPLE`，用于验证管线和安全边界，不是 Phase 8、MuJoCo、Isaac、MoveIt 或 Simulation Runtime 的真实运行结果。Phase 12.1 validation 接入 actual software runners，生成 validation 级 evidence。Phase 12.2 对该 evidence 重新核验后发现 provenance 记录 `worktree_clean=false`，当前权威状态为 `PHASE12_VALIDATION_PIPELINE_ACCEPTED_WITH_RUNTIME_EVIDENCE_GAPS` 和 `THESIS_PACKAGE_INCOMPLETE`，不能声明 validation accepted。Full profile 需要额外资源和完整多 seed 运行，不能由 smoke 或 validation 结果替代。

硬件边界保持：

- `real_controller_contacted=false`
- `hardware_motion_observed=false`
- `hardware_write_operations=[]`
- `highest_real_hardware_acceptance_level=NONE`

真实机械臂验证仍为 `NOT_STARTED`。
