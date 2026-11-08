# R496 — 补足跨 byte-token 的 Unicode 标量字符域

实际规划模型：gpt-6-astra；仅规划。完整输入及 SHA256 见 plan.json，原 failure.json 四项已逐项核验。

实际诊断证实：前三合法 fixture 完成，第四在多 token 拼出 🦾 后失去字符串状态，emoji 不在 tokenizer trie 根字符构成的 alphabet 中，下一个正常标点5205被拒。尚无模型加载/生成。本轮仅允许一次配置级字符域补足；不批准非ASCII→\u转义，因为其长度、enum和跨byte增量等价性尚未建立，也不删除 emoji fixture 或换英文。

新 backend_r496.py 保留 R493 regular tuples、decoder、EOS 与 R495 构造顺序；仅将新 TokenEnforcerTokenizerData 实例的公开 tokenizer_alphabet 配置为原集合与 U+0080..U+10FFFF 全部 Unicode scalar 的并集（排除 surrogate，原ASCII域不变），JsonSchemaParser 构造使用同一集合。保留原序并按码点追加，记录集合关系/hash/大小和边界。它补足多 byte 拼成字符的输入域，不更改 token、原始文本、schema 或库实现；不得只加已知 emoji、放宽字符串长度或修改 trie。

新 CPU gate 完整重放原四合法 fixture、emoji逐token及后续标点；另验其他 supplementary 字符和组合字符、原结构/enum/maxItems负例、三EOS终态/非终态、1030前缀与请求隔离。regular tuple hash/decoder/输入/原73依赖全部不变，原数据与失败不覆盖。保存新 cpu-backend-r496 报告和最小diff；必要新runner仅切导入与唯一结果名。R494硬件PASS与同环境前置继续适用。全部原契约通过方可进原R491模型实验；若仍失败，记录 UNICODE_TOKENIZER_INCOMPATIBLE，不另试转义/框架或把核心约束失败交给末端校验掩盖。

新CPU gate最多120秒，配置和测试相对同环境基线峰值RSS增量≤1GiB，记录实际成本；超限停止自有进程并判成本未合格。CPU **15:24:20 UTC**、整体 **16:19:20 UTC** 不变，最大1load/24gen不增加，无模型warmup；真实JSON臂必须计入完整callback开销及原每请求180秒限制。通过仅是软件契约，不代表JSON/定位/正式验收。旧源码、库、模型、环境均不改，交付沿用R491并显式加入本轮。
