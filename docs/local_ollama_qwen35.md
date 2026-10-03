# 本地 Ollama 与 Qwen3.5-4B

2026-10-03 已在当前 Ubuntu 主机安装并完成实际文本、图片、OpenAI 兼容接口及 CUDA 推理检查，服务重启后模型仍可用。机器为 RTX 4070 Ti SUPER 16 GB；测试时推理进程占用约 4.1 GiB 显存。

| 项目 | 当前配置 |
|---|---|
| Ollama | 0.35.1，用户目录安装，无需 sudo |
| 模型名 | `qwen3.5:4b` |
| 权重 | 魔搭 `unsloth/Qwen3.5-4B-GGUF` 的 Q4_K_M + F16 视觉投影，约 3.4 GB |
| API | `http://127.0.0.1:11434` |
| OpenAI 兼容地址 | `http://127.0.0.1:11434/v1` |
| 默认工作上下文 | 8192 tokens，单并发 |
| 云端功能 | `OLLAMA_NO_CLOUD=1` |
| 启动方式 | systemd 用户服务，登录后自动启动；`Linger=no`，不承诺未登录时启动 |

这里的 `qwen3.5:4b` 是上述魔搭 GGUF 在本机导入后的名称，并非从 Ollama 官方 registry 拉取的同名 manifest。完整模型 digest 为 `45767c5edcbd36f617dd77cb32d0bd4bf72fb6f027314db26596b2065909444c`。Ollama 正确识别 `completion`、`vision`、`thinking`、`tools` 能力；本次未单独验收工具调用。

## 使用

```bash
ollama run qwen3.5:4b
ollama list
ollama ps
```

调用本机接口，不经过代理：

```bash
curl --noproxy '*' http://127.0.0.1:11434/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen3.5:4b","stream":false,"think":false,"messages":[{"role":"user","content":"你好，请简短介绍自己。"}]}'
```

服务管理：

```bash
systemctl --user status ollama.service
systemctl --user restart ollama.service
journalctl --user -u ollama.service -n 50
ollama stop qwen3.5:4b
```

`ollama stop` 释放模型占用的显存，服务仍可接受下一次请求。默认空闲 5 分钟也会卸载模型。服务只监听回环地址。

## 安装位置与直连下载

- 程序：`~/.local/opt/ollama/0.35.1/`；命令链接：`~/.local/bin/ollama`。
- 模型：`~/.ollama/models/`。
- 用户服务：`~/.config/systemd/user/ollama.service`。
- 已校验下载缓存：`~/.cache/BIGsmall/ollama-qwen35/`。

安装包来自[魔搭 Ollama 镜像](https://modelscope.cn/models/Lixiang/ollama-release)，固定 revision `3bc525537000ecb80ffadc9fdef4566e95385181`；SHA-256 与[官方 v0.35.1 发布](https://github.com/ollama/ollama/releases/tag/v0.35.1)提供的安装包摘要一致。模型来自[魔搭 Unsloth 仓库](https://modelscope.cn/models/unsloth/Qwen3.5-4B-GGUF)，固定 revision `167b4afc359863325cb4164418c715421b4e9118`，两个 GGUF 均与上游 SHA-256 一致。

安装包和模型共下载 4,853,020,465 字节，均由 `modelscope.cn` 跳转到 `cdn-lfs-cn-1.modelscope.cn`。下载器使用仓库已有严格直连传输：DNS 和 TCP 绑定 `enp7s0`，显式 AliDNS，忽略代理变量，保留 TLS 校验，不允许系统网络回退。实际下载连接记录显示 `192.168.3.221%enp7s0 → 60.221.22.27:443`，见[套接字证据](../artifacts/research/process/20261003-ollama-qwen35/download-sockets.txt)。官方版本元数据也通过物理接口直连查询，未通过隧道。部署过程没有执行 `ollama pull`。

以后下载新模型仍应使用此直连流程；普通 `ollama pull` 不继承下载脚本的物理接口绑定。

## 复现与验收

从仓库根目录运行，首次安装流程如下；安装脚本遇到已注册同名模型时会停止，避免覆盖：

```bash
.venv-data/bin/python artifacts/research/process/20261003-ollama-qwen35/download.py
.venv-data/bin/python artifacts/research/process/20261003-ollama-qwen35/install.py
```

独立重复推理验收，不下载文件：

```bash
.venv-data/bin/python artifacts/research/process/20261003-ollama-qwen35/verify.py
```

验收记录与原始响应在[acceptance.json](../artifacts/research/process/20261003-ollama-qwen35/acceptance.json)。中文算术返回 `95`；真实 VINS RGB 图片识别出前景黑色沙发和右侧黄色单人椅；`/v1/chat/completions` 返回正常中文；GPU 进程已实际运行。下载来源、大小、SHA-256 记录见[downloads.json](../artifacts/research/process/20261003-ollama-qwen35/downloads.json)。

本次完成本地服务部署和单图推理检查。研究计划 T3 的 RGB-D 请求、结构化空间输出、冻结配置及专门验收仍需下一阶段完成；这次检查不计为 RGB-D 定位精度、闭环抓取或机械臂执行验收。
