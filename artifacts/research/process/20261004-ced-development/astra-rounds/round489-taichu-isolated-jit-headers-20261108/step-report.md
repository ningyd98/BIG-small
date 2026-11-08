# R489 步骤报告

实际 Astra 规划后，按本机 apt 缓存固定的同版本 metadata，经严格 enp7s0/AliDNS/TLS 通道取得 libpython3.12-dev 3.12.3-1ubuntu0.17，5,683,746 字节及预期 SHA256 一致。仅解压至 ignored cache，不安装系统包、不执行包脚本、不使用静态库。子进程 CPATH 仅引用匹配头文件。

A 结束释放 GPU 后，真实 Triton target=cuda/89、66 multiprocessors、101376 shared memory；FLA hardware 明确为 CUDA，4096 元素 Triton 数值与 CPU 精确一致，stderr 无原 Python.h 或 CPU fallback 错误。driver/JIT/processor 前置共 10.907 秒，成本已独立记录。

B 一次加载完成既定 8 次请求，实际两个 GDN 路径调用非零；生成期间新增 chunk/fused_recurrent gated_delta CUDA 编译元数据可核对。causal-conv 仍 fallback。warm 开启 34.299 秒、关闭 12.169 秒；第一模型请求 58.166 秒包含模型内核编译，且已在 driver 预检之后，不能称全冷启动。

两组严格 JSON 与完整质量均 0/4，关闭输出均 176 token 且带 Markdown 围栏，坐标不可评分。相对基础关闭思考的 13.3% 观察耗时下降包含输出长度/内容变化，不能全归因于内核。正式研究验收未执行。
