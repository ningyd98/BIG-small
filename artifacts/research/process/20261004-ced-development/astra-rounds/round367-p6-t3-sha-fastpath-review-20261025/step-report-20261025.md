# R367 执行步骤报告（2026-10-25 23:00 +08:00）

- 执行：外部 agent（用户授权恢复开发后按 plan.md 步骤 1–5）
- 产品：`local_temporal.py` 现为 `c8a5a5a4…`（121,341 B），含 `_copy` 一行与 `_sha` 正则化
- 运行器：`implementation/run-r367.py`（193 行，仅 4 个字面命令，无祖先继承）

## 1. 四次运行结果

| 命令 | 用例 | child exit | 超时 | 耗时 | 结果 |
| --- | ---: | ---: | --- | ---: | --- |
| `sha_contract_before_01` | 31 | 0 | 否 | 0.264 s | **PASS** |
| `sha_contract_after_01` | 31 | 0 | 否 | 0.264 s | **PASS** |
| `codec_regression_01` | 26 | 0 | 否 | 14.25 s | **PASS** |
| `utc_both_01` | 0（无 JUnit） | **-15** | **是** | **600.016 s** | **NONCOMPLETION** |

四次均 `nodeids_exact=true`（前三项）、`sources_unchanged=true`、进程组回收干净、无残留进程。

## 2. UTC 运行的具体事实

- 600.016 s 到点，SIGTERM（-15），进程组已空；
- **没有 JUnit、没有 utc-provenance case、resources 目录为空**；
- `persistent-basetemp/` 下只出现 `memory-1` 一个 exercise 目录，**+1 天、late-bound 与 sqlite backend 均未开始**。

即：在 600 秒内，连 **memory backend 的 −1 天 exercise 都没有跑完**。

## 3. 结论

1. `_sha` 正则化在**语义层面成立**：31 例合同在改动前后逐例一致（31/31 → 31/31），26 个 codec 节点无回归。
2. 该改动**不足以**让原 UTC 节点在 600 秒内完成，且差距不是 20% 而是数倍：单是第一个 exercise 就超过 600 秒。
3. 因此本轮的 UTC 验收**未通过**，`utc_both_01` 记录为 `NONCOMPLETION_600S`，`used=1, remaining=0`，不退款、不重试。
4. 按 plan.md：UTC 不完成不能靠改断言、延时、改 backend 或重跑解决，需交实际 Astra 决定下一步。

## 4. 证据位置

- 三次通过：`implementation/<命令>/{result.json,completion.json,junit.xml,stdout.txt,stderr.txt}`
- UTC 失败：`implementation/utc_both_01/{failure.json,invocation.json,stdout.txt,stderr.txt,persistent-basetemp/}`
- 账本：`implementation/r367-ledger.json`（四项均 SPENT 1/0）
- 合同测试：`tests/test_local_temporal_sha_contract.py`（31 例）

## 5. 未做

- 未重跑、未改断言、未改预算、未推送 GitHub；
- 未对 R365 的 `utc_memory_01` 做任何处置（仍 HELD 0/1，按决定 2 待退役记录）；
- 未新增诊断器。
