# R322：fresh T2 限定续审计划

> 实际模型：gpt-6-astra。仅规划，不实施、不运行产品/测试/SQL。

**问题与原始证据：** R317 fresh 第 16/16 批在展示前组合输出达到 49,323 UTF8 字节，超过 39,000 上限；b3446d exit 1。原 batch-16-receipt.json 保存完整 selector/actual，保持 SPENT，展示失败没有增加审阅覆盖。原因是同批嵌套证据与源码组合过大，不能以散列值替代尚未读到的语义。

**输入：** input-observation.json 保存原失败、批 14/15、源码世代清单、四次运行及 seam/memo 原件 SHA。ROOT 报告当前 R317 patch Spec Approved、Quality Incomplete；实际累计双 verdict 和 remaining 由独立席位报告，最终解释以该报告为准。

## 新独立额度

新 bucket `R322.fresh_T2_exact_remaining`：最多 **2 次**读取尝试，每次最多 **400 源码行、28,000 UTF8 字节总展示**（包括 header、pins、代码、证据、coverage）。原 12/12 和 R317 16/16 全部保留 SPENT；不重置、不借用 R319 独立 4 读。沿用实际 `/root/fresh_t2_review`，ROOT 记录真实身份。本轮没有新增任何测试、SQL、产品执行或修改权限。

每次先确定完整输出字节数再展示；超界/工具失败/拒绝同样消耗一次，不拆分成隐藏子调用逃避额度。禁止自动重试 batch16。不得只打印摘要结论而隐去矛盾行；任何异常行须可见，超界则保留 Incomplete。

## 两批精确内容

1. **源码重建及四次运行文件完整性。** 对原 source-manifest 的 8/9/10 三文件做全 before/after 文本 diff 重建，与已完整读的 product-source.diff 逐字比较；展示每文件 before/after SHA、重建 diff SHA、完整相等结果及不相等的有限定位。只需补原失败中的实际范围 S8:153–239、S9:1784–1805、S10:2362–2396，已覆盖处无需重复。四个 R317 result 的 raw_streams、persistent_index 及其登记项、new_databases 原件/archives/存在 sidecars 做只读 bytes/SHA 对照；不存在 sidecars 显示 recorded/actual absence。每唯一文件只展示一次相对路径、bytes、SHA、match，聚合总数但不隐藏失败行；不输出完整 result、base64、目录大图或 SQL 内容。保留 cleanup/errors/unobserved 的实际必要标量。仅 pin 容器而不核对所列文件不足以闭合此项。
2. **原 seam/no-repeat 预算及 memo。** 原失败的 S23:3978–4000、4250–4302 有限源码，四组 true-commit-loss/restart 原 JSON 的实际预算对比。提取每个相关 bootstrap value_json 的 payload.state 中 remaining_reobservations、remaining_retries、verification_rounds、consecutive_no_progress、exhausted_reason 及 limits 的有限原值；显示 scope/record_key 与 before/after 对齐、原始时间保持、原预算引用相等与独立 digest、phase/operation/identity、重复恢复无授权与不重提交断言所需实际值。same-live-owner 使用 before/current 的相同状态字段、原 duplicate_disposition、receipt phase 与 original_time 比较。不得展开 definition/draft/history 或完整 snapshot；缺失关键字段如实记录。memo 展示原 copied_context_after_parent_cases、exceptions、primary_duplicate_success_counts、registry_counts 短数组/对象（合计约 2.9KB），连同原件 SHA；不重跑 decoder 或调用产品。

## 实际前置与记录

- [ ] ROOT 将累计报告精确 path/bytes/SHA 与 remaining 追加到 R322 独立 applicability/binding，不覆盖本计划或旧报告。仅报告缺口属于上述范围时放行；增加其他问题则暂停该新增范围。
- [ ] 对上述已冻结输入核对适用性。若 R319 后续修改 observer，S23 继续明确读原冻结 fixture；不得把 R319 当前源码当 R317 相同源码。通过 R319 独立 review 的 generation map 交叉引用 observer 新代。
- [ ] 每批保存 exact arguments、actual、输入 pins、展示行/字节数、已读覆盖及 remaining；保存为 R322/reviews/batch-01-receipt.json、batch-02-receipt.json。行政归档不含额外源码/证据读取，不额外消费读取槽。
- [ ] 新报告分别记录 Spec/Quality verdict、原所有 spent、本轮 consumed/remaining、实际闭合项及仍缺项。ROOT 独立核对。只有本轮实际看到的内容可加入覆盖。

## 验收边界

原 R317 2 RED + 2 GREEN 的 source-specific 结果保持；本轮不是新行为验证。续审可闭合列出的文件完整性与语义缺口，不能把 R319 observer finding 自动判为已解决。最终 T2 质量须结合独立 R319 修复/证据审阅，缺口存在即保持 Incomplete。不得自动重跑原七节点或增加运行额度。R319 source-only prep 可继续，彼此单写者和活跃 gate 边界照原计划。
