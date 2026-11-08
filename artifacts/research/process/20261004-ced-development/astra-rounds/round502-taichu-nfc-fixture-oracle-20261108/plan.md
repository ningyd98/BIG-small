# R502 — NFC 编码与原始字节测试分开验证

实际规划模型：gpt-6-astra；仅规划。输入SHA/bytes见plan.json。

批准仅CPU测试oracle修正，不改adapter。实际NFC witness证实6项native字节均等于HF canonical decode，4/5的组合字符由原tokenizer NFC规范化；6项单byte IDs又均能还原原字节。旧断言把HFencode当作无损原文本encode，因此失败；此roundtrip尚不替代完整matcher测试。原R500四合法及EOS抑制通过证据保持。

新cpu_contract_r502.py分别记录原文本/UTF8 hash、canonical IDs/HF decode/nativebytes及NFC差异。canonical路径应比native与实际HFdecode，保留canonical token IDs一致门槛；新增仅CPU用的真实ByteLevel单byte词表ID回放，逐项证明没有D/EOS、native/HF decode精确等于原始fixture。真实生成不使用该编码器、不强制分词、不改原fixture。

6合法必须canonical与原byte两流完整通过；原11非法+4值边界必须按原byte流及原严格schema拒绝，canonical路径若因NFC变化须按实际decode文本独立判定和披露。27ASCII见证、全词表/D28/187例外、3EOS、1030prefix/视觉、状态隔离及原72包门槛全部保持，adapter SHA不变。新唯一报告不覆盖旧失败。native≠HF或原byte matcher失败/未知差异则最终负结果，不再修。

新CPUgate≤120秒，仅从原A余量再拨最多3分钟至 **15:51:20 UTC**；原总 **16:19:20**、A16:00/B16:04:20、1load24gen均不变。CPU全部PASS并满足原codec/环境/GPU门槛后才准A八次，B仍等真实格式4/4与专项计划。无模型warmup，本轮通过不等于真实质量或正式验收；交付沿用原R491，保留所有原件及NFC区别。
