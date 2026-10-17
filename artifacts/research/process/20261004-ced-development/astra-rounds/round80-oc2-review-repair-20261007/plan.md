# Astra Round80 — OC2 预审两项修复计划

**状态：待 R79 实际冻结激活；当前无执行授权。** 本计划不假定 R79 通过、不编造未来 source SHA。ROOT 必须按 plan.json.activation 完成实际字节/收据核对并生成独占 activation.json 与授权后，Sol 才能开始。

## 原始发现

冻结报告 MD SHA `8b04e3e0a2294992cb401ec320009ab20f779390a094da2c90308efc00c92d27`；JSON SHA `aade5721d12a8f5811f4a9bd3a19376f9c12c550d7991acc402a30d9bb599b2b`。两项均为静态反例，审查者和本规划者未运行注入。

OC2-PR-01/P1：preregistration 原 ValueError 后，startup-failures.json 的 OSError 可越过裸 raise，外层把报告异常标成 PRIMARY 并改变 worker 分类。

OC2-PR-02/P2：reader 未读 returned_acquisition_id。改成不存在 ID 并仅重算该文件 receipt SHA/bytes 仍可能通过；返回帧也可指向另一来源。合法 returned/source 可不同，必须校验保存的原始关联，不能直接要求 ID 相等。

## 修复合同

### OC2-PR-01

_prepare_source_v1 appends an unclassified preregistration failure then directly writes startup-failures.json inside except. A second write exception escapes before bare raise; runner only sees/relabels it PRIMARY.

1. Add one private registry field on _LiveApplicationV1, preregistration_primary: tuple[BaseException, int] | None = None, for exact exception object and already allocated failure_id; this is internal one-shot handoff, not public authority.
2. In _prepare_source_v1 except, replace the legacy role-less append with _failure_row_v1(record, "preregistration", error, primary_id=None) before any report write. Store (error, row["failure_id"]) in that field.
3. Write startup-failures.json once via existing _failure_write_v1 with phase="startup_failure_persistence" and same primary_id. That helper marks durable evidence incomplete and records OSError as linked SECONDARY without throwing it over the primary.
4. On failed startup report write, try existing _persist_failure_stage_v1(record, record.output, primary_id=id) once as a new distinct append-only sidecar, not a retry/overwrite. Wrap this fallback so an unexpected fallback exception is recorded as SECONDARY with durable flag false and original error is still re-raised. Bare raise in the original except must execute; no new raised wrapper exception.
5. At first runner preserve(), consume and clear preregistration_primary if present. Reuse its original exception/traceback/id rather than adding a duplicate PRIMARY; if the currently caught error is a different object, retain it as linked SECONDARY. When no pending preregistration primary exists, keep the existing _failure_row allocation path. Subsequent cleanup remains the existing secondary path.
6. Preserve exclusive file semantics, source_called/once guards, failure_id uniqueness and all original error text/types/terminal classification. Do not retry startup report or modify old artifacts. Direct Task1 _prepare callers still receive the original exception and can inspect persisted sidecar or in-memory incomplete evidence.

### OC2-PR-02

reader never accesses current.returned_acquisition_id; checking only source event/D/S/age leaves recorded returned-frame identity and source relation unaudited.

1. Add a narrow pure helper _current_source_event_v1(current: dict[str, Any], frames: list[dict[str, Any]], captures: list[dict[str, Any]]) -> dict[str, Any] near reader helpers. Any is only the existing heterogeneous JSON value contract; no cast or suppression.
2. Require current returned/source IDs to be nonempty str. Resolve exactly one saved returned frame by acquisition_id; compute its original_source = frame["source_acquisition_id"] or frame["acquisition_id"]. Require original_source equals current.source_acquisition_id; do not compare returned ID directly with source ID.
3. Resolve exactly one source frame and exactly one CAPTURE event for original_source. Require the source frame and returned frame interval_id equal operation-<source_event.operation_id>. Derived frames copy the original interval in VisualRawRecorderV3._record_transformed_observation, so distinct returned/source IDs can pass this relation.
4. Return the selected existing source event. In verify_operational_prefix_originals_v1 replace only the current source next(...) lookup with this helper call after existing full frame/manifest checks. Keep all following token/domain/sequence/episode/S/bracket/age logic, previous full denominator checks, persisted-frame comparisons, and unavailable live authority unchanged.
5. No schema change required: referential integrity belongs in reader where frames/events exist. Do not loosen allocation counts or enable new transformed-frame production/acceptance in the broader OC2 recipe. The helper permits a valid distinct-ID relationship; this alone is not a claim that a synthetic derived slab passes all existing full-reader recipe constraints.

## 实施顺序与次数

