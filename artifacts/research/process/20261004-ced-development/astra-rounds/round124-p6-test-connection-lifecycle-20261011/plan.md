# R124：A20 测试自建 SQLite 连接生命周期补齐

实际 Astra 规划，2026-10-11。只读源发现，不是RED/GREEN或运行时失败。

## 事实与根因

冻结稿SHA `4ccdc0a50b459485db27ea1d14626652b8ab1171a580c9bac1f386f1de227eae` 与当前测试一致。文本枚举确认恰好五处直接sqlite3.connect：_rows、_all_sql、acquire holder、restart foreign-live更新和legacy expiry更新。它们仅依赖Connection事务上下文，没有显式close；事务上下文提交/回滚并不关闭连接。这不满足R113 plan第67行每测试关闭自有资源、第73行保留清理证据的要求。未执行连接probe或导入产品。

原RED已用1/剩0，后七命令各0/1；冻结finding/index/test/ledger保留。source-index中的生产快照只是已有冻结资料，本轮不读取或将正在修改的生产字节设为新前置。

## 限定修改与关键事务边界

只修改原test文件上述五个连接生命周期，必要时增加stdlib contextlib.closing导入。采用外层closing/try-finally确保连接最终close，同时保留内部原Connection事务上下文；异常、断言、return路径同样关闭。**不能只把事务with替换成closing**：两个UPDATE fixture还须在后续独立读/恢复前完成原成功提交，close本身不会替代commit。

保持publication_guard锁序、connect参数/isolation_level、SQL/值、真实BEGIN IMMEDIATE/ROLLBACK、barrier顺序和所有断言不变；事务退出先于close，close先于guard退出。_rows/_all_sql在关闭前完成结果物化。不要修改repository签发的view._connection及rollback/CAS0/connection_close/commit_close/ack/replay真实负例；不吞异常，不增加改变可见性的commit/rollback。

## 执行步骤

1. ROOT checks frozen finding/index metadata, current test equals snapshot SHA and snapshot ledger red1/0,other7x0/1. Confirm same author pause on test/validation. Do not rehash/read current production sources for R124 activation.

2. Same replacement author updates only five test-owned connection lifetimes plus necessary stdlib import. Preserve transaction contexts and original explicit failure injections. Save R124 mapping-change.json limited diff and before/after test SHA; do not overwrite frozen finding/test/ledger or earlier mappings.

3. Complete original R113 writer/issuer coverage table and short-transaction/cleanup text self-review, save semantic-before-format bytes after intended edits. This is original preparation, not another product command or proof invocation.

4. Resume original remaining seven commands exactly once each and in R113 order: import_sort,formatter,scope_proof,ruff,format_check,mypy,green. Original single scope proof includes these five closes and unchanged semantic contract; do not add connectionprobe/compile/import/collect/test/static. RED remains consumed and never reruns.

5. Final source/evidence freeze and different-author review must verify no open test-created direct connection and original actual transaction/negative-path semantics remain. Any new root cause or unexpected failure stops for new Astra; no retry/budget reset.

## 验证和验收边界

ROOT可保存R124 activation/input-check、限定mapping-change和步骤报告。原20节点/参数/测试目的全部保持，不增加连接probe、compile、import、collect、测试或静态运行。原scope proof在唯一已有额度内覆盖资源关闭及事务语义，原GREEN20与独审尚待。独立R113文本自审和writer映射准备不受影响。

本轮不改生产、旧helpers、计划/原件或预算；新异常先停相关修复并交Astra。通过也只属于 `LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO` 软件准备，不宣称P6/native/actual/formal验收。所有输入SHA/bytes、五处原始行和完整预算见plan.json。
