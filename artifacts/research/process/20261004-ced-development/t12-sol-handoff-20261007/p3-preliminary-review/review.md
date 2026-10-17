# P3 independent preliminary review

Status: **PRELIMINARY — no new substantive defect identified in the reviewed R92 product changes; not final software approval.**

Reviewer: `/root/astra_delivery_boundary` (requested gpt-6-astra), different from implementer `/root/sol_t12_p1` (GPT-6.1-sol). R95 successfully routing this review is not itself review acceptance. This review only reads frozen P3 materials; no R93 active source was reviewed.

## Findings and scope

No new actionable product-semantic issue was found. The known R92 scope-proof failure and test import-order I001 remain unresolved evidence pending R94, not waived. R94's completed plan/root review authorizes only the precise new-test import ordering plus proof/runner repair; its future execution is not assumed successful.

- `configs/research/ced_roles.yaml:9`: normalized_1000 is the sole YAML change; 320×240 and grasp v2 remain. `vision/role_models.py:192–195` retains the real profile temperature/max_tokens and adds strict `think: False` to the frozen snapshot; it does not hardcode all profiles to 0/512. Existing max_tokens=777 assertion at `tests/test_rgbd_role_models.py:144` is unchanged.
- `vision/planner.py:435–445`: compatible serialization adds `enable_thinking` only if `think` is present. Its value remains the strict bool checked by unchanged `model_resolver.py:81–91`; no snapshot mutation, no internal think wire key. No-setting/no-snapshot generic compatible stays the previous five keys. Ollama's separate pop-on-copy path and paid-before-send rejection remain unchanged.
- `vision/role_models.py:229–250`: request binding includes snapshot evidence, hence think false→true changes its request hash. The two new runtime-binding tests at `tests/test_ced_runtime_binding.py:337` and `:353` reject changed current source/settings; they do not let historical Max success confer current authority.
- `tests/test_rgbd_role_models.py:1076` mocks only urllib's external opener. The normalized test at `:1153` constructs real CPU 320×240 PNG/metric-depth input, uses actual factory/messages/planner/request serialization, checks two distinct image payloads, normalized prompt and (500,500)→(160,120), plus grasp v2 and request binding. Its current RED stops at the expected old pixel field, so its positive serialized wire is **not yet observed**; this is a required R94 GREEN check.
- The cost test at `:1249` explicitly makes three calls, two TimeoutError then success; no production automatic retry was added. It checks distinct IDs, all sent/received bytes, statuses, all-request totals and remote monetary_cost=null. Its frozen cost-export independently has 3 distinct attempts, TIMEOUT/TIMEOUT/SUCCESS, 540 sent + 212 received = 752 bytes; all three bill amounts are null.

## Evidence checked

All five current sources match both the R92 source-freeze hashes and exact source-after bytes. Reviewed the complete five-path diff and relevant before/semantic-after/after bytes; formatter-only portions are textually consistent with the plan. **This review did not execute a replacement AST proof.** Final restricted-scope equivalence still requires R94's exact TypeIgnore/tag/assignment proof, four mutation rejections and precise import-only change.

Independently parsed original RED JUnit: 11 unique cases, expected 3 failures and 8 passed controls, no error/skip; raw stdout and actual exit1 receipt agree. The three failures are normalized pixel and missing serialized enable_thinking for false/true. The six added named test functions implement the registered 1+1+1+2+5+1 denominator. Generic missing settings/no snapshot, both Ollama controls, paid-disabled, current-source change, thinking hash change and timeout/all-sent/null-bill controls are present.

All 56 CPU original files (72,850 bytes) match the declared SHA/size; all 56 still-existing temporary originals match their preserved copies. The 13 captured fake HTTP boundaries include 9 simulated inference sends and 4 Ollama telemetry requests; they are CPU fixtures, zero real network/model calls. Exact read-only observations and limited input pins accompany this report.

## Required final re-review

1. R94 final current/frozen five-source hashes and exact delta: only specified new-test import order; three R92 product changes unchanged, old assertions protected.
2. Actual repaired restricted-scope proof and fail-closed runner receipts; retain original proof/Ruff failures and original sequence deviation.
3. Ruff, format-check, mypy and original-budget GREEN actual receipts all exit0; JUnit covers all 11 new cases and reports actual total unique selected tests. No new RED/formatter/extra GREEN.
4. Final CPU wire/cost originals, source/diff/report pins and budget accounting. Do not infer GREEN or current actual qualification from this preliminary review.

Old 35 real calls stay historical. Current role/source qualification still awaits the later P8 final source freeze and ROOT's separately activated cold+3warm probe when applicable; weight/revision unknown remain null. Software, real role qualification, physical and formal status stay separate.

Review actions: product/test edits0, product imports0, test/static executions0, network0, Git0, spawn0. Only this new preliminary-review directory was written.
