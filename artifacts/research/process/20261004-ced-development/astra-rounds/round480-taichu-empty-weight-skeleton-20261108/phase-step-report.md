# round480-taichu-empty-weight-skeleton-20261108 步骤报告

全局 meta 设备使 timm 的 CPU torch.linspace().item() 失败。改用 accelerate.init_empty_weights(include_buffers=False) 创建骨架及替换量化层。v3 与详细补充验证通过：全部参数 meta、CPU buffer 272 bytes、248 层范围正确；详细运行 RSS 样本和 lifetime peak 独立记录，缺测字段保留 NOT_MEASURED。

证据：

- `artifacts/research/process/20261004-ced-development/astra-rounds/round478-taichu-loader-api-scope-20261108/meta-scope-verification-v3-detailed.json`，SHA256 `5861e6c9128a5f263e9122d72456804ec84d094b5b8a224136e1e4fbbb086698`。
- `artifacts/research/process/20261004-ced-development/astra-rounds/round478-taichu-loader-api-scope-20261108/meta-v3-detailed-evidence-notes.json`，SHA256 `274900df90ee051bd057978ecfdaa9be9afb8791ceef26a494fcaf02eb21890e`。

仅为限定开发验证；实际生成和质量结果单独汇总，正式研究验收未执行。
