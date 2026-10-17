# R284 角色描述误作路径：最小处置计划

实际模型：gpt-6-astra。仅规划，冻结后 STOP。

原 e0809e 实际 exit1：规划汇总将 failure.root_role 描述字符串 `selected RESERVED1/0 pending independent reconciliation; no refund` 交给 Path.read_bytes，在源码第16行 FileNotFoundError。此前只打印两条 STREAM_SCHEMA，未产生角色或最终汇总，未写源码、控件或运行产物。原命令/actual完整保留；独立 stdout/stderr 未提供，仍 null。

本轮直接 ABANDON 原命令、汇总和缓存。零重放、零更正执行、零替代 validator；不 strip 描述、不猜路径、不把未打印的汇总补造为成功。原角色描述继续作为文本事实。

ROOT 接受后，R281 必要普通规划读取只能使用明确物理路径白名单，或固定 R276 plan 的 `runner_contract.roles['ROOT']` 与 `['AUTHOR']`。不得遍历全部 roles.items()，不得打开任何 failure 描述值。身份仅按 path/bytes/sha256；历史角色若经合法结算改变，使用准确 fullbefore/base64/mode→after 映射，不能强制旧 pin 等于 live。

cdfe3b 已实际观察 ROOT22257/d84f…、AUTHOR22472/90c…；本轮只核其完整权威原件，没有另读 live 角色。六输入完整 SHA 见 JSON/observation。既存131944/043c…完整成功 trace/源码证据和 ROOT3aca9d摘要可复用；失败未完成的聚合不补造。

R281 行为修复、R282 可选 viewer、R283 optional marker 分属各自后续计划。本轮不恢复其中任何工作、不改变原额度、不运行产品/测试/import/AST/SQL/Git。只有 ROOT 审核后才恢复规划资格，不等于行为通过或 runtime 放行。
