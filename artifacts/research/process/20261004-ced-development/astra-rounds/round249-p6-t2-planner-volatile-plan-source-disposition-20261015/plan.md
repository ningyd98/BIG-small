# R249 — 易失计划源处置

实际作者：`/root/astra_status_plan`，实际模型：`gpt-6-astra`。状态：仅计划，等待 ROOT 接受。

R248 编排调用从旧 store 取得 undefined，随后 JSON 克隆抛 SyntaxError。失败前未调用 nested 工具、未启动子进程、未写 R248 计划；不存在可报告的子进程退出码或独立流。完整原始 JS 未事前冻结，其缺口保留为 null；原件只声明真实前缀与可见错误。

放弃该失败调用和旧 store 路径，不重放、不恢复易失对象、不补造全文。ROOT 核对本计划及三个输入后，才允许 Astra 从固定物理 R242 plan.json 完整读取、核 SHA，再以当前显式局部值编制 R248。完整候选先持久保存，再形成一致的 MD/JSON；不得把旧计划中的预算或世代当作当前事实。

R247 仅作为同类持久源原则参考，其历史 HELD 状态不覆写 R242 已消费三槽的事实。R248 仍须绑定 ROOT 最终结算的真实输入，并保留 R245 精确缺失证据边界。R249 不放行任何产品修复或验证。

本轮新增执行、产品、测试、审查、Git 槽均为 0；不新增核验 helper，不改任何源码、账本、阶段状态或旧原件。仅正常文本/JSON/字节哈希门。冻结本计划后 STOP，等待 ROOT 接受。

## 固定输入

- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round249-p6-t2-planner-volatile-plan-source-disposition-20261015/original-planner-transport-failure.json` — 1997 bytes；SHA256 `49f55459dcb5103c7860d5f01b1fd4a7895e7d406bdfa61048977ca116d0b405`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round242-p6-t2-writer-barrier-condition-synchronization-20261015/plan.json` — 22524 bytes；SHA256 `f6d8aef8b1e7ee62aadaa55c95b8a465878d7eda46fe6e48f27f4d7a0c945137`。
- `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round247-p6-t2-runner-durable-source-preparation-20261015/plan.json` — 8972 bytes；SHA256 `f41799aace2040e325652775d375a0d8df4ba05717060bcd1adf74113bb5ca72`。

原始失败保存 native 返回为 `{}`，不能称 numeric exit 0。正常输入读取 d176f5、c38da3 均实际 exit 0。身份比较仅 path/bytes/sha256，其他属性原样保留。

验收只恢复 R248 规划资格；legal RED、T2、T12、native、formal 均未完成。详细执行边界以同目录 plan.json 为准。
