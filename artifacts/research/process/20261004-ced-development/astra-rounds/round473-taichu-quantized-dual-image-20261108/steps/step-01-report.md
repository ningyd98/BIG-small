# 阶段 01：来源、小文件及权重

PASS。固定官方 revision、上游大小及 SHA；17 小文件和12.67GB权重最终复核匹配。

命令入口：`download_candidate.py sources / weights`。时间未单独测量处明确标为 NOT_SEPARATELY_RECORDED，不由文件时间伪造运行时钟。

证据：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/step-01-sources.json`，SHA256 `810a36d28b30284be0041ec9e575b72c3aca8a4871e6846bbce7472a30b9361a`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/step-03-weights.json`，SHA256 `73a3585d8cafede1d68d99f9ec8f00ecd9cc61e3ad2e2c1576c7749a8bab7dd2`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/final-byte-verification.json`，SHA256 `f416ae9dd3026d786f197ea90080adf64af3be9999291741087a3a50bcf63b68`。
