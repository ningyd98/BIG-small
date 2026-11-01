# R367 `_sha` 最小修改与真实 UTC 验收前瞻计划

> **For agentic workers:** 恢复开发后，按 `superpowers:executing-plans` 逐项实施。此文件只完成审阅与规划，**不授权恢复开发、运行、改账、commit 或 push**；用户当前暂停仍有效。

**Goal:** 在不改变严格 SHA256 校验语义的前提下，只规划 `_sha` 快速路径，并把一次真实 UTC 双 backend 验收的预算和证据边界写清楚。

**Architecture:** 保留 `_text(value)`，只把其后的 Python 长度/逐字符判断换为预编译 ASCII 正则完整匹配。沿用现有有限 runner 的超时、资源采集和清理方法，去掉历史祖先递归及固定 HEAD 行政门禁，不另建协调框架。

**Tech Stack:** 当前 Python 3.12+ / pytest / 标准库 `re`；不安装依赖。

**Spec:** 外部原名输入 `artifacts/research/process/20261025-r366-sha-fastpath/{astra-brief.md,intake.md,intake.json,astra-request.md,r366-candidate.patch}`；本轮为 R367，因为现有 dependency-locator 已占用 R366。实际规划模型为 **gpt-6-astra**，agent 为 `/root/astra_r367_sha_review`，2026-10-25。

## 四项决定

1. **推荐 `_sha` 候选为唯一后续产品修改。** 允许 `import re`、`_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")` 和一个判断替换；`_text` 调用、异常消息、返回值及当前 `_copy` 一行均保持原样。这是静态语义支持的候选，不是已验证性能修复。
2. **A 与 B 同时采用。** 待明确恢复后，申请 R367 自有的一次双 backend UTC 预算，并用新的退役记录关闭 R365 未运行槽的未来使用权。旧槽保持历史 `used=0`，不能把 HELD 0/1 写成已运行 SPENT，也不能给已消耗失败退款。**现在不修改任一账本。**
3. **接受 ≤12 个直接控制对象，不声称 ≤12 个实际文件。** 采用下文 9 项控制，源码身份使用 Git 当前 `src/tests` 树及真实 dirty/untracked overlay。当前覆盖 **694** 个源码/测试文件，新增合同测试后为 **695**；这是公开的保守源码身份范围，不是最小实际 import 闭包。若“12”指全部依赖文件，不能承诺。禁止把 649 个历史祖先改装成一个隐藏 manifest。
4. **600 秒是两 backend 合计 child 上限。** 一次 child 包含完整 UTC memory、sqlite 两节点，outer 900 秒，不重试、不新增诊断、不改原断言。额外条件仅为真实 artifacts、准确 nodeid/数量、源一致性、资源与清理验收。没有足够证据保证其能在 600 秒内完成。

## 已核对证据与纠正

所有引用输入的实际大小与完整 SHA256 见同目录 `plan.json.inputs`（44 项；它是审阅索引，不是运行祖先门禁）。原件不改名、不覆写。关键输入为：

| 输入 | 字节 | SHA256 |
| --- | ---: | --- |
| 当前 `src/cloud_edge_robot_arm/vision/local_temporal.py` | 121321 | `1695aded2b2e1e5c21d677bd4d445184537aabc84310cf14474ace91b1ca15d3` |
| 原名 `r366-candidate.patch` | 761 | `21bdc1d06c1ce9f0f7244dd0f3c61cb1e407f22cee5179712680a1d5ec05ba24` |
| R365 ROOT 账本 | 19245 | `9b96d3a6ef75faa8d3b4fcd3a49b2134a19eb430fd0488c0e33bc74b629727d6` |
| R365 AUTHOR 账本 | 5136 | `957e1a46c0431e7bd0b6139dc0087b2dac40c35226d807657f390594da755074` |

