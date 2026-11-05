# R437 三项独立审查问题的修复核对

唯一 fresh review 由实际 gpt-6-astra 完成；原审查提出三项 Important，其原报告保持不变。本文件是实施者依据 RED→GREEN 与实际诊断的修复核对，不冒充第二次独立审查或改写原审查结论。

| 原问题 | 反例与修复后的行为 |
|---|---|
| F1 停止窗口允许外线程命令 | RED 中夹爪命令成功穿透。GREEN 中另一线程的夹爪和 step 均在效果前拒绝，夹爪 ctrl 仍为 0.039，物理步数为 0，原主异常与内部停止 CONTROL 均保留。豁免仅在当前线程的内部 CONTROL 调用期间生效。 |
| F2 observer 独立失败未关闭 guard | RED 中 COMMAND BEGIN 异常后命令成功返回。GREEN 覆盖 COMMAND/CONTROL/PHYSICS × BEGIN/END：BEGIN 对应效果为 0，END 保留 1 次效果，原异常对象向外传播，会话关闭并停止；无 guard 对照保持原语义。另核对 source snapshot 失败、STOP observer 二次失败和不可打印异常。 |
| F3 诊断遗漏停止/快照失败 | RED 缺少失败归并入口。GREEN 使用真实软件 backend 生成的 guard-events：先失败后恢复仍为 FAIL，纯预期到期拒绝仍为 PASS，overflow closure 内的附加失败不丢失。真实诊断在计算 status 前调用该归并。 |

三项 RED 均是预期 call 阶段断言失败，setup/teardown 正常。最终合并 GREEN 为 162 PASS、1 deselected；静态三项通过；唯一真实诊断为 1 PASS、实际 2 步、无附加错误。原始证据和哈希见 fix-verification.json。R437 计划要求不再派第二 reviewer，本轮遵守。
