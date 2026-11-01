# 诊断更正（按实际 Astra / R367 审阅）

- 时间：2026-10-25 22:42 +08:00
- 性质：**追加更正**，不覆盖原件。`diagnosis.md`、`timings.json`、`profile-summary.json`、`raw/*`
  已被 R367 `plan.json` 的 44 项输入 pin 固定，保持原样。

## 1. 被测节点错误

四组计时跑的是 `test_private_startup_to_transaction_grounding`（startup grounding：
**每个 backend 1 个 exercise**），不是 UTC 节点
`test_local_new_schema_ignores_utc_jump_but_external_does_not`
（**每个 backend 3 个 exercise**：−1 天、+1 天、late-bound）。

因此 572.65 s / 607.00 s / 452.75 s / 322.19 s 都**不能**称为 UTC-memory 耗时，
也不能用来推断 UTC 节点的 600 秒预算。

## 2. fast-sha 探针 != 候选补丁

`raw/fastsha_plugin.py` 用 `type(value) is not str` + 正则替换了 `_text(value)`：

- 跳过了 `strip()`；
- 非 str / 空白输入的错误消息从 `nonempty text required` 变成 `SHA256 required`。

候选补丁 `r366-candidate.patch` **保留** `_text`。所以 452.75 s 不是候选补丁的计时。

## 3. 探针不是"通过"

`probe-e`（452.75 s）与 `probe-c`（322.19 s）均为 **2 FAILED**，失败点在收尾写侧车
（文件重名 / 缺 `BIGSMALL_R158_T2_RESOURCE_DIR`）。它们只说明主路径走到了收尾，
不构成通过证据。

## 4. inclusive 不可相加

`_copy` 57.95% 与 `_sha` 30.11% 在调用链上重叠（`_sha` 由 `_copy` 子树内的校验触发），
不能相加成 88%，更不能推出"优化后只剩 12%"。原报告的粗分类表只是 self-time 归类，
不是互斥成本。

## 5. memo 命中率是推断

"decode memo 几乎全 miss" 来自 key 结构分析（key 含整条 canonical 文本，时间戳一变即变），
**没有实测**命中率。

## 6. 仍然成立的部分（仅限 startup 节点）

- 该节点 CPU 主要在 `from_payload` 解码校验路径（inclusive 92.7%）、`_copy`/`_object` 深拷贝、
  `_sha` 逐字符扫描；SQLite self 0.16%。定性结论"解码校验昂贵、IO 不贵"仍成立。
- `_sha` 正则化在保留 `_text` 时与旧判断接受的字符串集合一致，可作为候选；
  但性能收益必须在合同测试与真实 UTC 上重新测量。

## 7. 对 R367 预算的量化含义（估计，未实测）

| 事实 | 数值 |
| --- | --- |
| startup：2 backend × 1 exercise | 572.65 s → 约 286 s / (backend·exercise) |
| UTC：2 backend × 3 exercise | 6 个 exercise 单元 |
| 若同价：6 × 286 s | 约 1,716 s |
| 若 late-bound 只按 30% 计：2 × (2×286 + 0.3×286) | 约 1,316 s |
| 即使每个 exercise 只要一半 | 约 858 s |

**结论**：`utc_both_01` 的 600 秒预算很可能不足，`_sha` 的 ~20% 不足以弥合这个差距。
R367 计划本身也写了"不保证能在 600 秒内完成"。建议在花掉那次运行前，先做一次
有界的 UTC 单 backend 计时（诊断，不占验收槽），或明确接受高概率不完成。
