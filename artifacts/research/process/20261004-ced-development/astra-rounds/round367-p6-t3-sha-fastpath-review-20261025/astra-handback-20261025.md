# R367 执行结果交回 Astra（2026-10-25 23:05 +08:00）

- 触发：用户 22:47 明确恢复开发，按 `plan.md` 步骤 1–5 执行完毕；UTC 未通过，按计划交回实际 Astra。
- 边界：四次命令各一次、无重试、无新诊断器、未改断言/预算/backend、未推送 GitHub。

## 1. 四次运行

| 命令 | 用例 | exit | 耗时 | 结果 | 证据 |
| --- | ---: | ---: | ---: | --- | --- |
| `sha_contract_before_01` | 31 | 0 | 0.264 s | PASS | result 24,592 B `23b19f46…`；junit 3,742 B `a14b7f72…` |
| `sha_contract_after_01` | 31 | 0 | 0.264 s | PASS | result 24,587 B `4631454a…`；junit 3,742 B `aa6a0ff6…` |
| `codec_regression_01` | 26 | 0 | 14.25 s | PASS | result 25,448 B `62d56562…`；junit 3,975 B `68932f6c…` |
| `utc_both_01` | 0 | **−15** | **600.016 s** | **NONCOMPLETION** | failure 15,186 B `4abc3182…` |

三次通过项均 `nodeids_exact=true`、源身份前后一致、进程组回收干净、无残留进程。

## 2. UTC 的关键事实

- 600.016 s 到点，SIGTERM，`timed_out=true`，进程组空；
- **无 JUnit、无 utc-provenance case、resources 目录为空**；
- `persistent-basetemp/` 下只出现 `memory-1`，**memory backend 的 −1 天 exercise 未完成**，+1 天、late-bound、sqlite 均未开始。

推论（非测量）：单个 UTC exercise 已超过 600 s；完整 6 个 exercise 单元约需 **2,400–3,600 s**。

## 3. 本轮确定的事

1. `_sha` 正则化在语义上成立：31 例合同在改动前后逐例一致（31/31 → 31/31），26 个 codec 节点无回归。
2. `_sha` 的性能收益**无法**弥合 UTC 预算差距：缺口是 4–6 倍，不是 20%。
3. `utc_both_01` 记 `SPENT 1/0`、`NONCOMPLETION_600S`，不退款、不重试。
4. **新增的可操作事实**：600 s 预算与该节点真实成本量级不匹配。这比"根因未知"更能指导下一步。

## 4. 当前状态

| 项 | 值 |
| --- | --- |
| 产品 | `local_temporal.py` `c8a5a5a4…`，121,341 B（`_copy` 一行 + `_sha` 正则化），**未提交** |
| 合同测试 | `tests/test_local_temporal_sha_contract.py` 2,710 B `990aa654…`，**未提交** |
| runner | `implementation/run-r367.py`（193 行，4 个字面命令） |
| R367 账本 | 4 项全部 SPENT 1/0；UTC 项 `validation_pass=false` |
| R365 旧 UTC 槽 | `HELD 0/1` 未运行，已写 `r365-utc-slot-retirement-20261025.json` 退役 |
| HEAD | `dd9df375…` 未变 |

## 5. 需要 Astra 决定

**Q1 `_sha` 候选的去留**：它没有解决 UTC，但语义安全、合同与 codec 均已锁定、量级 -20%。
是否作为独立的小改动接受并提交？还是随 UTC 失败一并回滚？

**Q2 成本与预算不匹配的路线**：

- **A｜继续压成本**：靶点是 `from_payload` 的"校验即复制"（inclusive 92.7%，`_copy` 58%）。把 `_object` 改为只校验不复制，理论上 2–3 倍；即便 3 倍，6 个 exercise 仍需 800–1,200 s，仍超 600。
- **B｜改验收结构**：按 backend 拆分（每 backend 一次 child）或提高 cap 到实测所需（约 2,400 s）。这动的是门禁与预算，不是产品，必须由 Astra 明确替代原 600 s 约束。
- **C｜先做一次 sizing**：memory backend 完整跑一次（cap 3,600 s），拿到真实成本，再定优化目标与预算。

**Q3 若走 A**：是否允许修改 `_object`/accessor（共享 codec 语义、所有权与脱别名边界）？需要什么证据边界？

**Q4 提交策略**：合同测试与 `_sha` 是否单独成一个 commit（便于回滚），UTC 修复另开？

## 6. 建议（供参考，非决定）

先 **C** 再 **A**：没有真实成本数字，任何优化目标都是猜测；B 可作为最后的验收结构替代，但会改变"一次 600 秒"的原约束，必须显式记录。

## 7. 证据索引

- `implementation/<command>/{result.json,completion.json,junit.xml,stdout.txt,stderr.txt}`
- `implementation/utc_both_01/{failure.json,invocation.json,persistent-basetemp/}`
- `implementation/r367-ledger.json`、`step-report-20261025.md`、`r365-utc-slot-retirement-20261025.json`
- 诊断背景：`../../20261025-utc-cost-diagnosis/`（注意：其计时节点为 startup，非 UTC）
