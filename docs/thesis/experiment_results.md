# 实验结果

实验结果由 `scripts/analyze_phase12_results.py` 和 `scripts/export_phase12_thesis_assets.py` 从 `artifacts/phase12` 自动生成。本文档不手工编造数值。

Smoke profile 只证明管线可用，不能用于最终论文结论。Validation profile 可证明 actual software runner 链路，但仍不是 full final thesis evidence。`authoritative_for_thesis=true` 只是行级 runtime-complete 标记；论文最终统计、effect size、置信区间和 LaTeX 表格必须使用 verifier-gated accepted evidence，并同时满足 full sample policy。
