# R393 研发分支限定交付前置计划

实际模型 gpt-6-astra；代理 /root/astra_r389_revalidate；2026-11-02T11:36:54.652759+00:00。当前仅计划，最终审查与R390诊断门尚未齐备，不宣称已交付。

## 新问题与有限例外

原生只读证据确认symbolicHEAD为refs/heads/main，而HEAD、main、已有research/20261004-continuation及两个origin本地ref全部为 `fdb2e94d3d7bc041e7d958f2514a08406fad4668`；索引无已暂存变更。research未由其他登记worktree占用。origin只是本地缓存，尚未实时查远端。

仅在即时同SHA、空staged、源/index/dirtygitlink保护门成立时，允许一次 `git symbolic-ref HEAD refs/heads/research/20261004-continuation`。只变更HEAD符号绑定，不checkout/reset、不切工作树文件、不创建/改mainref或其他ref。重绑后HEAD对象仍fdb2、全refs/indexhash/工作区字节及嵌套指针/dirty证据应相同。前置有差异即停，不自动修正。

两个gitlink索引与内部HEAD均ddbeb92a1aa1dfa8039f6260d6b5887c58072383；已记录完整porcelain路径状态与trackedbinarydiff哈希。未穷尽hash嵌套untracked载荷，不把这说成全raw字节审计；所有嵌套路径均排除于任何写命令。

## 最终门与选择范围

R379最终独审与R392/R390静态审查已批准；R390唯一离线分析已exit0（0.084775秒），10traces与14jobs、原DB/WAL/SHM前后hash一致，内部原因仍UNKNOWN；其因果边界最终审查与主总结仍须完成。已有R381通过、R377partial批准、marker75通过各按原scope保留。R377默认20PASS/19未满足/1原skip、research3SOFTWARE_ONLY/NOT_RUN/formalfalse以及R390未知因果不能升级。

代码/数据允许精确9路径：closure/newcommitcontract、console单字段、v2registry/两markerconsumer、assetmanifest/docsphase9/registrytest；另仅authoritative与continuation两总结。src/product和已checkpoint temporal等不改不重纳。

证据仅本次新计划、审查、步骤/紧凑验收、argv/minimalenv、JUnit/log/result、sourcehash/cleanup/spec和R390派生诊断；每个文件在新精确NUL manifest中逐项bytes/SHA/mode/purpose审核。不能整目录stage。排除完整raw/DB/WAL/SHM/forensiccopy/cache/basetemp、大量截图export/trace、legacy/frame/source重复拷贝、模型SDK权重凭据及两gitlink。冻结错误/log不为检查改字节；必要白字符例外按原hash说明。精选清单不是完整远端复现包。

## 实施顺序与预算

最终ready后开始本轮最多600秒行政窗口：冻结精确候选manifest；保存HEAD/所有ref/index/source/nestedguards；按允许工具获准执行symbolic-ref并立即验证无文件变化；literal pathspec NUL明确stage；核index路径/bytes/mode精确等于批准集合。

一次普通commit≤60秒，parent=fdb2，只更新research，main仍fdb2；无amend/-a/force。随后沿R379尚未使用的原额度：一次normal explicit-refspec push≤60秒、一次exactbranch ls-remote≤60秒；本地HEAD/上游/实时远端完整SHA相等才确认交付。R393不新增测试/诊断/网络预算，不重跑已有验证。

当前workspace-write/networkrestricted/.gitreadonly；实际Git写/网络需允许工具升级，计划不绕过审批。transport/nonfastforward/timeout失败保存本地commit与原生证据，不retry/fetch/rebase/改proxyTLS/config；未知结果只读核验，不能盲重发。push成功但远端核验失败必须标未确认。

## 留存与验收

source/index/refs即时有漂移或用户新staged内容即停，禁止reset/unstage清理用户状态。保护scene66、三markerXML、v1、temporal和历史失败。完成后原mainref保持、research指向新commit、嵌套dirty保持；不靠ignore清空显示。

提交后才产生的commit/push原生收据保存在新本地R393/delivery并在答复中定位，不递归生成第二次receiptcommit，不声称这些收据已包含在之前commit。原始raw/失败保持，交付边界与开放事项明确。完整原生HEAD/ref输出及SHA、允许路径、最终门、命令/预算见plan.json。
