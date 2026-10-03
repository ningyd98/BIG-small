# T3 本地 RGB-D 模型探测（2026-10-03）

状态：**BLOCKED，未生成 `model-frozen.json`**。本机 `qwen3.5:4b` 能在 RTX 4070 Ti SUPER 上接收同一 MuJoCo 观测的 RGB 与深度可视化两图，并返回可严格解析的 JSON；但模型给出的目标与目的像素没有落在相应可见表面上，不能作为已验证空间规划模型冻结。

正式候选配置见 `configs/research/model_candidate.yaml`。Ollama 版本 0.35.1；本机模型 digest `45767c5edcbd36f617dd77cb32d0bd4bf72fb6f027314db26596b2065909444c`，量化 `Q4_K_M`，均与候选一致；`/api/show` 广告 `vision`。固定分辨率 320×240，temperature 0、num_ctx 8192、num_predict 512、think=false。推理非流式，TTFT 为 `NOT_MEASURED`。

最后一次正式运行的原始证据见 `probe-report.json`，每次同步帧见 `captures/attempt-01` 至 `attempt-04`。4/4 次 `/api/chat` 请求各含两张不同图，4/4 次输出可解析且可反投影；0/4 次红方块像素命中 `object_geom`，0/4 次绿色目标像素命中 `target_region_geom`。独立实例图只在响应后用于核验，未传给模型。320×240 首帧中红方块可见 bbox `[172,113,185,126]`（196 像素），绿色目标区 `[118,59,146,88]`（870 像素）。

冷启动墙钟 4401.032 ms；热启动 3 次为 1246.067、1272.392、1256.533 ms，p50 1256.533 ms，p95 1270.806 ms（仅 3 个热样本，不代表总体服务时延）。Ollama `/api/ps` 报 `size_vram=3436267437` 字节；`nvidia-smi` 记录推理期间整卡显存峰值 4684 MiB，推理后 compute PID 947468 占 4200 MiB。首轮前已卸载模型，卸载后整卡使用 311 MiB。

有限诊断：`diagnostic-rgb-first.json` 只加强“按第一张 RGB 的颜色定位”的自然语言指令，仍错落桌面。`diagnostic-640.json` 使用一次原生 640×480 同步双图，保持相同模型和生成参数；红方块离线 bbox `[344,226,371,253]`（782 像素），绿色区域 `[235,118,293,176]`（3481 像素），模型给出 `[408,232]` 与 `[368,272]`，仍均命中桌面。该次原始 RGB/深度和离线实例图在 `captures/attempt-64/`，完整实际请求在 `diagnostic-640-request.json`，原始响应与显存峰值 4694 MiB 在 `diagnostic-640.json`。640×480 是诊断，不更改正式 320×240 门槛，也不产生冻结配置。

自动化回归：`.venv/bin/python -m pytest -q tests/test_rgbd_model_probe.py` 5 passed；Ruff 和 `MYPYPATH=src .venv/bin/python -m mypy scripts/probe_rgbd_model.py` 通过。冻结写入器不会覆盖既有文件；再次探测仅在先前 PASS 报告及 SHA 证明同目录旧冻结文件归属于本脚本时归档它。正式脚本因像素定位不合格返回退出码 1。下步需提升视觉定位能力后用同一离线命中门槛复测，当前不把可解析 JSON 或 GPU 运行当作几何有效结果。
