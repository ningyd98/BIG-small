# Qwen3.8-max TTY 单行修复 Implementation Plan

> 执行者沿用 superpowers:executing-plans；本轮仅补足真实 TTY 前置检查并修复一行。

**Goal:** 修复凭据输入前 /dev/tty 打开失败，继续既已授权的最小可用性诊断。

**Architecture:** 原始无缓冲只读 fd 交给 termios，保留现有 getpass 与 finally 恢复流程。

**Tech Stack:** .venv/bin/python、termios、getpass。

**Spec:** AGENTS.md 与上一轮 `artifacts/research/process/20261004-ced-development/astra-rounds/qwen38max-availability-20261006/plan.json`。

**Planner:** gpt-6-astra；planned_not_executed。

## 问题与根因

tty:true 真运行在 read_key 首句打开 /dev/tty 时失败；尚未输入凭据、零 API 调用。

open 的文本 r+ 模式构建带缓冲读写流，对不可寻址的终端要求 seek；该诊断只需原始 fd 调用 termios。已通过的 AST/import/输入哈希检查未触达真实 TTY 前置条件。

原错误：`io.UnsupportedOperation: File or stream is not seekable.`，probe.py:68，exit 1。冻结错误路径 `artifacts/research/process/20261006-qwen38max-availability/attempt-1-tty-failure/failure.txt`；CRLF 原字节及冻结源不改。

## 输入 SHA256（六项均已复核）

| 文件 | SHA256 |
| --- | --- |
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` |
| `artifacts/research/process/20261006-qwen38max-availability/probe.py` | `7b0428095d4374560a4e6b90d6425494f59479a490d7272f2672aa91ef392f1e` |
| `artifacts/research/process/20261006-qwen38max-availability/offline-check.json` | `b652071c059f23eced1bbc2bc21e3432a502d7940589d8a3ca2a75841d1efa5f` |
| `artifacts/research/process/20261006-qwen38max-availability/attempt-1-tty-failure/probe-original.py` | `7b0428095d4374560a4e6b90d6425494f59479a490d7272f2672aa91ef392f1e` |
| `artifacts/research/process/20261006-qwen38max-availability/attempt-1-tty-failure/failure.txt` | `7e4fc706cb06f413b73aff92a4595a6e0ff9674a83d220c1865d2542b9ff1e2c` |
| `artifacts/research/process/20261004-ced-development/astra-rounds/qwen38max-availability-20261006/plan.json` | `5234f3f3b45cd2234676f677162d5dc3ed220b0057af224d093eaf6e9dab06af` |
| `artifacts/research/process/20261006-qwen38max-availability/attempt-1-tty-failure/input-sha256.json` | `7bc00457d3e3f860bfd49d63758d9c0a33e16a130615f32a65d68ed94189b3f7` |

## 限定修改

仅 `artifacts/research/process/20261006-qwen38max-availability/probe.py` 一行：

```diff
-    with open("/dev/tty", "r+") as terminal:
+    with open("/dev/tty", "rb", buffering=0) as terminal:
```

只替换此一行；保留同一 fd 的 termios ECHO 关闭与回读验证、getpass 内存读取、finally 恢复。端点、模型、请求参数、transport、预算、其他源码及原始证据不变。

## 执行前置与步骤

- 实施前复核本轮全部输入哈希；确认 probe.py 仍与 probe-original.py 相同且替换目标恰好一次。
- 固定 .venv/bin/python、tty:true、既有已批准 require_escalated 通道；不安装或调整系统配置。
- 用户凭据由主控保留，规划者不读取；只有终端隐藏 prompt 已确认后才输入，不落盘、不加入参数或环境变量。
- 继承原轮计划全部请求、网络、输出保护及 Git 交付约束；旧 run-start.json/result.json 不应存在，否则停止且不覆盖。

- [ ] 用 tty:true 单独打开 /dev/tty 为 rb、buffering=0，验证 fileno 与 termios 可读；保存原设置、关闭 ECHO、回读断言关闭，finally 恢复并核对原设置。禁止读取输入或发送网络，仅将检查结果以独占创建写入 attempt-2/tty-check.json。
- [ ] TTY 前置通过后仅执行规定的一行替换。记录新 probe.py SHA256 与单行 diff 到 attempt-2/implementation.json，冻结旧源不动。
- [ ] 使用 importlib 导入当前 probe.py（不调用 main/run），ast.parse 校验并调用 check_inputs()；记录 current inputs 与原计划仍匹配，确认 BASE/BODY/POLICY 和原计划一致。采用独占创建写 attempt-2/offline-check.json。禁止重跑旧 --offline-check，禁止覆盖根目录 offline-check.json。
- [ ] 复核单行差异与冻结证据哈希；使用 tty:true 运行现有真实脚本，隐藏 prompt 后由主控输入 Key。继承最多一次 GET、最多一次 POST、串行、无自动重试；本轮此前 API 调用数为 0。
- [ ] 将 TTY 验证、离线验证、真实结果分层记录到 attempt-2/steps.md 并汇入阶段 summary；原失败永久保留。仅提交本任务无密钥路径，推送当前研发分支后核对本地、上游、远端 SHA。

## Review Focus

不可寻址终端由无凭据 TTY 检查覆盖；ECHO 必须在 finally 恢复；旧离线报告不可覆盖；真实请求预算不增加；凭据不得输出或持久化。

## 验证及验收边界

- **development**：单行 diff 精确、TTY 打开与 ECHO 关闭/恢复检查通过、AST/import/check_inputs 通过，原证据哈希不变；仅证明本次 TTY 前置及脚本离线检查。
- **real_run**：真实脚本通过 read_key 才证明 TTY 故障已修复；GET 200 不等于推理成功。POST 200、model 精确为 qwen3.8-max、content 非空、finish_reason stop 才证明一次文本推理可用。
- **formal_acceptance**：视觉、云边端闭环、硬件及可靠性/正式研究验收全部未测试。

TTY 前置、单行替换或离线检查出现计划外失败时暂停受影响实施，交下一轮 gpt-6-astra；HTTP/网络预期诊断错误沿用原计划只记录、不重试或换配置。

覆盖原始失败及 CRLF、六项输入及 manifest 哈希、单行范围、无凭据 TTY 前置、独立新验证目录、不覆盖既有离线报告及分层验收。本规划未执行修复/测试/网络。

## 主控追加的真实 read_key 回归验证

原始 RED：UnsupportedOperation；terminal_state_restored=true、network_calls=0、real_credential_used=false。冻结 RED 保留，以下两项已读取并计算哈希：

- `artifacts/research/process/20261006-qwen38max-availability/attempt-1-tty-failure/tty-input-check.py`：`ebd2a2da8317ab46423170452891e2f93ab64d1352971dcab75a60e5ff2d4c2d`
- `artifacts/research/process/20261006-qwen38max-availability/attempt-1-tty-failure/tty-red.json`：`c79f095461ace63325a5f9c2cdb7cf64a160b93d833a7849d5801313c0fd0675`

- [ ] 单行替换后以 tty:true 执行 .venv/bin/python artifacts/research/process/20261006-qwen38max-availability/attempt-1-tty-failure/tty-input-check.py --output artifacts/research/process/20261006-qwen38max-availability/attempt-2/tty-green.json；要求 status PASS、echo_disabled_observed true、terminal_state_restored true、network_calls 0、real_credential_used false。该检查导入真实 read_key，仅将 getpass 替换为固定非敏感返回值，GREEN 前禁止输入真实 Key。不执行项目全量测试。
