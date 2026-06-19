# 实验设计

Phase 12 冻结 RQ1-RQ7 和 F01-F20。实验分为 smoke、validation 和 full 三种 profile：

- smoke：验证管线、artifact、图表、表格和安全边界；所有样本标记为 `SYNTHETIC_PIPELINE_SAMPLE`。
- validation：至少 3 seeds 和 2 repetitions，调用 actual software runners，验证 evidence authority、source artifact hash 和聚合稳定性。
- full：满足分类型 sample policy 后，才用于论文最终统计结论。

所有实验均保持软件/仿真边界，不接触真实控制器。
