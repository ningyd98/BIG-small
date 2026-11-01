# 给实际 Astra 的立项请求（R366）

请阅读并据此生成 R366 的 `plan.md` 与 `plan.json`：

- 立项输入：`intake.json`、`intake.md`
- 证据：`../20261025-utc-cost-diagnosis/diagnosis.md`、`timings.json`、`profile-summary.json`、`raw/profile-a.json`
- 候选补丁：`r366-candidate.patch`（已 `git apply --check` 通过，尚未应用）

## 必须回答的问题

1. `_sha` 正则化是否是本轮最小、可区分、可验收的修复？若不是，给出替代方案与理由。
2. R365 的 `utc_memory_01` 槽位在改动后必然失效（gate 只允许那一行 `_copy`）。选择方案 A（R366 自建端到端预算）还是 B（作废该槽并在 R366 声明范围）？
3. 新 gate 的 pin 集合：建议 ≤ 12 项、只绑直接输入、不递归继承。若不同意，说明必须保留的祖先依赖及最小集合。
4. 端到端运行的验收边界：600 s 上限内完成、两个 backend、资源侧车完整；是否还需要额外断言？

## 约束

- 不新增诊断器、不修改测试断言、不延长超时、不重试；
- 不碰 `_copy`、`_object`、accessor、memo、所有权与 codec 语义；
- 性能提升只作为一次性基准证据，不写成计时断言；
- 计划需包含：问题、原始证据与 SHA、根因假设、限定范围、验证方法、运行前置、验收边界、预算与回滚。

## 期望产出

`artifacts/research/process/20261025-r366-sha-fastpath/plan.md` 与 `plan.json`，其中 `plan.json` 至少包含：`commands`（本轮允许的运行与预算）、`inputs`（带 SHA 的输入清单）、`acceptance_and_followup`（验收边界与后续节点）。
