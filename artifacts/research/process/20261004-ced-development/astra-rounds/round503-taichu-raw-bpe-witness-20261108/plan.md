# R503 — 原字节 BPE 存在性见证

实际规划模型：gpt-6-astra；仅规划。输入SHA/bytes见plan.json。

实际raw-bpe见证六项全部通过完整matcher，native/HF decode精确还原原fixture、无D/EOS混入、终态三EOS可达且原tokenizer未改，故批准最后一次CPU见证编码器修正。R502单byte分词被拒属于已披露token-sequence子集，不能直接推出原字符串不可生成；具体库内部优化原因不作未经验证的结论。

新cpu_contract_r503.py仅把原字节流编码改为：从实际backend序列化建立CPU独立Tokenizer副本，normalizer=None，用原BPE merges对原fixture分词。序列化diff必须仅normalizer，其他vocab/merges/addedtokens/pretokenizer/decoder等全不变；原实例、byte_decoder_r500和生产processor都不改。逐项保存IDs并证明native/原HF decode严格还原原字节，不改fixture、不清洗、不在真实生成强制使用该分词。

canonical流继续以真实HFdecode为对照并记录NFC差异；六合法双流、原11非法/4值边界按原schema及raw-BPE流、27ASCII见证、D28/187例外、三EOS、1030prefix/视觉和状态隔离完整重放。新唯一报告不覆盖失败。不得声称任意byte或所有canonical分词均可生成；任何raw-BPE失败、字节差异、未知问题或超时即最终负结果，不再换方法。

从原A余量最后拨3分钟：CPU至 **15:54:20 UTC**，新gate≤120秒且受剩余时间限制；整体 **16:19:20**、A16:00/B16:04:20、1load24gen不变。全CPU及原codec/环境/GPU前置PASS才准原A8，无warmup；B不足则NOT_RUN。软件、真实生成、定位和正式验收分列，保留全部失败/NFC与子集说明，沿用原R491交付。
