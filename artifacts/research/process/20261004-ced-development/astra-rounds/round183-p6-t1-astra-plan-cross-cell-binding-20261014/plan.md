# R183：Astra 计划保存的跨调用绑定恢复

实际规划者：`/root/astra_status_plan`；模型：`gpt-6-astra`。2026-10-14。仅本轮计划，等待 ROOT 激活。

原调用实际发生 `ReferenceError: edges is not defined`，位置 `exec_main.mjs:53:11`。错误在 JavaScript 构造 Markdown 时、任何 apply_patch 调用之前。此前完整 JSON 草稿已进入 store。functions.exec 每次使用新 isolate，前次局部 edges 不存在；这与 R180 输出截断解析、R181 字符串语法错误是不同根因。

没有 shell、child numeric exit 或独立 stdout/stderr。完整可得 wrapper 和精确表达式保留；未事前保存的完整调用文本为 null，不重构。两份 R182 plan 当前仍不存在。

## 已冻结输入

- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round183-p6-t1-astra-plan-cross-cell-binding-20261014/original-failure.json` — 953 bytes；SHA256 `7cba990a7df62b7bc0f7ac264698cae52f67bfd1492fc80a1e89c771d65b3519`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round183-p6-t1-astra-plan-cross-cell-binding-20261014/source-snapshot.json` — 136098 bytes；SHA256 `82100de3713beccb61ceeb0da87d40d3cbb6a4552890c6c72337d899fad96c5d`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round182-p6-t1-recursive-local-projection-closure-20261014/input-observation.json` — 83405 bytes；SHA256 `a29eacd682fe9d7c7b609ba7a20da4d383574d0f895aa0678f7b7ff64e36e90d`。

source-snapshot 是完整候选：255 inputs、6 commands，contract.semantic_edges 为4项对象列表，字段 edge/position/accepted_nested_tag/rule；不是已批准 R182。

## 最小恢复

1. ROOT 全文读本计划，核对3原件和两个目标缺失后单独激活。当前不执行恢复。
2. Astra 在同一个新调用中声明所有变量，从已保存 plan.contract.semantic_edges 读取4项，不引用历史局部 edges。仅一次直接 structured apply_patch 首次写 R182 plan.md/plan.json；JSON必须逐字等于 source-snapshot，MD完整表达同一合同，不增加范围或预算。使用本cell的行数组/JSON.stringify，不复演失败调用，不嵌套 shell/Markdown 模板。
3. 唯一一次 .venv/bin/python 标准库核验：只读3原件+2新计划，核原件未变、JSON逐字一致、实际255/6/8RED/13GREEN字段，并输出两文件完整pin和短摘要。先store真实结果再显示；不读产品、不AST/import/compile/probe/test/static/Git。
4. 直接 structured apply_patch 保存本轮 step-report.json，保留实际返回和pins；完成后STOP交ROOT审查真实R182。不得称已激活修复。

所有新写入仅R182两计划和R183步骤报告；原source-snapshot、failure、input-observation不可改。任何新失败/字段不符/目标已存在立即停，不重试。

## 边界

新增元数据保存1次、核验1次；新增产品/测试/静态/Git/网络额度0。R179剩四槽仍HELD0/1，R1583spent12HELD、R175三spent不变。唯一Sol保持停止。本轮成功仅表示已保存原候选计划，不表示T1、B9、T12、native、physical或formal通过。
