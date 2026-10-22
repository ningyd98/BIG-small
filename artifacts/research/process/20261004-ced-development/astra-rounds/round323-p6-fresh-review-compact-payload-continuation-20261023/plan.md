# R323：压缩 fresh review 展示的限定接续

> 实际模型 gpt-6-astra；本轮仅规划。ROOT 独立放行，同一实际 fresh seat 审阅。

## 问题、证据与根因

R322 batch1 的完整原调用及返回保存在 reviews/batch-01-receipt.json，SHA a6b8ebeca2be23cf7b5957305effd2619c03459530372da8100fdd5fd460d404。原 native 7b369e exit 1：29,021 UTF8 字节超过 28,000 展示上限；失败在 print 前，SPENT 1/2，未增加覆盖。完整脚本已读：meta 重复输出全部 plan（该计划文件本身 14,243 字节）和 release 字段，同时展示 144 行源码及证据。该组合导致展示超界，不是产品或测试失败。

## 精确补读

新增独立 bucket `R323.fresh_T2_G1_G2_product_context`，**仅 1 次**，最多 400 源码行、28,000 总 UTF8 字节；本次 reader 使用更严格 **24,000 总字节**展示断言，包含所有 header/pins/source/metadata/coverage。超界或工具拒绝同样耗用，不自动重试。

以原失败回执 invocation.args.cmd 为模板，按 plan.json 的逐项字面映射，计数各恰为 1：

- 去掉 meta 的 `plan` 全文、`release_keys`、`release_scalars` 三项；保留计划及 release 的精确 pins 和原适用性断言，不输出 binding/旧报告正文。
- 原 144 行 current product 源码、三个文件全 diff 重建、四个已固定 result 的 raw/index/DB/sidecars 验证和所有 mismatch 保留。
- 读取原 persistent_index 后，在 records.append 前加 `verify(index['files'],'indexed_files')`，补其已有常规文件 bytes/SHA 登记项核对。其目录/链接不是常规文件 hash pin，不让递归验证读取目录或跟随无 hash 的链接；不输出完整 index。每份 index 仅 3/4 项，已做结构核对。
- 标题和 coverage selector 更新为本次 R323；护栏改为 `<=24000`。原源路径、expected_results、pin 断言及预算之外的读取范围均不改。仅更改展示与同 G2 的已登记项校验，无新产品或源码查询。

**本批范围只有 G1/G2/G5 product context：** protocol153–239、memory1784–1805、sqlite2362–2396。不重复展示完整计划、release 或历史大报告，不省略错误行来通过字节门。修正文本由 fresh seat/ROOT 在执行前核对；本 Astra 未运行该 reader。

## 配额、前置和结果

- 原 12/12、R317 16/16、R322 batch1 SPENT 全部保留。R322 总额度仍 2；其尚未用 batch2 按原计划独立处理 G3/G4/76 行 frozen fixture，不转借给本批。R319 独立四读和 runtime 额度不变。
- ROOT 放行前绑定本轮计划、原失败和当前 inputs，确认三 product 源码仍为 R317 修复代。若 observer 已进入 R319 新代，本批不读它；frozen fixture 由 R322 原 batch2 明确使用旧路径。
- 保存 R323/reviews/batch-01-receipt.json：exact arguments、actual、输入 SHA、真实行数/总字节/consumed 与 remaining。累计新报告记录 G1/G2/G5 实际覆盖；未覆盖保留 Incomplete，Spec/Quality 分别报告。
- 不新增产品修改、测试、SQL、运行或自动重跑权限。独立 R319 RED 和 R322 batch2 可以继续。不得把 observer 修复的 R319 结果混作 R317 世代源码相同，最终 T2 仍需相应独立审阅闭合。
