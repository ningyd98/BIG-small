# Phase 12 Design

Phase 12 停止无边界功能扩展，集中做最终实验评估、论文证据整理和项目软件/仿真封板。

核心模块：

- `cloud_edge_robot_arm.final_evaluation.models`：Phase 12 结果、manifest、aggregate 和硬件声明模型。
- `cloud_edge_robot_arm.final_evaluation.registry`：F01-F20 固定实验注册表。
- `cloud_edge_robot_arm.final_evaluation.runner`：受控软件/仿真 runner，不注册真实硬件。
- `cloud_edge_robot_arm.final_evaluation.aggregation`：raw runs 聚合。
- `cloud_edge_robot_arm.final_evaluation.statistics`：CI、effect size、paired difference。
- `cloud_edge_robot_arm.final_evaluation.plots`：论文图表导出。
- `cloud_edge_robot_arm.final_evaluation.tables`：CSV/Markdown/LaTeX 表格导出。
- `cloud_edge_robot_arm.final_evaluation.report`：论文素材和答辩包导出。
- `cloud_edge_robot_arm.final_evaluation.validation`：Phase 12 smoke/validation/full 验收。
- `cloud_edge_robot_arm.final_evaluation.adapters`：Phase 12.1 actual software runner adapter allowlist，覆盖 Phase 8、MuJoCo、Isaac、Phase 10 dry-run、Phase 11 runtime 和 Phase 11.2 planner dry-run。

数据来源：

- smoke rows are `SYNTHETIC_PIPELINE_SAMPLE` and `authoritative_for_thesis=false`.
- validation rows must invoke actual software runner adapters where the environment is available.
- `BLOCKED_BY_ENV` rows are retained and counted separately.
- `authoritative_for_thesis=true` is only a row-level runtime-complete marker. Thesis statistics,
  thesis tables and thesis plots require verifier-gated accepted evidence; current Phase 12.2
  gap evidence has `verifier_gated_authoritative_thesis_run_count=0`.

安全边界：

- 不接触真实控制器。
- 不执行真实机械臂运动。
- 不调用 MoveIt execute。
- 不自动下载大型模型。
- 不把 smoke、validation 或 `BLOCKED_BY_ENV` 写成 full final accepted。