- 原始 R363 `utc_no_sigusr2_01/result.json` 确认 child `-15`、`timed_out=true`、包含清理耗时 `600.0180412190093s`；进程已回收、进程组空。原 UTC-memory 不完成问题仍未解决，不能把诊断无崩溃当成修复。
- 四组诊断的实际节点均为 `test_private_startup_to_transaction_grounding` 的 memory + sqlite。`baseline.out` 是 **2 passed / pytest 572.65s / WALL 572.88s**；`probe-f.out` 是 **2 passed / pytest 607.00s / WALL 607.30s**。这不是原 UTC 节点，不能据此排除原 UTC 死循环/超线性，也不能将 572.65 秒称为 UTC-memory 耗时。
- `raw/fastsha_plugin.py` 直接类型判断加正则，**跳过 `_text` 及 `strip()`**。非 str、空白错误消息改变；有效输入也少了一步工作。`probe-e.out` 为 **2 FAILED / 452.75s**，收尾 sink 重名；`probe-c.out` 为 **2 FAILED / 322.19s**，缺 sink 环境且另改 accessor。它们支持主路径走到收尾的探索性线索，仍不是完整通过，也不是保留 `_text` 候选的精确计时。
- 不接受候选已经得到 **20.9% 提速、24.5% 余量**的结论。150 秒 startup profile 的 inclusive 数字相互重叠，不能相加，也不是完整 UTC 成本归因；memo 几乎全 miss 没有实测支持。
- `_text` 源码要求 `type(value) is str` 且 `strip()` 非空，返回原对象。保留它以后，固定 64 位 `[0-9a-f]` 的 `fullmatch` 与旧判断所接受的字符串集合一致，错误顺序也可保持；仍需后续合同验证。
- 原 UTC 每 backend 有 `-1 day`、`+1 day` 和 late-bound 三次 `_b_t2_exercise`，还涉及监督和外部 UTC 检查。双 backend 共 **6** 个生命周期，而 startup 每 backend 只有一个主 exercise。直接用 452.75 秒预测双 UTC 的 600 秒结果不成立；这个预算下成功很可疑，不作性能保证，不先花一次运行来补猜测。

R365 的实际 26-pass 与用户此次背书的外部接受状态保留。四次 wrapper 启动、三次预检失败、一次实际 child 运行也全部保留。外部材料记录授权来源；本 agent 不倒写自己做过历史 ROOT 复核，也不因拿不到外部聊天原文否定用户决定。旧 acceptance 的 invocation hash 仅 16 位，实际文件为 30667B、完整 SHA256 `c971965ee6cc853f043cae066a0a65a9814de52ca508a227869ad5f28fa76717`，前缀一致。这是证据元数据截短，不是文件损坏或产品根因，不因此重跑 codec 或另造修复轮。ROOT 新 `root-review.json` 独立保存复核。

## 范围与前置条件

不修改 `_copy`、`_object`、accessor、memo、codec 语义、存储、时钟、既有测试断言和冻结件。不扩展到其余 local_temporal 全部测试。源码/新合同测试之外，只允许有限的新轮 runner 身份/选择/预算配置、证据记录与报告准备。需要更大 runner 重写、新诊断或新产品根因时，暂停相关实施，再交实际 Astra；本计划不包办它们。

恢复后的运行前需满足：明确用户恢复授权；产品和候选完整 SHA 仍适用；一次性独占输出路径；不存在并行测试/源码写入；环境及载荷有记录；当前解释器/依赖身份和必要启动条件明确；真实 seed 可读且 hash 一致；所有 argv/env/资源上界静态审阅完成。禁止用 pytest collection、产品导入或试运行来充当无预算准备。

九项直接控制对象是：

1. 有效 `src/tests` 源码身份（Git 树、内容/模式、staged 与 unstaged overlay、逐项列出的 untracked 实际输入）。
2. 本轮有限 runner。
3. 实际使用的 resource helper。
4. 不变的 R235 prerequisite plugin。
5. R196 真实 codec seed `green63/cases/6d92899340e539991792be9037c073ce65513cc029918750cae4831bd0ef02f4.json`。
6. `pyproject.toml`。
7. 实际 runtime 环境身份（解释器路径/realpath/full hash/版本、pyvenv、依赖版本及可用 RECORD 身份、pytest 配置、清洁 env）。
8. 本 `plan.json`。
9. 一份当前授权/预算/节点选择记录。

当前 `src` 为 406 tracked 文件；`tests` 为 287 tracked + 1 个 untracked copy 测试。Git 树和 overlay 的实际标识见 JSON。**不逐次递归重建/哈希 694 文件的历史门禁**：复用 Git 已有内容树；检查真正的工作树变化和未跟踪输入；必要时在执行前后核对有效源码内容。源码身份覆盖范围与真正运行所读输入分开说明，不把 149 或 649 项依赖藏入一个 manifest。`tests/test_operational_time_v1.py`、`tests/__init__.py` 及 factory/bootstrap/owner/verification 等 fixture 文件在当前 tests 身份内可追溯；seed/plugin 位于树外，单独绑定。未在本次只读规划中声称求出了最小动态 import 闭包。

观察到的 HEAD `dd9df375e1d372490145327bcbfee5804352fcc4` 只作来源记录。纯文档 commit 不使验证失效；提交已验证源码后，以相同有效源码内容重核，不因 HEAD 字符串改变而重新运行。无锁文件是环境复现边界，不据此安装或更新包。

## Review Focus

严格 str 子类拒绝；空串/Unicode 空白与一般非法 SHA 的异常消息区分；换行/NUL/Unicode/孤立代理码点拒绝；原字符串不裁剪且合法值原对象返回；已有 copy/codec 行为不退化。前四项由同一合同矩阵验证，第五项由源差异核对及原 26 codec 节点验证，不增加计时断言。

