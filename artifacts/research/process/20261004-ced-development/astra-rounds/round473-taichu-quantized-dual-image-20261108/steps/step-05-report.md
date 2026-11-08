# 阶段 05：四次真实生成

PASS。一次新load，四次固定同帧生成；均512tokens，248FP8保留，无OOM。

命令入口：`run_fp8_pair_r481.py four requests`。时间未单独测量处明确标为 NOT_SEPARATELY_RECORDED，不由文件时间伪造运行时钟。

证据：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/runtime-measurements.json`，SHA256 `968c3dffb038f669fe14f0f9dabe1d72a907d5f383b24090892ed2f1ba897c4a`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/model-run-b-r481-result.json`，SHA256 `452309d8672d6326901011556f97f8cae71a203b395c3bd37cf5862cd9923302`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round481-taichu-processor-required-imports-20261108/actual.stdout`，SHA256 `0fa9517726a7864131aa1b3f0e357de406c88d841d12a3476efcf8e7d8974dc2`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round481-taichu-processor-required-imports-20261108/actual.stderr`，SHA256 `cc50c0b2d9e3216a80832a2c799d407c3355c4a3b5df3f46238d08265e1e86c0`。
