# R370 执行结果（2026-11-01）

用户授权修复问题1（UTC helper）。19/19 原输入 hash/bytes 匹配；保持现有工作区和全部旧证据。唯一源码新增 `request_id="external-utc-contract"`，18个其余输入不变；新runner仅调整轮号、路径、plan pin和单GREEN路由，12个核心定义AST经标签归一后相同。

单次短合同已执行：1 test / 1 failure / 0 error / 0 skip；pytest 0.781秒，wrapper 0.986176秒；child exit1，无超时、输出截断或缺失，源前后相同。旧字段构造错误已越过，真实失败为 `_b_t3_external_utc` 的 `(reason is None) is valid`，实际 `None` 对应预期 `False`。原JUnit没有显示具体循环offset，不能仅据输出断言落在何项。

该slot已SPENT，不重试。完整UTC、性能和正式研究未验收。新边界根因交实际Astra R371；不通过改变断言或扩大时效阈值修复。原失败见 implementation/external_utc_green_01/；工具回执见 implementation/transport-result.json。
