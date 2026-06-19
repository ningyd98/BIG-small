# Phase 12 Statistical Method

Phase 12 统计分析遵循以下规则：

1. 描述统计同时报告 count、mean、median、standard deviation、min/max、P25/P75、P95。
2. 连续指标报告 95% confidence interval。
3. 成功率使用 Wilson confidence interval。
4. 配对实验优先使用 paired difference。
5. 不满足正态假设或样本量较小时，结论以非参数趋势和 effect size 为主。
6. 多组比较需要控制多重检验，不能只报告单个 p-value。
7. 每个结论必须同时报告样本量、effect size 和置信区间。
8. `FAILED`、`TIMEOUT`、`SAFETY_STOPPED` 和 `BLOCKED_BY_ENV` 不得静默删除。
9. 环境阻塞单独统计，不计为算法失败，也不能计为通过。
10. seed 必须按配置完整运行，不能挑选对结论有利的 seed。

Smoke profile 只验证管线和 artifact 结构，不能生成最终论文统计结论。Full profile 才可用于最终结论。
