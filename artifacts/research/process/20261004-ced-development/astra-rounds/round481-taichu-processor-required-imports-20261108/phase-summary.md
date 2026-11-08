# R481 步骤报告

新增 requests 2.34.2、certifi、charset-normalizer、urllib3 四个缺少的依赖，原64版本保持；干净B pip check与完整实际双图processor通过。随后一次新load及四次真实生成完成，248FP8保留，原BF16层正确，全部GPU，无offload或OOM。四次均到512 token上限且响应相同，质量不由生成完成替代。

实际生成四次、进程退出码0；真实执行时间08:31:30–08:33:52 UTC。GPU compute 清单结束后为空。

证据：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round481-taichu-processor-required-imports-20261108/dependency-verification.json`，SHA256 `17c34bc6a2c23c40f9d0506def31eac2bf9a5a4f19981b6937235a3e033ebbe0`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round481-taichu-processor-required-imports-20261108/pre-run-verification.json`，SHA256 `bd59eb90adbe051513800ca72d2844f2fa2c16d5d4dbfa35f4c0f1ffbacff412`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/processor-b-r481.json`，SHA256 `be83b6994d84831adbbffed30c945755eba43e1f338fdd848139917649996dc9`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/steps/model-run-b-r481-result.json`，SHA256 `452309d8672d6326901011556f97f8cae71a203b395c3bd37cf5862cd9923302`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round481-taichu-processor-required-imports-20261108/actual.stdout`，SHA256 `0fa9517726a7864131aa1b3f0e357de406c88d841d12a3476efcf8e7d8974dc2`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round481-taichu-processor-required-imports-20261108/actual.stderr`，SHA256 `cc50c0b2d9e3216a80832a2c799d407c3355c4a3b5df3f46238d08265e1e86c0`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round481-taichu-processor-required-imports-20261108/gpu-cleanup.json`，SHA256 `506b617bcd81760fc4fcbb7203c0d1815b6e4f2118ab8607baddb5decfdbf2d0`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/runtime-measurements.json`，SHA256 `968c3dffb038f669fe14f0f9dabe1d72a907d5f383b24090892ed2f1ba897c4a`。

四份原始响应和权重留本地缓存，远端派生报告不是完整复现包。正式研究验收未执行。
