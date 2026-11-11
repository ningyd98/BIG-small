# R558 首次独立整体实现审查

**结论：暂不具备真实运行条件；Ready to merge: No。** 共 5 项 Important，0 Critical，0 新增 Minor。此报告是本轮首次审查中断后的继续，不是第二轮审查，也不是修复计划。

审查基线 `8a8057e7f2089401ad64906b7fc1efe29cee5ca2`；三个新增文件的完整快照和 SHA 在 `review-evidence/`，24 个冻结输入全部匹配，已有 tracked diff 为空。未修改生产源码或 Git。

## Strengths

- Fixed seven static cases, order and 8/6/6 caps match the registered plan; scene data is confined to rendering and saved setup, with explicit task/RGBD/capabilities entering the planner.
- Exclusive fresh roots, fsynced reservation writes, group flock/no-restart claims and per-case quotas prevent ordinary duplicate execution/reallocation. Negative cloud entry is intercepted and explicitly fails.
- Original production adapter/pipeline returns are preserved; positive classification checks contract, production validation, fresh/final admissions and four point completions over two same-session captures. Existing runtime overlay, profile settings hash and source checks are reused.
- Baseline HEAD is 8a8057e7f2089401ad64906b7fc1efe29cee5ca2, tracked diff is empty, all 24 plan input hashes match, and the 29 existing new-harness CPU tests pass.

## Critical

无。

## Important

### R558-I1 — Invalid original depth is incorrectly accepted as expected visual rejection

位置：`scripts/probe_molmo_multiscene.py:507`（相关行：409, 523）。

The stage wrapper labels any ValueError visual unless a short substring blacklist matches. The original PointAssociationError text "native association pixel has invalid original depth" does not contain contiguous "invalid depth". classify_case therefore accepts a sensor/depth fault as program_geometry success.

**复现证据：** reproduction-results.json:R1_invalid_original_depth uses actual run_case, original PlanningPipeline and original associate_target_point with a validated RGBD fixture whose selected pixel has zero depth. Returned REQUEST_MORE_OBSERVATION reason is the invalid-original-depth error; both native POINT fixture results bind correctly; recorded visual_rejection=true; verdict=PASS_EXPECTED_REJECTION.

**影响：** Inflates the fixed negative pass rate and violates explicit R558 classification exclusion of depth/context/calibration/runtime faults; this is not evidence that ambiguity or occlusion was correctly rejected.

**最小修复边界：** Use positive stage-specific structured evidence/error identities for the permitted original geometric refusals, default unknown errors to ERROR. Preserve causal gate and complete exception identity/evidence. Do not broaden this blacklist or modify production thresholds/functions. Add regressions for original invalid-depth, camera/episode/calibration/TTL errors and allowed geometry refusals.

### R558-I2 — Actual generation and paid accounting disappears on exception exits

位置：`scripts/probe_molmo_multiscene.py:569`（相关行：362, 378, 672, 683, 691, 848）。

Actual generation delta is emitted only in the successful point end event. An exception after generation start/completion records only runtime_error, so classify_case sums zero while group provider counters increase. paid end is likewise emitted only after parsed _post return: a received malformed response is omitted from paid_responses, and no group paid actual/reserved/unspent reconciliation exists.

**复现证据：** reproduction-results.json:R2_provider_failure has group generations_started=3/generations_completed=3, but case actual_generations=[0,0,0]. supplement-results.json:malformed_received_cloud invokes original _post with a fake HTTP response containing invalid JSON: response-0001.json is saved and one paid reservation exists, yet paid_responses=0 and paid start has no terminal event.

**影响：** Failure costs cannot be reconciled by case/group or distinguished from conservative reservation. Hard reservation caps still bound delegated work; the issue is incorrect actual accounting/evidence, not demonstrated budget overrun.

**最小修复边界：** Record per-attempt terminal success/error in finally with before/after started/completed native counters, reservation ID, request binding and raw reference. Reconcile per-case totals with provider group counters and reservations. Separately expose paid reservation, delegated transport attempt, received bytes/response, parsed success and unknown transmission state; do not infer actual paid send from reservation alone. Include aggregate reserved/actual/unspent/stop reasons and retain failed native/cloud originals.

### R558-I3 — A failed resident provider is reused for later cases

位置：`scripts/probe_molmo_multiscene.py:837`（相关行：572, 857）。

run_group continues after every case/native exception unless ledger.fatal or budget_block is present. The point exception wrapper does not mark provider failure fatal. Native raw persistence failure, CUDA/runtime failure or deadline failure can therefore reuse a provider with uncertain resource/state/evidence integrity.

**复现证据：** reproduction-results.json:R2_provider_failure injects OSError after each fixture generation completes. All N01/N02/P01 delegate to the same provider (three calls), status=COMPLETED, despite the first provider failure. This executes the actual run_case/group control flow with no native model/network.

**影响：** Violates worker_lifetime contract requiring provider/load/resource corruption to stop the group and keep remaining fixed rows NOT_RUN. Further model calls consume bounded allocation after an unsafe-to-reuse failure.

