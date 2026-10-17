# R122：A20 草稿的既有 P5 API/handle 映射修正

实际规划者：gpt-6-astra。日期：2026-10-11。只修正原20节点测试草稿对冻结P5接口的引用；生产实施仍仅原R113范围。

## 原始发现与独立核实

作者已冻结 `R113/implementation/stage-a/stopped-test-api-mapping`。核9项evidence-index全部SHA/bytes一致；当前四旧生产源及草稿与快照一致，新operational_lease不存在。作者42d9dd/657aa7只读工具combined输出仅在会话，source-evidence.json是原源码摘录，不冒充工具raw。

独立解析原RED invocation/result/raw/JUnit：原精确argv/cwd/env与R113相同，stdout/stderr哈希匹配，20个指定节点全在缺operational_lease断言处FAIL，0error/skip。下游错误映射尚未实际运行到，不能称其已有运行时失败或被RED验证。RED已用1、剩余0；另七预算各0/1，不重跑。

根因是草稿猜测了P5公共字段，而已冻结实现仅有私有owner及指定window/deadline/token接口。另foreign线程先取owner.clock会被P5属性守卫提前拒绝，不能证明OC1检查；ROOT已同意将此作为同一草稿handle映射修正。未发现需要修改P5产品语义的依据。

## 限定映射

- `runtime.operational_owner` → `runtime._operational_owner`。All affected references in the single A20 test file. Assert actual owner exists; do not add public compatibility property to product.

- `owner.export() / runtime.operational_owner.export()` → `owner.export_record(owner.task_window)`。Require original task_window exists; use detached original task record in renewal/restart evidence. Compare before/after record byte-equivalent contents, including hard deadlines/source/origin. Do not synthesize owner/window.

- `owner.task_deadline` → `Actual original _Hard.deadline selected from owner._hard using exact source_id owner._startup.job_source + ":task" (must uniquely match)`。Read-only use of original issued handle. Retain original task and verification hard deadline handles and compare identity/fields after heartbeat; deadline.origin must be owner.task_origin, not reconstructed from exported dict or numeric ns. No start_deadline/new origin for this check.

- `owner.origin_token` → `owner.task_origin_token`。Require original token non-null; read_current(after=that same original token) on original owner thread; before_deadline(original_deadline,current) signature unchanged. Set explicit CPU raw counter to original deadline_ns, retain strict equality rejection.

- `foreign thread accesses runtime.operational_owner.clock property before begin_event` → `Owner main thread first obtains genuine owner.clock handle; foreign thread invokes begin_event on that exact saved handle`。P5 property would otherwise reject before entering OC1; actual same handle must reach OC1 wrong-thread check. Retain existing main-thread domain/copy assertions, real thread/native identity and explicit error; do not accept P5 property rejection as OC1 coverage. Keep this destructive OC1 negative after required positive checks and allow normal terminal cleanup; never reissue owner to hide revocation.

## 执行与验证

1. ROOT rechecks exact frozen evidence/index and current A20 SHA, four old production hashes/new operational_lease absence, relevant P5/OC1/plan pins and original RED ledger; save R122 activation binding actual replacement identity /root/p6_stage_a_sol. Current RED output/tmp exist and are immutable; do not reassert their absence. Remaining seven command output leaves/tmpGREEN/mypy must still be unused before invoking them.

2. Same author changes only mapped references/local read-only captures/assertions in original A20 draft. Preserve all20 exact nodeids/parameter IDs, test purposes, real transactions/threads/permission checks and evidence. No new tests, skipped nodes, rewritten RED, compatibility product APIs, mocked verdicts or new deadline issuance. Record concise before/after mapping and edited-source SHA in R122 metadata.

3. For original task deadline, preserve genuine _Hard.deadline and task_origin_token created by real startup; compare unchanged original record and handle identity across heartbeat. Current receipt must be read from same original OC1 clock after same origin token. Equality test advances explicit CPU counter only, not task origin/deadline or UTC. For foreign-thread negative, capture real clock on owner thread before passing exact handle to foreign.

4. Continue original R113 production work and remaining seven commands in original order: import_sort, formatter, scope_proof, ruff, format_check, mypy, green. Each original authorized1/used0/remaining1 is inherited; red remains1/0 and must not rerun. No extra product import/compile/collect/test/static proof or standalone mapping probe. Original scope proof includes bounded mapping diff and existing20node invariants within its single budget.

5. Freeze semantic-before-format after intended mapping and original implementation, then use original import/format gates; preserve original stopped draft as historical input, do not claim raw RED ran on corrected bytes. At original GREEN20 classify any new failure and stop for fresh Astra before repair. Final independent review verifies this mapping and full original A contract; A remains LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO.

## 保留与边界

本轮唯一新增修复权限是原 `tests/test_operational_runtime_closure.py` 内上述映射、实际handle捕获及原始引用断言；不增加节点、不改既有helpers/P5/OC1、不加产品兼容别名、不重新签发deadline或owner、不用mock许可。原源码、草稿、RED和发现证据全部保留。输入SHA/bytes和逐项核查完整见plan.json。

后续生产代码仍沿R113原6路径，不因本轮扩大；新writer身份/解释器/预算继承R119/R120。原单次scope proof应覆盖限定差异和20节点，不新增一个单独probe/compile/import/collect/static运行。修正稿并未重新RED，报告须明确原RED对应冻结旧稿。

遇新根因、范围扩大、预算/输出漂移或计划外失败，停止相关修复并交下一实际Astra。GREEN/静态/范围/独审未过前无A验收；即便通过也仅 `LEASE_FOUNDATION_WITH_LEGACY_UTC_VETO`，不代表P6/native/actual/formal。规划者未运行产品或Git、未改生产代码。
