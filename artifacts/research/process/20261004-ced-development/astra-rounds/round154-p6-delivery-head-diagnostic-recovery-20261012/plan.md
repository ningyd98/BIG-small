# R154 交付 HEAD 变化的有限只读诊断计划

实际规划者：gpt-6-astra / /root/astra_status_plan。状态：冻结，等待 ROOT 输入与脚本复核激活。仅诊断，不实施交付。

## 原始问题与独立核查

R153 `prepare-delivery.py input` 工具45bd5b实际退出1，line184断言实际HEAD等于旧基线失败。G1本身exit0，返回315fdadd8f42b0d624cafb9b5f0e4d5966a51b3e；计划旧值为cb59be66fe281d7ee2c1ca90bc803c3b80f37c76。M1/M2/M3/G1四个Git子命令均已真实执行，各exit0，其独立stdout/stderr/result/invocation完整保留。主树HEAD仍34c7a5595b72a3b23f4d0ca4d31aa4154cd6f24e。

已独立读 failure.json、四组实际 invocation/result 与raw SHA、prepare-delivery.py135–193行。代码先收集有限文件检查，然后开始Git循环；失败发生于G1后，尚未成功生成input/preflight/rootactivation，不能把内存中检查结果冒称完整成功门禁。无验收、三文件更新、copy、stage、commit或push。本问题是Git基线前置变化，不是产品测试失败。

failure.json 1291B SHA256 fe9ded65a5c54f7987652e7c3289ee6457472c0e8fe6ba8128f632fa41eae5ca。外层只有真实返回combined，不能另造独立流；Git子命令确有独立流。M3的2,623,851B NUL原件仅核SHA，不输出整份脏树列表。25个本轮直接输入及全SHA见plan.json.inputs。

## 原因假设与范围

可能是此前独立工作推进交付分支，但尚未读取commit/parents/diff，不将它当已证事实。需要确认315fd的真实祖先、内容、分支/上游/实时远端/干净状态，以及50依赖、6交付底座和当前6源码/53保护/终审仍适用。标题不能代替范围审查。

只允许新R154只读诊断脚本，不编辑/重跑旧R153脚本，不更改产品、测试、STATE/PHASE/docs或旧证据。R153 input1/0与四次实际Git永久保留；其余原额度暂停，不能当新额度。本轮新增1次stdlib诊断调用、最多13个精确只读Git子命令，命令各一次；产品、Git写入、重试额度0。

## 执行门禁

- [ ] ROOT核25直接pin、读本计划；新建本轮diagnose-head.py，仅标准库与plan.json所列Git argv，完整文本+SHA写script-gate后再激活。
- [ ] D01–D06读取当前HEAD、分支、上游名称/值、实时远端和状态。HEAD必须仍315fd；不运行fetch/pull。
- [ ] D07–D11读取commit父链、祖先关系、最多33条区间log、实际changedpaths与numstat。祖先检查exit1是明确不适用观察；不是修复授权。超过32个中间commit须停止扩读。
- [ ] 仅依据真实changedpaths运行D12安全文本diff，最多64路径/2MiB。遇credentials/SDK/weights/DB/binary等不读取内容，报告不完整并另规划；不猜模块或自动扩大。
- [ ] 核740静态输入、canonical current6/53保护、50两树依赖、6交付before基线、终审与三个状态before pins；不重扫完整fixture。使用真实JSON类型/字段，历史snapshot不硬比当前版本。
- [ ] D13复核HEAD未再变化。诊断结果独立保存到新JSON，stdout只给短摘要；保存实际raw与工具返回，不以重跑补捕获。

Git精确argv/顺序、全部路径和字段合同见plan.json。读取和结果写入均限定R154元数据；不得有产品AST/import/compile/collect/static/pytest/SQL/probe、Git修改或凭据读取。

## 后续与验收边界

本轮输出只可判定“适用于下一交付计划/不适用”，不得自动作A验收或copy/stage/push。ROOT与actual Astra读取实际诊断后，下一R155以真实新base和完整新派生路径集合恢复交付；不伪造R153成功激活，不把R154文件偷偷加进冻结的759路径。

R153740静态证据、旧计划/脚本/失败及四组Git原件全部保留为历史。未生成的19派生成功输出不补造。下一计划需显式纳入这些历史和本轮诊断，再安排有限受控验收与交付。主树dirty/index不动；无reset/stash/rebase/cleanup。任何新失败或漂移保存后停，零重试。CPU40四run和独审结论不因此失真，但本轮既不授予软件A验收，也不提升B/C/D、公开确认闭合、native/physics/actual/formal。

