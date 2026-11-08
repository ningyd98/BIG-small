# ZDTaichu5.0-9B-FP8 兼容性和双图实测

官方 FP8 在本机 RTX 4070 Ti SUPER 16GB 上经限定的内存兼容适配后，可完成真实双图生成。四次运行均完成，248 个量化层保持 FP8、全 GPU、无 offload 或 OOM。固定 S01 的有效决策为 0/4：四份响应相同，含思考过程，并在 512-token 上限处截断，未形成严格 JSON。因此尚不能接入当前决策链，也无法据此判断其空间定位能力优于其他候选。

| 项目 | 实测结果 |
|---|---|
| 权重 | 官方 FP8，12,672,885,688 bytes，SHA256 `c2b70d4aeaa499e4bc4a267332b0338cdfca685de448338ea5014fc3eaf0a07a` |
| 运行环境 | Torch 2.10.0+cu128 / Transformers 5.22.2 / compressed-tensors 0.20.1 |
| 双图输入 | 320×240 RGB + 对齐深度可视化；两条独立图像输入，processor 输出 `[2,3,512,512]` BF16，1,028 input tokens |
| 量化 | 248 个真实 FP8 层，四次生成后均保留；官方 BF16 ViTPatchLinear 保持原状 |
| 加载时间 | 1.837 秒，仅 from_pretrained 区间，缓存已使用，非整机冷启动 |
| 首次生成 | 34.809 秒，修正 reload 后的首次请求 |
| 热生成 | 33.944, 33.920, 34.063 秒；均值 33.976 秒 |
| Torch 显存峰值 | allocated 12.389 GiB；reserved 12.746 GiB |
| 整卡采样峰值 | 14096 MiB / 13.766 GiB，含桌面，200ms 采样 |
| 决策质量 | 严格 JSON 0/4；无合法坐标，不能把 hit=false 解释成测得错误像素 |

| 次数 | 请求 | 生成秒数 | 输出 tokens | 严格 JSON |
|---|---|---:|---:|---|
| 1 | first-inference-after-corrected-reload | 34.809 | 512 | 失败 |
| 2 | warm1 | 33.944 | 512 | 失败 |
| 3 | warm2 | 33.920 | 512 | 失败 |
| 4 | warm3 | 34.063 | 512 | 失败 |

原样 loader 存在 ignore metadata 的 list/set API 差异，并把非量化 ViTPatchLinear 误匹配成量化层。本轮仅在 artifact 中保留相同 ignore patterns 并转换集合、按 checkpoint 中 248 个 FP8+scale 名称限定目标；官方源码、config 和权重字节未改。attention 明确为 SDPA；依赖环境独立，部分算子使用官方 PyTorch 慢路径。未做内核 profiling 或性能对照，不宣称 FP8 加速倍率。

实际生成参数为 do_sample=false、max_new_tokens=512、num_beams=1、use_cache=true、return_dict_in_generate=false、output_scores=false。官方模板以 `<think>` 开始。运行原始配置和覆盖参数保存在 `hf-execution-parameters-v2.json`；离线评分的 snapshot 只是合法身份/坐标适配，不能当成实际 HF 配置。未剥离思考、补全 JSON 或修改四份原始回答。

本轮只有一个 MuJoCo 静态场景的四次重复，不是四个独立场景；深度是否被因果利用未测，TTFT 未测，三次热样本不估稳定 p95。开发验证与本机实际生成已完成；实机机器人、跨场景泛化和正式研究验收未执行。生产模型未切换。

权重、wheel、venv 和完整 raw 保留在本地 `datasets/model-cache/zdtaichu5-9b-fp8-round473`；Git 中的计划、脚本、清单和派生摘要不是完整远端复现包。后续若调整思考/输出策略，应单独预注册，再做跨场景对比。

详见 `compatibility-report.json`、`dual-image-results-v2.json`、`runtime-measurements.json` 和 `evidence-manifest.json`。历史失败及逐轮 Astra 计划均保留。

交付检查：完整 `git diff --check` 因13个精确列出的冻结证据原件/原始检查输出保留空白而不通过（原rc2已留存）；这些原字节不修改，其余交付路径按默认规则单独检查。详见 R484 计划与交付记录。
