# round482-taichu-offline-scoring-snapshot-20261108 步骤报告

以合法离线 snapshot 的 num_predict=512 表示唯一 token 上限投影，并完整独立保留 HF 配置与调用覆盖参数。一次离线评分 rc0，四次真实响应严格 JSON 全失败；无合法坐标，未测得定位像素误差。所有模型/产品/原始输出字节复核不变。

证据：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/dual-image-results-v2.json`，SHA256 `5346872d36b59703190cae0bc169eb6b9cca535d629f59590105fb673d9e5829`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round473-taichu-quantized-dual-image-20261108/hf-execution-parameters-v2.json`，SHA256 `b0d6ffe9ab20ddf938a06148243a6aa4b5dfb888f65c72101bec3439abe58b65`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round482-taichu-offline-scoring-snapshot-20261108/post-run-verification.json`，SHA256 `dd726fe465cebaee054103a85734303cffe9a9869ad56ed4b06dc3a134d50a0c`。
