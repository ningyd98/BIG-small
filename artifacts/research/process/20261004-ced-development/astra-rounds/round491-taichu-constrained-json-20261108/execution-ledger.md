# R491执行记录

用户已授权约束生成同条件比较。预检：新overlay依赖接口供CPU gate、CPU gate供唯一GPU runner，raw与旧helpers只读复用。初始70模型分发与完整71分发含pip统计冲突由R492按身份及来源修复，不改旧环境。

- R491 FREE原capture及unrestricted测试为预期RED，围栏输出/过早EOS不受生成约束。
- R492完整原71依赖未变，精确加2轮包，实际新解释器73项闭包与pip check通过。
- 官方TF adapter发生预授权的TF5 import兼容门槛失败，原脚本/日志保留，选择原计划允许backend-agnostic路线。
- R493 guard发现原模型EOS248040不在tokenizer special IDs，按Astra新计划在TokenizerData中精确排除这一个ID；原HF EOS三项及pad/bos不改。
- 新中文合法样例在红色后被阻止，ASCII例能完成；R495等待实际Astra计划，未私自修改语言/跳过测试。
- codec软件序列化成功但launcher漏传CPATH导致Fla硬件发现fallback，原PASS仅指codec，不能用于GPU就绪；R494等待Astra计划。
- 至此模型loads=0、generation=0，原权重/产品/云边端默认未变。

原总窗口14:49:20Z到16:19:20Z；阶段预算若重新分配需明确记录Astra裁决，不能把延长写成原25min内通过。


## Final bounded outcome 2026-11-08 16:06 UTC

Byte-native final CPU PASS; Stage A one load / 8 generations completed; FREE strict0/4, JSON strict4/4, JSON spatial0/4. Stage B B_NOT_RUN_TIME (198.329<240.122 seconds), no authorization/no generations. Model exited rc0. See round497 report.md and phase-summary.md. Historical failures and old draft scripts retained unchanged.