## 前瞻步骤（当前均未执行）

- [ ] **1. 恢复授权后准备合同与有限 runner。** 新建 `tests/test_local_temporal_sha_contract.py::test_sha_contract`，31 个固定 ID 和预期 nodeid 在 JSON 列明；覆盖 3 个合法值、长度、大小写/非十六进制、空白/换行/NUL/Unicode、非 str 与 str 子类。合法值验证相同对象与内容；其余验证精确 `ValueError` 类型和消息。不增加随机 fuzz、性能断言或实现细节断言。
- [ ] **2. 运行一次原产品合同。** `sha_contract_before_01`，预期 **31 pass / 0 skip**。这是等价性 baseline，预期通过，不伪造 RED。child 60 秒；失败不是本计划预期 RED，保留证据并回 Astra。
- [ ] **3. 应用原候选补丁。** 仅产品三处允许 delta；保留现有 `_copy` 一行。重新核对差异，冻结相同测试的 candidate 身份。
- [ ] **4. 运行一次候选合同，再运行一次原 26 codec。** `sha_contract_after_01` 预期 31 pass；`codec_regression_01` 仅三份既有 codec 文件，预期 JSON 列出的准确 **26** 节点全过。合同 child 60 秒，codec 600 秒。不得把“其余单测”作为无界附带任务。
- [ ] **5. 条件满足后才预约一次完整 UTC 双 backend。** 同一次 child 精确选择下列两个 nodeid，**合计 child 600 秒、outer 900 秒**。保留原 R235 plugin 与真实资源侧车；不运行 startup 对照、基线比较或额外诊断。

```text
tests/test_operational_runtime_closure.py::test_local_new_schema_ignores_utc_jump_but_external_does_not[memory]
tests/test_operational_runtime_closure.py::test_local_new_schema_ignores_utc_jump_but_external_does_not[sqlite]
```

四次命令的完整 child argv/env、准确 nodeid 列表与预算在 `plan.json.commands`；它们是**提议，非已授权命令**。一个时刻仅一个 child。runner 只调整本轮字面选择、路径、源码身份与 UTC 总 cap 6，保留原有采集、deadline、cleanup 机制，不执行旧 R365 runner，不递归导入旧门禁。

## 验收、失败处理与交付

开发验收要求 baseline 31、candidate 31、codec 26 各自准确 nodeid 全部 pass、0 fail/error/skip，退出 0，源身份一致。只有完整 UTC **2/2 pass**、退出 0、未超时且合计 child 不超过 600 秒，再加以下真实证据，才形成这两个当前源码节点的软件运行候选：

- 两个 `utc-provenance` case 各含三场景；资源 sidecar 精确对应节点、进程、命令。每 case 3 次、全命令 6 次 attempted/entered/normal-return poll，有实际 ID/线程/分配与回收关联，未知计数不算通过。
- poll 并发峰值 ≤2，**全命令** constructed-worker attempts ≤64，每 worker broker/heartbeat 峰值 ≤1；初始化/分配分母准确，无清理错误。
- 全 stdout/stderr、JUnit、case、prerequisite、source-before/after、resource、process/deadline 与 cleanup 记录完整；进程 leader 已 reap、组空，sink 独占新建，不能合成缺失侧车或忽略写入失败。

沿用现有保护边界：cleanup 15 秒含 TERM grace 5 秒，capture 至多 240 秒，outer 900 秒及 kill-after 20 秒；stdout/stderr 各 32 MiB、metadata/JSONL 16 MiB、每命令 persistent 1 GiB/10000 entries、全轮 4 GiB、运行前可用空间至少 3 GiB。不得截断原始日志使其通过。900 秒不赋予 child 超过 600 秒的运行权。

所有提议命令各一次、无重试；任何启动与预检拒绝都留记录，不自动退款/reprovision。计划外失败、新根因或范围扩大时，暂停受影响工作，保留原始失败与步骤报告，交实际 Astra。UTC 不完成不能靠改断言、延时、改 backend 或重跑解决。

开发验证、此两节点软件真实运行、正式研究验收分列。即便全过，也不代表全 T3/B9/B、物理机器人、云边端正式研究或完整远端复现包验收。若未来需要撤销候选，只反向恢复 `_sha` delta 至上述 121321B 原产品 SHA，保留 `_copy` 一行、失败原件及已消耗账；不 blanket reset。

授权实施且相应交付确实验证后，按明确路径 commit/push `research/20261004-continuation`，核对本地、上游、远端完整 SHA，并重核有效源码内容。raw、数据库、凭据、权重和 SDK 的既有交付边界不变。本次审阅不执行这些动作。
