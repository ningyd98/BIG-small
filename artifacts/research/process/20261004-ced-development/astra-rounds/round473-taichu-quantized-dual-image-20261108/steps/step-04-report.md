# 阶段 04：加载与量化范围

PASS_WITH_IN_MEMORY_ADAPTER。原loader API/匹配失败保留；Astra R478-R480限定适配，248FP8，全GPU、无missing/mismatch/error、BF16层不误替换。

命令入口：`run_fp8_pair_r481.py load`。时间未单独测量处明确标为 NOT_SEPARATELY_RECORDED，不由文件时间伪造运行时钟。

证据：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round478-taichu-loader-api-scope-20261108/meta-scope-verification-v3-detailed.json`，SHA256 `5861e6c9128a5f263e9122d72456804ec84d094b5b8a224136e1e4fbbb086698`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/model-run-b-r481-result.json`，SHA256 `452309d8672d6326901011556f97f8cae71a203b395c3bd37cf5862cd9923302`。
