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

安全边界：

- 不接触真实控制器。
- 不执行真实机械臂运动。
- 不调用 MoveIt execute。
- 不自动下载大型模型。
- 不把 smoke 或 `BLOCKED_BY_ENV` 写成 final accepted。
