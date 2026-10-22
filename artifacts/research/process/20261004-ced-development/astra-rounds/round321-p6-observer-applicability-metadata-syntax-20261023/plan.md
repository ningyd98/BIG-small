# R321：R319 applicability 元数据语法接续计划

> 实际规划模型：gpt-6-astra；仅规划，沿用 ROOT 元数据复核和 Sol 单写者。

**问题：** R319 applicability 生成器原调用 7bdabe exit 1，在报告字典的 `fresh_R317_reads` 中遗漏字段值：`observer_change_waits_fresh_source_comparison` 后没有 `:True`。Python 解析即停止，没有任何脚本语句、产品代码或测试执行，没有 report/ledger/source 写入。原始调用和错误全文保持在 R319/reviews/applicability-generation-failure-actual.json。

**输入与只读核对：** input-observation.json 保存精确输入及 SHA256。13 个 R319 输入均一致；R317 世代清单的 32 行 current/frozen 均一致；四个 R317 ROOT/AUTHOR 键均 SPENT 1/0，ROOT 已接受两次合法 RED 和两次 GREEN。R319 applicability、implementation 及三个运行输出均 absent。完整生成器已读；仅补该值后的 AST 解析通过；save 的换行为单个 LF，不需改转义。以上均为只读文件/语法核对，不执行生成器。

## 限定一次接续

- [ ] ROOT 复核输入仍适用、预期 applicability 输出仍 absent，R319 原执行前置继续成立。
- [ ] 从冻结失败回执读取 invocation.arguments.cmd，将唯一字面量 `'observer_change_waits_fresh_source_comparison'}` 替换为 `'observer_change_waits_fresh_source_comparison':True}`，替换计数恰为 1；其他原逻辑不改。
- [ ] 可在 `out=save(` 前追加唯一 provenance 赋值：report 引用 R321 plan.md、plan.json、input-observation.json 和原失败回执的 pin。不修改原 R319/R317 计划、原失败或运行额度。
- [ ] ROOT 读修正后的完整命令后，仅执行一次元数据接续。预期 exit 0，独占创建原 R319/reviews/plan-applicability.json；保留 exact arguments/actual 到 R321/reviews/applicability-continuation-actual.json。
- [ ] 核对输出 JSON 可解析、13 输入/四项结算/32 行世代的检查保留、provenance 正确。随后按原 R319 进入 source-only preparation；测试仍须原 RED/GREEN 门禁及逐键 ROOT reserve/settle。

## 边界

本轮新增 runtime/test/SQL/修复权限和运行槽位均为 0；不重跑 R317 四键，不重置任何 SPENT。R319 原三 once 配额及 observer 修改须合法 RED 后实施的顺序不变。独立 fresh R317 剩余审阅继续，不受本语法修正阻塞。新错误/输入漂移/已存在输出应保留现场并暂停相关步骤，不覆盖或自动重试。本轮元数据成功不代表 observer 已修复或 T2/P6/正式研究通过。所有输入原件保持，ROOT 按既有授权最终显式路径交付。
