# R115 — Git 状态与冻结计划对账

实际 Astra（gpt-6-astra）计划；仅 ROOT 后续执行 Git 元数据交付。本轮不激活 P6，不修产品、不运行验证。冻结后不得改本计划。

## 问题与证据

用户要求做好 Git 整理和推送。隔离分支已交付 P5，但现有三份状态文档还含 P5 早期停点。保留历史字节，加入 plan.json 中精确的新段落。P5 postpush 小收据经完整读取，仅含 Git 与验证摘要，可供复核。

交付父级为 `a08794857dc6ec40cec897250c62d845f396493c`；ROOT 的 3ef193 已确认本地/上游/实时远端一致且 clean。916db7 对比的23个 tracked runtime/config/test路径与交付字节一致；ba9a89另核新P5模块、测试、三fixture共5文件一致。这些是 ROOT 已报告观察，本计划不伪造独立 Git 命令结果。

R113 原前置93e262因过宽进程断言退出1，尚未激活/保存before/写产品；八项验证均0已用。R114已经冻结针对性元数据恢复方案，当前仅交付计划和原始只读证据，不执行该恢复或启动P6。PID的旧快照不是终止证明，不干预进程。

## 精确范围

共23路径，详见 delivery-manifest.json：R113根部7文件及startup-stop3文件；R114的4文件；Sol P6 API只读报告2文件；P5 postpush小收据1文件；交付工作区三文档；本轮plan.md、plan.json、manifest三文件。17份冻结文件逐条SHA/bytes在清单和JSON中。

三文档为 `docs/current_authoritative_status.md`（标题后插入最新段）、`docs/research/t12-git-delivery-20261008.md`、HAND/phase-summary.md（后两者追加）。JSON的document_edits包含完整插入字节、原baseline SHA与预期结果SHA；只在交付工作区执行。主树全局文档不改、不复制。较早文字均保留其历史时点。

不包含产品、测试、配置、active-state、source/before副本、完整raw/CPU、DB、凭据、权重、SDK。计划中的引用不会递归扩大文件清单。清单不是完整远端复现包。

## 最简执行顺序

1. ROOT复核双计划与manifest、17原件、三个交付doc baseline和分支父级/clean/祖先。要求4d40祖先、用户1007非祖先；保留主树和脏嵌套。R115三个自文件以本地独立activation收据固定最终SHA，避免自引用。
2. 明确路径复制冻结文件，原同字节可复用，不同则停。按JSON插入三段一次；已为预期结果时复用，禁止重复append。逐文件核对最终23项SHA、bytes、mode，只解析JSON并审查文档，无产品import/test。
3. 精确路径stage；核对staged路径全集和每个blob。完整cached whitespace check一次保存真实exit；strict仅三文档+R115三自文件一次，必须0。完整check可0或因原样证据为2；逐行登记原件异常、source/staged/line SHA、原因，未分类必须0。禁止strip、ignore或改attributes/config。原始片段不可执行。
4. ROOT审完整diff，单独metadata commit，正常nonforcepush同分支。复核新commit父级、三SHA一致、clean及祖先隔离。postpush/步骤报告留本地 HAND/delivery-git-reconciliation-round115，不再扩成新提交。

## 预算与验收

新增产品测试、compile、Ruff/format/mypy、模型、actual、formal均0。仅元数据/hash/JSON/doc/staged审查及whole/strict各一次；R113预算不消费、不重置。本次记录P5既有32唯一用例与candidate compile12+3PASS，不能称本次重跑。P6规划47节点含两条最终native正链，未激活且未通过。完成仅指23项有限元数据提交、推送及三SHA/clean；不代表T12整体或真实研究完成。