1. S1 Complete activation exactly as specified; do not execute tests or edits while R79 pending. ROOT assigns GPT-6.1-sol sequentially on the same two OC2 files after previous ownership handoff.
2. S2 Freeze actual activated source-before and append only the four counterexample test cases. No product change yet. Run review_RED once, expected four failures and no errors/skips; preserve complete originals. A different cause/shape is a new Astra stop, not a reason to adjust tests until red.
3. S3 Implement PR-01 exact primary object/id handoff and protected report writes; implement PR-02 narrow pure relation helper and one reader call substitution. Append direct/derived pure helper controls for post-fix verification. Existing tests/assertions/fixtures and R79 config guard remain untouched.
4. S4 Review every hunk and produce coordinate-specific scope proof; explicitly record behavior changes (primary preservation and rejection of broken returned joins). Do not claim whole-AST/runtime equivalence. Reverting only registered AST fields/except/preserve/helper/call/new test nodes must recover activated modules; no global stripping or old-assert removal.
5. S5 Run specified Ruff check/format on two changed files and original four-source mypy once each; failure preserves raw output and halts. Then run review_GREEN once:4 new counterexamples+2 helper controls+7 affected existing cases=13, all pass, no error/skip. No R03, R79 targeted8, full63 or broad prior suite repeat.
6. S6 Freeze new sources and bounded evidence; retain full new CPU success/failure/partial denominator and local DB boundaries without claiming full remote raw package. Write step-report.md/json, original review counterexamples as static provenance plus new real RED/ GREEN evidence, count ledger and remaining limits. Return to different-actor independent reviewer; author cannot self-accept or authorize actual/Git.

精确命令、命名测试/参数、注入方式和断言见 plan.json。新 RED 一次4例全部失败；post-fix GREEN 一次13例通过。纯 direct/derived helper 控制仅在实现后运行，不能用旧源码不存在helper伪造RED。R79 targeted8、已完成R03、历史63额外重跑均为0。

## R79 激活与待冻结清单

1. Wait for ROOT R79 terminal notification. If R79 fails unexpectedly, do not activate R80; next Astra handling of R79 takes priority and requires this plan applicability reconsideration.
2. Read only completed R79 frozen source and command artifacts. Verify actual SHA/bytes, freeze linkage to source-after, R79 controlled AST changes, declared exactly-once runs and full actual acceptance; do not infer from filenames/status prose alone.
3. Immediately before R80 first edit, compare current prefix/capture test bytes to actual R79 source-after and record their actual SHA in activation.json. Verify unaffected schema/capture/worker/CLI/source helper/test baseline pins against immutable reviewed snapshots. Do not pin active RW1 or ROOT progress.
4. Pin every actual R79 result used, both R80 plan files and all active source/test inputs in activation.json; then ROOT writes separate exclusive root-authorization.json referencing plan+activation hashes. These explicit actual bytes complete the implementation input set; no placeholders or hashes copied from old source as if future source.
5. Only after ROOT review and authorization may Sol execute the R80 RED/repair sequence. Activation is metadata only and grants zero product/actual run before the authorized sequence.

- step-report.md/json and failure/terminal receipt or equivalent final status
- source-freeze.json plus source-after for prefix and tests/test_operational_capture_v1.py
- source-before/diff/restricted scope proof proving only the exact R79 config guard + appended two-parameter test changed since R75/old test
- config_RED raw command/stdout/stderr/JUnit: missing FAIL, changed PASS, zero error/skip
- ruff_check and ruff_format_check raw results exit0
- mypy four-source raw result exit0
- targeted_CPU raw command/stdout/stderr/JUnit:8 pass, zero failure/error/skip
- R03 raw result/JUnit:pass with observed case count, zero failure/error/skip
- R79 output/test run count ledger and before/after bounded inputs

该 activation.json 将记录真实 R79 两源SHA、完整用到的R79命令/结果/JUnit SHA和R80计划SHA。当前只绑定既有不可变规划输入；没有任何未知未来SHA。若R79发生新失败，停止激活、交下一实际Astra重新评估，不跳过剩余门。

## 验收边界

At most author verified after actual R79 activation, preserved expected RED4, static pass, GREEN13 with complete receipts/failures and bounded scope proof. Independent final review still required.

本轮actual=0、formal未验收；实际来源前置、独立gates、ROOT单独真实运行授权保持。新派生ID正控制只证明纯关系校验，不证明完整派生raw有效，不放宽既有recipe/分母。保留所有旧失败/CPU原件/数据库交付边界，清单不冒充完整远端包。

## 已实际读取的不可变输入

