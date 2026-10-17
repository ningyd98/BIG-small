# R162：作者准备报告模板恢复

> 实际 Astra：gpt-6-astra（`/root/astra_status_plan`）。ROOT 激活后，仅恢复元数据保存。

原 functions.exec 在发出 shell 前返回 ReferenceError。完整可见 wrapper 错误已保留；完整失败 JS/candidate、cmd、嵌套返回和独立流缺失，不能重建。未转义 Markdown backtick 终止模板是原件支持的原因假设，不是已恢复的完整源码事实。原失败未写任何目标文件。

本轮给出新明确蓝图，不复现失败程序：作者通过一次直接 tools.apply_patch 写四个已确认不存在的 R158 准备产物：t1/fixture-map.json、budget-report.json、step-report.json 与 executor-report.md。精确路径、字段和六项输入 pins 见 plan.json。不使用 String.raw/Python/Markdown 嵌套模板或新 helper。测试、runner、ledger 全部保持当前字节。

报告必须如实写 PREPARATION_UNEXECUTED_HELD_R163：七个 T1 节点/预期均属未运行合同；15命令0已用且HELD。新 R163 当前 publication 夹具问题独立待处理，不在本轮修复，不声称 legacy control 通过或报告已可执行。

随后只执行一次 plan.json 中的标准库 metadata 核查：六原输入、原80556字节 A 测试前缀、15命令零消耗状态以及四新产物的 JSON/bytes/SHA。保存完整实际返回和捕获边界。任何产品导入、AST、静态、测试、Git 或额度重置均禁止。

原失败、临时保存目录及旧报告原字节保留。本轮成功仅准备元数据连续性；ROOT 与 R163 门仍需各自完成。新异常立即停并交下一实际 Astra 计划。
