# 交接简报：R365 → R366（给规划模型的完整输入）

> 作者：外部 agent（用户授权），通过 SSH 操作 `ningyd@192.168.3.221`，工作区
> `/home/ningyd/文档/ChatGPT/BIGsmall`。产品代码未改，未提交，未改动任何冻结件。

## 1. 我做了什么

1. 停掉 `qwen38-flash-strata` 用户服务（释放约 46 GiB 内存、15 GiB 显存），未禁用开机自启。
2. 读完 `20261025-development-pause-review` 的三份审阅，独立复核后指出：R365 的一行 `_copy`
   改动在数量级上不可能是 600 秒的主因（此判断后来被实测部分修正，见 §3）。
3. 写 `copy_green_01` 的独立事后审阅并落账：`ROOT_accepted=true`。
4. 跑 `codec_regression_01`：4 次启动、3 次预检失败（全部是我写的预约字段错误，
   子进程均未启动），第 4 次 **26/26 通过**，已接受。
5. 收口 R365：`utc_memory_01` **未运行**（槽位仅剩 1 次、不退款），写入收口记录。
6. 做完整诊断（py-spy 采样 + 4 组端到端计时），定位 600 秒的真实成本结构。
7. 写 R366 立项包（本文 + `intake.md/json` + 候选补丁），**补丁未应用**。

## 2. 当前仓库与账本状态

| 项 | 值 |
| --- | --- |
| HEAD | `dd9df375e1d372490145327bcbfee5804352fcc4`（未提交任何改动） |
| 分支 | `research/20261004-continuation`，与 origin 0/0 |
| 产品 | `src/cloud_edge_robot_arm/vision/local_temporal.py`，`1695aded…`，121,321 B |
| 产品改动 | 仅 `_copy` 一行谓词（R365 已接受），未提交 |
| 新测试 | `tests/test_local_temporal_copy_dispatch.py`，`51cf4261…` |
| R365 账本 | `9b96d3a6…`：RED / GREEN / codec 均 SPENT + `ROOT_accepted=true`；`utc_memory_01` HELD 0/1 |

**为什么没提交**：HEAD `dd9df375` 是 R365 全部 649 项 gate pin 的一部分，提交任何一个文件都会让
gate 失效；留给 R366 建新 gate 时一起处理。

## 3. 诊断结论（R366 的直接依据）

节点：`tests/test_operational_runtime_closure.py::test_private_startup_to_transaction_grounding`（memory + sqlite 两参数）。

**核心事实：它不是死循环，也不是超线性爆炸，而是贴着 600 秒上限。**

| 变体 | 墙钟 | 结果 |
| --- | --- | --- |
| 当前产品（含 `_copy` 一行） | **572.65 s** | 2 passed |
| 还原旧 `_copy` 谓词 | **607.00 s** | 2 passed，但已超 600 s |
| `_sha` 换正则 | **452.75 s** | 测试逻辑跑完，仅收尾写 sink 文件重名报错 |
| `_sha` + accessor 缓存 | **322.19 s** | 测试逻辑跑完，仅缺 sink 环境变量报错 |

CPU 分布（py-spy，150 s，14,826 样本）：

| inclusive | 占比 |
| --- | --- |
| `LocalEnvelope.from_payload` | 92.70% |
| `_copy` | 57.95% |
| `_object` | 57.61% |
| `_sha` | **30.11%**（其中逐字符 `<genexpr>` self 24.41%） |
| `to_payload` / `semantic` | 17.34% / 16.62% |
| SQLite（self） | 0.16% |

根因结构：`_object()` 是"先整树 `_copy` 再比字段集"，并按嵌套层级反复调用（`_copy` 最大栈深 23）；
decode memo 的 key 是整条 canonical 文本，轮询中时间戳一变就 miss；`_sha` 用 Python 生成器逐字符扫 64 位十六进制。

## 4. 提议变更（R366 候选）

`r366-candidate.patch`（761 B，`21bdc1d0…`，`git apply --check` 通过）：

```python
import re
...
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")

def _sha(value: JSONValue) -> str:
    text = _text(value)                      # 保留在前，错误类型/消息顺序不变
    if _SHA256_HEX.fullmatch(text) is None:
        raise ValueError("SHA256 required")
    return text
```

只碰 `_sha`；不碰 `_copy`、`_object`、accessor、memo、codec 语义、存储、时钟。
等价性已逐类论证：长度、大小写、非十六进制字符、非 `str`、空串/空白、尾部换行。
实测收益：**572.65 s → 452.75 s（-20.9%）**，600 s 余量从 4.5% 提到 24.5%。

## 5. 需要你决定的事

1. `_sha` 正则化是否作为 R366 的唯一产品变更？若不是，给出更小的可区分方案。
2. **槽位治理**：改动后 R365 的 `utc_memory_01` 必然失效（gate 要求产品字节等于 baseline 加且仅加那一行 `_copy`）。
   选 A（R366 自建端到端预算，同一 UTC 节点）还是 B（显式作废该槽并在 R366 声明边界）？
3. 新 gate 的 pin 集合：建议 ≤ 12 项、只绑直接输入、不递归继承 649 项祖先。若不同意，请给出最小必需集。
4. 端到端验收边界：600 s 内完成 + 两 backend + 资源侧车完整，是否还需额外断言？

## 6. 约束（不要违反）

- 不新增诊断器、不改测试断言、不延长超时、不重试；
- 不复用 R365 gate，不静默复用其 UTC 槽；
- 性能不作为计时断言写入测试，只留一次性基准证据；
- 计划需含：问题、原始证据与 SHA、根因假设、限定范围、验证方法、运行前置、验收边界、预算、回滚。

## 7. 文件索引

| 内容 | 路径 |
| --- | --- |
| 诊断报告 | `artifacts/research/process/20261025-utc-cost-diagnosis/diagnosis.md`（`ba83e793…`） |
| 计时数据 | 同目录 `timings.json`（`a1da6c33…`）、`profile-summary.json`、`raw/profile-a.json` |
| 原始运行输出 | 同目录 `raw/*.out`、`raw/*.py` |
| R366 立项 | `artifacts/research/process/20261025-r366-sha-fastpath/{intake.md,intake.json,astra-request.md,r366-candidate.patch}` |
| R365 收口 | `.../round365-.../r365-closure-20261025.md` |
| 状态入口 | `artifacts/research/process/20261025-green-postrun-review/current-state-entry-20261025.md` |
