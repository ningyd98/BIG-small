# qwen3.8-max 可用性实测

2026-10-06 13:27（Asia/Shanghai），用户提供凭据在既有北京 Token Plan 端点的一次文本推理可用。

- 端点：`https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。
- GET `/models`：HTTP 200，目录包含 `qwen3.8-max`，耗时 62.297 ms。
- POST `/chat/completions`：HTTP 200，返回模型精确为 `qwen3.8-max`，`finish_reason=stop`，内容为 `OK.`，耗时 651.383 ms。
- API 用量：输入 16、输出 2、合计 18 Token；实际账单金额未知。
- 提示要求仅返回 `OK`，模型多返回一个句点。因此严格文本一致性未通过；这不改变本次文本推理正常完成的可用性判据。未改提示或重试。
- 两次串行请求，无自动重试；DNS/TCP 均使用既有物理网卡 `enp7s0` 直连传输，逐响应 socket 绑定验证通过，代理关闭、重定向关闭、TLS 校验开启。
- 用户凭据只通过回显关闭且经验证的 TTY 输入到测试进程内存，没有写入源码、环境变量或证据文件；进程已正常退出。

## 开发验证与原始失败

首次默认执行工具因 bwrap loopback 权限失败；自动审批后的 escalated 通道可执行。Astra 第一轮将执行限定为既有直连传输、一次目录和最多一次短文本推理。

诊断脚本最初离线语法/导入/哈希检查通过，但真实隐藏输入在文本 `r+` 打开不可寻址的 `/dev/tty` 时失败。此时未输入凭据、未发送 API 请求。原始 CRLF 错误和原脚本保留在 `attempt-1-tty-failure/`，不以离线通过代替终端实际证据。

Astra 第二轮批准唯一一行改为无缓冲二进制只读打开。相同真实 `read_key` 无凭据回归先 FAIL 后 PASS，验证 ECHO 关闭及终端设置恢复；新的离线检查保留在 `attempt-2/`，原检查未覆盖。生产源码、云边端配置和运行数据库未修改。

## 证据与验收边界

- `request.json` 是实际发送的非敏感 POST body 字节；两个 `*-response.body` 是实际服务端 body 原字节，receipt 与 verification 绑定 SHA256。
- `result.json` 保存逐请求实际网络、状态、耗时、模型与用量；`verification.json` 从原始响应重新解析并验证。
- `steps.md` 与 `attempt-2/steps.md` 记录步骤和验证，`output-sha256.json` 是本次交付文件清单。
- 本次只有一例文本可用性证据。视觉输入、云边端闭环、机械臂动作、稳定性和正式研究验收均未测试；没有把软件检查通过写成正式验收。
- 本次小规模请求/响应证据将提交，不包含其他批量 raw、运行数据库、凭据、权重或 SDK，也不宣称是完整远端研究复现包。
