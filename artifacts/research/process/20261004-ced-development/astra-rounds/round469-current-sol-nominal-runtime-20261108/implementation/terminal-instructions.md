# R469 本地隐藏输入与真实 API 运行

当前状态：`READY_WAITING_HIDDEN_TTY_SECRET`。唯一 CPU 预检已通过，退出码0、外层耗时0.328秒；API/render/physics均0。现在可以执行下方真实运行命令。

用户已授权真实运行，不需要再次确认权限。当前缺少可供本轮运行进程使用的会话密钥。请只在本地终端的隐藏提示中输入密钥，勿发到聊天、环境变量、文件或命令参数。历史 R460 的 session-only 密钥不会自动转移。

## 真实运行

在仓库根目录执行以下命令；等待输入不占 GPU 锁或启动运行计时。

```bash
cd /home/ningyd/文档/ChatGPT/BIGsmall
env MUJOCO_GL=egl PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round469-current-sol-nominal-runtime-20261108/implementation/run_nominal.py --execute
```

出现 `OpenAI API key (hidden; memory only; never paste in chat):` 后输入并回车。

运行只使用精确 `gpt-6.1-sol`、新 v2 基础场景、320×240 RGB-D；最多 first1+warm3 四次串行请求，任何失败立即停止，不自动重试。真实运行仍需当时的源码与 GPU/服务/磁盘准入通过。

完成后告诉本聊天“终端已完成”，由 ROOT 核对收据并执行唯一独立 reader。若终端显示失败，请保留原始输出，无需重复运行。

完整 raw 只留本地 `cache/research/r469-current-sol-nominal-20261108`。这轮 nominal 不代表物理、edge、full-H 或正式研究验收。