| 路径 | SHA256 | 字节 |
|---|---|---:|
| `AGENTS.md` | `8567e10635a650e2619905d6b3a6e0a885812060fecb1cdd4487bbf118593649` | 1774 |
| `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/oc2-independent-review/preliminary-review.md` | `8b04e3e0a2294992cb401ec320009ab20f779390a094da2c90308efc00c92d27` | 6830 |
| `artifacts/research/process/20261004-ced-development/t12-sol-handoff-20261007/oc2-independent-review/preliminary-review.json` | `aade5721d12a8f5811f4a9bd3a19376f9c12c550d7991acc402a30d9bb599b2b` | 35320 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round79-oc2-backend-config-type-20261007/plan.md` | `288e8ee01dba97af76e39339c033e386db7e9f1884cb662e3535e6ab6fa70eb9` | 23966 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round79-oc2-backend-config-type-20261007/plan.json` | `bc57e73b493c75f287bd4d048c42ff02dd8419b93b115cf7d3657bb807d52143` | 44687 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round79-oc2-backend-config-type-20261007/root-authorization.json` | `401cbd7b80ffc95e5ab5c499cc7d10e13d699f0caae2b4970d2a41ccaa0ac32e` | 22279 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round75-oc2-residual-type-20261007/implementation/failure-receipt.json` | `ae12bbe535439ac2512ccd6cf9327df236231bcda6abfb56390a7a0eeb1f73bf` | 4639 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round75-oc2-residual-type-20261007/implementation/source-freeze.json` | `183ffed66b2834d5d708cf41ed99b38f2a99de00d92e82405a50dbb8ffee3002` | 175 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round60-operational-oc2/plan.md` | `7cabb71aec1c4d485d6505a060ed227b5a810ae71d325e6b4fbc66da41d160b9` | 22261 |
| `artifacts/research/process/20261004-ced-development/astra-rounds/round67-oc2-green-partials/plan.md` | `62bc42d4e638fb3e0f7d423f3d6752c0e8818c2ed1adfd926e8cf71f549f2f47` | 39566 |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/source-after/scripts/run_operational_prefix_v1.py` | `fe8e8c9e021ec437b601895de724f1d10f17eb221fea6b8302c304a65fbcffa9` | 1885 |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/source-after/tests/test_operational_capture_v1.py` | `ebe63baa223a7f2dc1f99fc28603ceb3ae9505516085c605ef0dbb2a39fa6aaf` | 18729 |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/source-after/tests/test_operational_prefix_cli_v1.py` | `f3cc2a0d2de8fb18dbcfa3c9b9969d92f657fd03b448b7cda7c58d5926480cfc` | 6546 |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/source-after/tests/test_operational_prefix_v1.py` | `1ccb56de190f5cea0280882690bead41ed15aaff0fdfa2b74b32ca9c5cd1b426` | 11934 |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round75-oc2-residual-type-20261007/implementation/source-after/src/cloud_edge_robot_arm/research/operational_prefix_v1.py` | `8ae58cf74fc7278462ac2b0d5a64b87b60b35e53d8879e6c48e97c9e01c76cd3` | 60216 |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/source-after/src/cloud_edge_robot_arm/research/operational_capture_v1.py` | `06373a9c702420ab38c5afa20f888efb35cd6ea109cf094c662fa04511e60b3c` | 14778 |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/source-after/src/cloud_edge_robot_arm/research/operational_prefix_schema_v1.py` | `918e029a6a1f0d2a7a455820c721118abdb50b7c5eda6e8ee15f54bed543e67c` | 11537 |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round74-oc2-static-typing-20261007/implementation/source-after/src/cloud_edge_robot_arm/simulation_runtime/worker.py` | `31cea6501ee9286ee933335f013422314985726036c8029844929cc96be2fdb4` | 80239 |
| `/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-repair-execution/OC2/implementation/task2-3/round67/implementation/sol-handoff-20261007/source-after/configs/research/operational_prefix_v1.json` | `c1d51bb28376f9a2c7e636efe16a0675d426951b8ed8849ead78d342f4b3ada1` | 394 |
| `src/cloud_edge_robot_arm/vision/raw_recorder_v3.py` | `4eabd3bf9cdf15b3942c4a740781a95c22ea684f410853c853d0336952d7a303` | 44175 |
| `src/cloud_edge_robot_arm/simulation/config.py` | `ece5dba5a710f63ba46bc99260ae768cec07c2773e7e0687bd2f55a4758f1d7b` | 2078 |
| `pyproject.toml` | `b2bf5c4042d568eaf9def415ae7b2f08f0fa541a01f970b7e68e6d950035bb6c` | 2458 |

规划期间一次只读行号展示越界（请求288行，文件280行）已以min边界恢复，原错误详情保存在JSON；无产品或证据字节修改。所有产品/test/mypy/Ruff/actual/network/Git运行次数为0。
