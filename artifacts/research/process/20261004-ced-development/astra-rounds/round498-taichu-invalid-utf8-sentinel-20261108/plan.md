# R498 — 单187屏蔽前提未成立，冻结候选负门槛

实际规划模型：gpt-6-astra；仅规划。输入bytes/SHA256和只读分类审计见 plan.json 与 diagnostic/astra-special-classification-review.json。

**不批准仅屏蔽187后进入GPU。** 原byteFF不是任何合法UTF8序列的组成字节，native将187映射为空并标special、root mask0，确实是一个精确异常；屏蔽它仍会排除部分HF lossy替换字符路径，不能冒称全部模型文本等价。更关键的是，native实际另报告额外nonEOS special。原tokenizer.json中 **248058–248069明确special=false**，native却true；只有另外部分可以解释为HF all_special_ids未列而backend标special。这直接否定“其余分类完全吻合”的必要前提。

本轮仅追加只读输入复核、逐项分类证据和步骤/阶段报告，保持原helpers、失败日志、tokenizer、72包及旧LMFE环境不变。不得实现backend_r498绕过断言、扩大屏蔽集合、重映射special、修改库或输出、换第三框架。无新安装/网络/模型运行；现有byte检查失败与special差异共同记 **NOT_QUALIFIED_TOKENIZER_SEMANTICS**。原21 fixture尚未完整通过，应记前置阻塞，不能改成通过。

实施报告前逐项复核输入SHA/bytes与来源；确认模型load/gen仍0，分别记录依赖PASS、tokenizer前置FAIL、真实生成NOT_RUN、质量/定位/正式研究NOT_ASSESSED。CPU **15:43:20 UTC**、整体 **16:19:20 UTC**不变；1load/24gen上限不代表资格已获得。独立报告和原R491显式artifact交付可继续，保留原件及三SHA核对。扩大到其他special语义适配须新Astra计划，本轮没有预授权。