**最小修复边界：** Distinguish independent ordinary case refusal from resident provider/evidence/resource failure. On the latter set a durable group stop condition and do not delegate subsequent cases; keep omitted IDs in fixed denominator with NOT_RUN/INCOMPLETE. Preserve counts and original failure. A parse INVALID returned normally need not be equated with corrupt provider state.

### R558-I4 — Ledger persistence failures outside _write do not stop the group

位置：`scripts/probe_molmo_multiscene.py:341`（相关行：293, 298, 303, 322, 843）。

record creates its directory outside the guarded persistence block. begin_case/end_case and ledger lock/list/read paths also have no centralized fatal transition. A directory creation failure can be recorded as a case runtime error later, leaving ledger.fatal=false and allowing subsequent delegations.

**复现证据：** reproduction-results.json:R3_ledger_mkdir injects event-folder mkdir OSError and observes fatal=false. supplement-results.json:ledger_failure_continues injects a one-shot event mkdir failure in the actual group flow: N01/N02/P01 all acquire case-start files, N02/P01 subsequently delegate native fixture calls, and group status is COMPLETED.

**影响：** The promised fail-closed accounting boundary is incomplete. A filesystem/ledger fault can consume further model allocation after evidence integrity has failed.

**最小修复边界：** Treat every ledger persistence/integrity operation, including directories, locks, claim writes, enumeration/read and end markers, as one fatal boundary. Once poisoned, reserve/record/begin operations must not permit new delegation; stop group conservatively even if best-effort error reporting succeeds. Release locks in unconditional cleanup. Add a group-level fault regression for one-shot mkdir and claim/end failures.

### R558-I5 — PASS and suite summary do not require closed, complete original evidence

位置：`scripts/probe_molmo_multiscene.py:362`（相关行：393, 405, 443, 463, 768, 918）。

classify_case counts terminal-looking events without validating matching start/reservation/terminal closure, raw hashes, native evidence or causal order. Negative ABSENT also requires neither capture evidence nor actual_generation_delta=1. _manifest only inventories files that happen to exist. summarize/CLI trusts verdict strings alone without checking registry identity, case expected/group binding, group terminal integrity, manifests, raw files, counters or passed consistency.

**复现证据：** reproduction-results.json:R4_unclosed_events uses an original CPU PLANNED pipeline response with otherwise passing end events and an unmatched extra point start; verdict remains PASS_PLANNED. R4_summary_missing_raw invokes actual summarize CLI on a fresh registered root containing only seven result rows with passed=false and PASS verdicts: no claims, events, captures, native/cloud originals, pipeline returns or group reports exist, yet exit_code=0/all_cases_pass=true. Its new manifest silently inventories the remaining registry/lock/result files.

**影响：** A partial copy, lost raw evidence or interrupted accounting can be certified as seven-case success. Fixed denominator/duplicate handling alone does not meet the contract that evidence/accounting gaps override every PASS.

**最小修复边界：** Add a shared evidence validator before case PASS and final summary. Verify operation IDs/start-terminal pairing, reservations, expected query hashes and frame/session binding, provider/raw-result identity and hashes, full original requests/captures/native/cloud/pipeline response, group completion and count reconciliation. Validate existing manifests against required expected files instead of regenerating a success manifest over a partial directory. Reject category/group/request/passed contradictions, preserve unknown/duplicate records as invalid evidence, and verify root/registry identity in summarize. Keep valid failures and missing cases visible rather than manufacturing PASS.

## Minor

无新增项；已知导入排序由 R559 处理。

## 验证与证据

- Existing new harness tests: 29 passed in 1.32s. `review-evidence/existing-tests.stdout`。
- CPU probes: `reproduce.py`、`supplement.py`，原始 stdout/stderr、完整返回/事件及计数 JSON 均保留。
- 模拟 provider 计数/假 HTTP 仅用于失败路径复现；实际模型加载/生成/付费均为 0/0/0。没有渲染、硬件或正式研究运行。
- 三个受审源文件完整快照、24 输入 SHA、基线与 tracked diff 证明见 `review-evidence/input-sha256.json`。

## Declined to judge

- Actual seven-scene visual/model/cloud outcomes, real native latency/ABI/GPU/resource admission and real selected credentials were not exercised: scope is independent read-only CPU review; parent real preflights remain required.
- Physical stability of the suspended N04 occluder, robot control and formal research validity are outside this paused synthetic capture validation; no hardware/formal acceptance is inferred.
- Existing frozen production algorithms/thresholds and historical unrelated full-suite/docstring failures were not redesigned or repaired; reviewed their interactions only.
- Known Ruff I001 import order is assigned to actual Astra R559 with exact-diff/AST-equivalence checks, so it is not a new Important finding here.
- Seven-scene renderer preflight and guide update were assigned to the parent in parallel; this review does not certify those not-yet-inspected results.

## Assessment

**Ready to merge? No. Real run can start? No.**

Five Important fail-closed classification, accounting and evidence gaps must be repaired under a new actual Astra plan before real model/cloud allowance is used. This is a review, not the required repair plan. No production code or Git state was modified.

Parent consolidates all five findings into one new actual Astra plan, performs one bounded repair pass and targeted regressions against these retained CPU probes. Do not claim CPU evidence as real native/cloud success.
