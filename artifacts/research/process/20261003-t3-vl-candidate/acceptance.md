# T3 候选 Qwen3-VL-4B-Instruct 实测记录

状态：**BLOCKED**。2026-10-03 从魔搭 Qwen 官方仓库经 `enp7s0` 物理网卡直连下载两个固定 GGUF，校验 SHA-256 后，以独立名称 `qwen3-vl-candidate:4b-instruct` 导入本机 Ollama 0.35.1。原 `qwen3.5:4b` 未覆盖。本轮按原 `scripts/probe_rgbd_model.py` 的 320×240、seed 0、同一指令和生成参数运行 1 次冷启动与 3 次热运行。双图请求、视觉模型调用和 CUDA 均实际执行，但目标与放置像素各 0/4 命中；未生成 `model-frozen.json`，不得将该候选宣称为已通过 T3。

| 文件 | 大小（字节） | SHA-256 |
|---|---:|---|
| `Qwen3VL-4B-Instruct-Q4_K_M.gguf` | 2,497,281,664 | `66358cb18bb6b3b1b6675aa412c7a88ef01d228f481184d13668e5201c730a0a` |
| `mmproj-Qwen3VL-4B-Instruct-F16.gguf` | 836,180,256 | `256f3a43bd4205ffef48d6b92715e1e70b5b0e9aef06522584967513a9985331` |

来源是[魔搭 Qwen 官方仓库](https://modelscope.cn/models/Qwen/Qwen3-VL-4B-Instruct-GGUF)，固定 revision `625828cbd3489786522366e19e22b6f12278e41a`。两份文件共 3,333,461,920 字节，存于被 `.gitignore` 排除的 `datasets/model-cache/qwen3-vl-4b-instruct/`；完整下载明细见 [downloads.json](downloads.json)。下载脚本使用仓库已有的 `create_direct_transport`，DNS 与 TCP 绑定 `enp7s0`，只允许 `modelscope.cn` 及 `cdn-lfs-cn-1.modelscope.cn`，忽略代理环境；HEAD 的 `x-linked-etag` 与上游 SHA 一致，实际 GET 的终点为魔搭 CDN。套接字抽样在 [download-sockets.txt](download-sockets.txt)：`192.168.3.221%enp7s0 → 119.249.48.43:443`。没有执行 `ollama pull`。

Ollama 新模型 digest 为 `d18dda6d10491bbe92186dbc7c854623bf99f48eb75829dbe290ef0f97626107`；`/api/show` 报告 `completion`、`vision`、`tools`，量化为 Q4_K_M。[导入请求](create-request.json)、[模型元数据](model-entry.json)和[原始探针报告](probe/probe-report.json)可复核。此次运行的模型驻留大小约 4.24 GB，`size_vram` 同值；GPU 峰值使用 5,741 MiB。探针结束后已显式停止该候选，`/api/ps` 为空。

四次 `/api/chat` 均收到 HTTP 200，且每次请求均有两幅不同的 RGB 与深度可视化图片；输出均可按 JSON 语法解码。模型每次只给出 `MOVE_ABOVE → APPROACH → GRASP → LIFT → MOVE_TO_REGION → PLACE → RELEASE`，缺完整技能契约所需尾部动作，因而全部 `strict parsed=false`；首轮明确记下技能顺序不完整，另外三轮虽 `parse_error=None`，也没有形成可执行 `observed_scene`。这不是 JSON 语法错误。

| 轮次 | 目标像素 | 放置像素 | 离线实例检查 | 深度 | 墙钟耗时 |
|---|---|---|---|---|---:|
| cold 1 | `[157,209]` | `[157,209]` | 两点均为机器人 `link5` | 均 0.933 m | 9,027.598 ms |
| warm 2 | `[150,238]` | `[139,238]` | 两点均为无实例背景 | 均 0 m | 1,956.227 ms |
| warm 3 | `[150,228]` | `[137,228]` | 两点均为无实例背景 | 均 0 m | 2,212.205 ms |
| warm 4 | `[158,30]` | `[158,30]` | 两点均为无实例背景 | 均 0 m | 2,103.197 ms |

热运行均值 2,090.543 ms，P50 2,103.197 ms，P95 2,201.304 ms。目标和放置区域各 0/4 命中，且第 2–4 轮深度无效，拒绝调度是正确结果。旧 qwen3.5 探针也 0/4 命中，另有真实 640×480 及 RGB-first 诊断均失败；更换这个候选没有解阻像素定位。

无额外下载的 RGB-D 颜色/几何 ROI 可作为单独 **HYBRID 辅助方案**：仅从 RGB 按指令颜色形成连通区域，再在原始米制深度中检查其中心和有效深度，模型负责语义或技能。现有同一静态场景中，RGB 独立阈值得到红色区域 195 像素、中位点 `[179,120]`，绿色区域 870 像素、中位点 `[132,73]`；用实例图在候选生成之后离线核对分别落在 `object_geom` 和 `target_region_geom`。四轮 RGB 完全相同，这只能证明该场景的可行性。若采用，必须冻结阈值和歧义拒绝规则，跨场景盲测并单独标 HYBRID；不得据此将当前 VLM 像素定位记为通过。

复现时运行 `download.py`、`import_model.py`，然后以 [model_candidate.yaml](model_candidate.yaml) 调用 `scripts/probe_rgbd_model.py --config ... --output ...`。导入脚本遇到同名模型会拒绝覆盖；若已经导入，应直接运行探针或人工核对模型 digest。

来源与兼容性边界：[Qwen 官方 GGUF 卡](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF)称分离的语言权重与视觉投影可用于 Ollama；[Ollama 官方 Qwen3-VL 页面](https://ollama.com/library/qwen3-vl:4b-instruct)列出视觉能力和 0.12.7 最低版本。但 Ollama 既往[分离 GGUF 推理失败报告](https://github.com/ollama/ollama/issues/13480)说明注册成功不能替代实际图像推理。本次 v0.35.1 未崩溃，仍未通过任务定位门槛。
