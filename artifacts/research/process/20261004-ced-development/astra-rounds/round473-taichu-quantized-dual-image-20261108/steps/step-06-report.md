# 阶段 06：严格评分

EXPECTED_QUALITY_NEGATIVE。四次strictJSON全部失败；无合法坐标，不把false hit计成实测错位。R482仅离线snapshot元数据投影，真实HF参数另存。

命令入口：`evaluate_pair_v2.py explicit R481 result and v2 output`。时间未单独测量处明确标为 NOT_SEPARATELY_RECORDED，不由文件时间伪造运行时钟。

证据：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/dual-image-results-v2.json`，SHA256 `5346872d36b59703190cae0bc169eb6b9cca535d629f59590105fb673d9e5829`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/hf-execution-parameters-v2.json`，SHA256 `b0d6ffe9ab20ddf938a06148243a6aa4b5dfb888f65c72101bec3439abe58b65`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round482-taichu-offline-scoring-snapshot-20261108/post-run-verification.json`，SHA256 `dd726fe465cebaee054103a85734303cffe9a9869ad56ed4b06dc3a134d50a0c`。
