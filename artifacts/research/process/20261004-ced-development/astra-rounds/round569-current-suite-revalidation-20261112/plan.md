# R569 Current Seven-Case Execution Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans; complete CPU implementation and one fresh review before actual execution. The user authorized continued development and fresh revalidation. No repeated design-approval question is needed. This Astra planner performs PLAN ONLY.

**Goal:** Run the unchanged fixed seven-case interface suite on the verified absence/P03 repairs with a new sealed source identity and truthful independent/cumulative accounting.

**Architecture:** Extend the existing harness with an explicit optional execution-plan binding at preregistration, creating a distinct current registry schema. Legacy registry behavior remains fixed to its old policy. All workers and offline verification validate the sealed current binding, while reservations, events, classifier, causal and historical-time checks remain the existing implementations.

**Tech Stack:** Existing Python/pytest harness, R545 runtime overlay, Molmo2-ER and unchanged selected Sol profile; no installation or package/model change.

**Spec:** This round's `request.json`, AGENTS.md and the original R558/R561 policies. Actual planner `gpt-6-astra`; planning source `d222d3556ccdafbe89babdc3673156da6e735c08`. Exact22 current inputs plus1 external manifest were read and SHA/byte verified; machine-readable manifest is in `plan.json`. Full plans/bindings/raw remain local.

## Evidence, problem and root cause

`probe_molmo_multiscene.py` fixes `ROUND` toR558. Its preregister CLI and `_check_sources` read old absolute input paths, while `preregister` and `_registry_check` fix prior counts4/10/2. R558's preserved integrity report records cumulative actual7 loads/27 generation starts/4 paid attempts; R566–568 added zero calls. A new run cannot use old source identity or unused old budget.

A second directly related identity constraint is `verify_molmo_multiscene_archive.py`: it fixes harness SHA `b27df4b4dfc4015e940ca807e6f1e72b56f3058a7b70d4f7268baa8e8df3a262` and source commit `75f5a991fe16549843177a1fa79c76cf1914e741`. New harness sources need an explicit versioned verifier identity branch, not overwriting historical constants. The historical tracker interval scope already avoids current-clock false rejection without changing clocks; reuse it unchanged.

The existing R558 launcher calls R545 `configure_overlay()`. R545 derives WORKTREE from its location, binds native Python/import proof and prepends current src; its bytes and proof are present here. No launcher/runtime monkeypatch, package fix, new download or replacement is necessary. All24 old required input paths can be mapped under the current worktree and currently exist; these mapped paths are the new source inventory's minimum inherited coverage, **not** a claim that old hashes match new code.

## Global constraints and boundaries

- Modify only the harness/source-identity boundary, independent verifier's versioned identity selection and tests. Do not change vision, parser, geometry, pipeline, roles, SDK, calibration, source/refusal allowlists, clocks or final admission.
- Keep GROUPS `G1=(N01,N02,P01)`, `G2=(N03,P02)`, `G3=(N04,P03)` and CAPS8/6/6. Keep the exact7 case payloads, scene/task/asset parameters and their original stable request labels; fresh root_id, registry SHA and run_id distinguish executions. No case exclusion, selection, retries or increasing caps.
- New maximum3 loads/20 generation starts/3 paid reservations/attempts, retries0. Prior7/27/4, cumulative maximum10/47/7. Expected successful-path actual3/19/3 (groups7/6/6 points) is a forecast, never an assertion replacing actual counters. Reservations and started/completed/request/response/parsed counts remain separately recorded; errors and unknown transmission consume the applicable allocation.
- Main-thread sequential isolated worker processes; one resident model per group; same resource/shared GPU lock and group/ledger locks. No model prewarm/generation outside accounted workers. No group restart after a claim, even a failed preflight or crash; preserve partial results and NOT_RUN rows.
- Capture paused MuJoCo scenes with once-only apply_scene and raw aligned depth. No step/settling/physics rollout or hardware dispatch. Current-source full closed-loop MuJoCo work is a separate successor Astra plan after interface audit.
- Keep old4/7 archive, all prior manifests and failed summaries immutable. No inference replay disguised as fresh captures, no timestamp/clock rewriting, no reason-string-only expected rejection.
- Known unrelated full-project Chinese-docstring failure remains documented. New unexpected implementation/runtime failures require another actual Astra plan before repair; independent safe work may continue. Expected RED below and the already-known strict historical summary clock limitation are not new repair mandates.

## Minimal interfaces and schema

Retain legacy calls unchanged. Add keyword-only `execution_plan: Path | None = None` to `preregister(output, cases, source_hashes, *, execution_plan=None)` and optional `preregister --execution-plan PATH`. No new worker budget, replay, resume or override flags. Omitted plan retains legacy schema/prior and old source policy; do not silently upgrade old registries. The current preregistration CLI obtains its sources from the already-frozen execution file rather than recalculating and accepting drift.

Use new registry schema `molmo.interface.r569.v1`, with `run_id="r569-current-suite-20261112"` and `execution_plan={"path": absolute_path, "sha256": digest}`. Its `prior` is7/27/4 and `source_hashes` equals execution file's exact map plus the execution-file's own repo-relative path/digest when that file is within ROOT. Do not use a mutable global ROUND, monkeypatch `_check_sources`, rewrite old_checks, or bypass `_registry_check`.

Implement a small `_load_execution_plan(path: Path) -> dict[str, Any]` and/or `_execution_for_registry(registry) -> dict[str, Any] | None` in the same harness; no new framework. Use the existing strict JSON reader (duplicate keys and nonfinite constants rejected) for this new trusted-input boundary. Require ordinary non-symlink files, well-formed hashes, exact types (bool is not int), safe relative source paths with no traversal/symlink escape, correct raw root and distinct fresh output. Validate prior/caps/schema/run_id strictly against this R569 policy; arbitrary user-supplied budgets or self-declared priors are not accepted.

The **post-review**, local-only `execution-plan.local.json` is a separate immutable run binding, not a rewritten Astra input plan. Required fields:
- schema `molmo.execution.r569.v1`, run_id above, source_commit (new reviewed committed harness HEAD, not planning HEAD), worktree_root, new_raw_root;
- `astra_plan` ref to immutable R569 plan.json with SHA; `prior_evidence` ref to original R558 real-run-integrity.json with exact intake SHA, mapping loads7/generations_started27/paid_attempts4; `prior={loads:7,generations:27,paid:4}`;
- additional_max3/20/3, group caps8/6/6, retries0, hardware_dispatch false, physical_formal NOT_RUN, canonical fixed-case payload digest;
- exact `source_hashes` for the `required_source_paths` list in R569 plan.json. Include R545 launcher/proof, existing R558 launcher, inherited R558 sources, R561 policy, unchanged current production stage modules, role/calibration, modified harness/verifier/tests and this Astra plan. Missing or altered required sources fail closed. The execution file excludes itself from its own map to avoid a hash cycle; registry seals its bytes. No future mutable summaries/logs are source inputs;
- runtime paths: exact native/CPU Python and R545 overlay/proof refs; model directory; asset manifest path/SHA and26-file count; model-store path/profile ID, SETTINGS_SHA and roles YAML SHA; existing shared GPU lock path. Store no secret value or credential/DB content.

`_registry_check` selects only recognized legacy/current schema policy, then continues all existing case, group, cap, claim/event/reservation and source checks. For current schema additionally re-read/hash the execution ref, verify its R569 plan, prior evidence and source map equality; reject edited/resealed registry priors or budgets, missing binding or unknown schema. `_check_sources` uses frozen required current source map for current schema, retains its exact historical behavior for legacy. Before each current worker delegates anything, compare its CLI model directory, asset manifest, model-store path, profile ID and lock with execution binding and validate manifest SHA; original resource/profile/provider checks still execute. Do not weaken generation/model asset checks to an identity declaration.

The required source list refers only to existing implementation files plus the one planned new test; final admission is covered by the existing pipeline/grounded-planner sources and final-admission tests, not a newly invented module. The source_commit is frozen after code/tests/review commit; source byte checks remain authoritative throughout actual run. Bind/verify the tracked frozen source subset against that commit before registration. No source-affecting changes until final audit. Publishing later reports can create a later commit without retroactively changing recorded execution source commit.

## Task1 — Execution identity and prior accounting

**Modify:** `scripts/probe_molmo_multiscene.py` only at preregister, source/registry validation and worker argument admission. **Create test:** `tests/test_molmo_current_execution.py`. **Small fixture extension permitted:** `tests/test_molmo_multiscene.py` optional current execution binding for recorded CPU suites, leaving default legacy tests intact.

- [ ] Recheck23 intake hashes and planning HEAD; record existing relevant baseline before edits. The pre-edit harness+archive baseline was inspected:106 passed in52.42s (`baseline.local.log`). Original R545 launcher preflight was inspected:IMPORT_AND_CPU_ABI_PASS,0 loads/generations/paid,cuda_initialized=false (`runtime-preflight.local.stdout`); retain these as baseline and repeat final identity/resource preflight after reviewed code freeze. Preserve original harness/verifier bytes or hashes and original failures. Source implementation may change only the two approved scripts and three test files listed in this plan.
- [ ] Write meaningful current-binding RED tests: new preregister flag/schema preserves exact7 and writes true7/27/4; current source inventory resolves under current ROOT without reading old absolute workspace; successful bound current worker stub starts only after complete admission. Assert every inherited case payload is equal and each source absent from the plan is rejected if required.
- [ ] Add negative tests for tampered source/current plan/execution ref, changed prior evidence or counters, bool/negative/extra cap values, changed group order/case digest/raw root, missing required source, escaping/symlink path, mismatched profile/model/manifest/lock and old-schema registry with current prior. Assert zero provider construction/paid calls on all pre-admission failures.
- [ ] Run RED before implementation. Expected failures are absent keyword/CLI option/new schema support or rejection of a legitimate current binding by old prior/source logic; assertions demonstrating unsupported input acceptance are also authorized RED. Existing ledger/classifier/legacy regressions must remain green. Unexpected errors need a new Astra round if not an explicitly planned assertion.
- [ ] Implement the bounded schema/source selection above. Keep reservation/event numbers, stage source hashes and classifier logic byte-equivalent wherever practical. No generalized arbitrary counter setter or global override.
- [ ] Run GREEN and existing harness tests. Verify exclusive root/claims, no restart/concurrency, capacities, poison/finalization, native counter reconciliation and paid0 negative behavior still hold under current schema via at least one CPU recorded-suite run. Arithmetic control: prior7/27/4 plus actual3/19/3 is10/46/7, while cap is10/47/7; unspent1 generation never becomes a retry allowance.

## Task2 — Versioned independent archive identity

**Modify:** `scripts/verify_molmo_multiscene_archive.py` identity dispatch/report fields only; `tests/test_molmo_multiscene_archive.py` and existing recorded-suite test helper as needed.

- [ ] Add RED tests that a complete current-schema CPU archive verifies with its registered reviewed harness SHA/source commit, and any mismatch between actual harness, execution map or registry fails. Do not replace HARNESS_SHA256 globally or relax source comparison. Check unknown schema fails and legacy schema retains the original fixed historical harness SHA/commit requirements.
- [ ] Change verify_archive to read schema and validate its appropriate identity: legacy retains frozen constants; current invokes the validated current execution binding and compares actual imported harness file SHA to its registered source digest. Report the correct original execution commit and expected/actual harness identity for that schema. Every manifest/event/refusal/field comparison and historical interval boundary rule remains unchanged.
- [ ] Update the synthetic delayed-archive fixture to create an authentic current binding rather than pretending modified harness bytes are the old frozen legacy hash. Add a legacy negative identity test and keep legacy registry/case semantics tests. Tests may construct temporary fixture manifests, but actual CLI uses only the sealed reviewed binding; no production verifier bypass hook.
- [ ] Preserve tests demonstrating later wall clocks do not rewrite frame timestamps, original online tracker still rejects stale captures, scope restores original methods, bound stage endpoints reject invalid intervals, and raw bytes/mtime do not change. Native/provider/capture/paid calls are forbidden in verifier tests.
- [ ] Run combined harness/current-execution/archive regression and pertinent perception/planner/final-admission tests; scoped Ruff and diff checks. Perform one fresh independent whole-diff review covering no-bypass source validation, prior arithmetic, source/hash cycle avoidance, admission ordering, legacy identity and zero clock/gate changes. Address only in-scope expected implementation issues; new causes require new Astra plans.

Commands (CPU interpreter from intake):
```bash
PYTHONPATH=src /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest -q tests/test_molmo_current_execution.py tests/test_molmo_multiscene.py tests/test_molmo_multiscene_archive.py
PYTHONPATH=src /home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m pytest -q tests/test_molmo_point_association.py tests/test_molmo_pointing.py tests/test_molmo_grounded_planner.py tests/test_molmo_final_admission.py tests/test_molmo_revalidation.py tests/test_rgbd_top_grasp.py tests/test_molmo_grounded_cli.py tests/test_rgbd_capture_session.py
/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python -m ruff check scripts/probe_molmo_multiscene.py scripts/verify_molmo_multiscene_archive.py tests/test_molmo_current_execution.py tests/test_molmo_multiscene.py tests/test_molmo_multiscene_archive.py
git diff --check
```
All scoped commands must exit0. Do not claim unrelated full-project GREEN or add overlapping test counts.

## Task3 — Freeze and preflight before actual calls

- [ ] Commit/push verified safe code/tests and sanitized plan summary by explicit paths, verify local/upstream/remote SHA. Record this commit as execution source. Do not stage full plans, runtime/private paths, raw or manifests. Create the local execution binding only after final code/review; then do not modify frozen sources.
- [ ] Freeze current23 inputs plus required source map, R545 launcher/proof and runtime identities, all26 model assets by original manifest path/bytes/SHA, old raw inventory (423 including index; retain prior422 distinction), and immutable R558 prior-integrity evidence. No package/SDK/model writes. Retain before/after evidence in local-only round directory.
- [ ] Run existing R558 launcher `--preflight` using exact native Python `-B`; require IMPORT_AND_CPU_ABI_PASS, current-worktree module paths/hashes, exact validated torch/transformers/numpy/cv2/pydantic/cryptography identities, baseline.pth identity and cuda_initialized=false. This imports modules only and consumes no load/generation. Do not test model creation outside a worker.
- [ ] Verify selected profile exists and secret presence only through existing `_profile`; require unchanged Sol settings hash `eb31dd5eb394646e1a09a0116c7d8d58c954a8c200f2443d12b5ce3ef972362d`, selected role config and model snapshot. No secret/DB export and no test paid request. Record only sanitized hashes/presence. No profile switch.
- [ ] Check new raw root and external registry do not exist, are outside old raw root and writable with ample output disk. Preserve existing resource thresholds: shared lock present, no foreign compute process, GPU free>=12000MiB, RAM>=8GiB, model-volume free>=60GiB. Also check output-volume space without reducing original resource policy. Existing `_admit_resources` rechecks and holds shared lock for each actual group. Read-only preflight must not steal/recreate/delete a held lock.
- [ ] Preregister exactly once with explicit execution plan; record registry canonical bytes/SHA/root_id, fixed cases and source commit. Verify registration sources before any worker, no accidental old registry reuse. Zero actual budgets consumed until durable reserved/start events.

## Task4 — Actual fixed-seven execution and audit

The user continuation authorizes this bounded new native/cloud run **after** Tasks1–3 pass. Run exactly three sequential worker processes, G1 thenG2 thenG3, never parallel. Each calls the existing launcher and unmodified inner pipeline/resources. No new load or generation merely to inspect responses.

Use the exact paths below (shell variables are task-specific, quoted; setting them is not running work):
```bash
R569_DIR="$PWD/artifacts/research/process/20261004-ced-development/astra-rounds/round569-current-suite-revalidation-20261112"
R569_NATIVE='/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/ordered-small-vlm-20261109/runtimes/molmoer-r505/bin/python'
R569_CPU='/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python'
R569_LAUNCH="$PWD/artifacts/research/process/20261004-ced-development/astra-rounds/round558-multiscene-grounded-interface-20261110/implementation/launch_multiscene.py"
R569_RAW="$PWD/datasets/model-cache/molmo-current-suite-r569-20261112"
R569_MODEL='/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/ordered-small-vlm-20261109/models/Molmo2-ER'
R569_ASSETS='/home/ningyd/文档/ChatGPT/BIGsmall/artifacts/research/process/20261004-ced-development/astra-rounds/round505-ordered-small-vlm-screen-20261109/candidates/04-molmoer/asset-manifest.json'
R569_DB='/home/ningyd/文档/ChatGPT/BIGsmall/data/model_control.db'
R569_LOCK='/home/ningyd/文档/ChatGPT/BIGsmall/datasets/model-cache/zdtaichu5-9b-fp8-round473/research/.r468-r469-gpu.lock'
"$R569_NATIVE" -B "$R569_LAUNCH" --preflight
"$R569_NATIVE" -B "$R569_LAUNCH" preregister --output "$R569_RAW" --registry "$R569_DIR/registry.local.json" --execution-plan "$R569_DIR/execution-plan.local.json"
"$R569_NATIVE" -B "$R569_LAUNCH" run-group --group G1 --registry "$R569_DIR/registry.local.json" --output "$R569_RAW" --model-directory "$R569_MODEL" --asset-manifest "$R569_ASSETS" --model-store "$R569_DB" --profile-id profile-4f24f5330ad644ad --gpu-lock "$R569_LOCK" --allow-paid
```
Capture each process stdout/stderr/exit separately in exclusive local log files. After G1 completion/accounting/locks exit is inspected, run the **same** run-group command with `--group G2`; inspect, thenG3. These are the only allowed substitutions. Functionally failed but evidentially valid cases remain rows; independent registered cases/groups may continue if existing ledger/resource gates permit. Unknown native/cloud transmission, corrupted source, broken ledger/resource or unplanned runtime cause stops dependent work and requires a new Astra plan; never rerun a claimed group. Leave all seven denominator rows, including NOT_RUN.

- [ ] After every group inspect native load starts/completions, generation starts/completions, point ordinal continuity/caps and all paid reserved/delegated/request-observed/response-observed/parsed counts. Record failures and unknown transmission conservatively, never equate received body with numeric HTTP status. Verify worker exited and lock release before next group.
- [ ] Run strict original summarize CLI once, preserve its output/exit (0 means all-case-pass,2 otherwise). Known N02 historical tracker clock issue may make strict summary invalid even though original runtime rejection is valid; **do not patch clocks or overwrite summary**. Then run independently version-bound archive verifier into a new derived directory; exit0 means valid evidence, not all7 passed:
```bash
"$R569_NATIVE" -B "$R569_LAUNCH" summarize --registry "$R569_DIR/registry.local.json" --output "$R569_RAW"
PYTHONPATH=src "$R569_CPU" scripts/verify_molmo_multiscene_archive.py --raw-root "$R569_RAW" --output-new "$R569_DIR/archive-verification"
```
- [ ] Audit exactly7 unique IDs, positive3/negative4, all case/group seals and causal event chains, source hashes/commit, queried raw binds and classifications. Positive success requires original PLANNED contract plus validation/post-cloud genuine fresh capture/final admission; negatives require actual legitimate ABSENT or validated original geometry refusal and zero cloud entry/paid. INVALID, model exception, freshness or resource failures never count as expected rejection. Full native/paid raw remains local.
- [ ] Compute new actual and reserved counts from durable events/provider records, add true prior7/27/4 separately. New max3/20/3, cumulative max10/47/7; expected3/19/3 only when the actual native paths support it. Keep unspent budget and stopped cases visible; no carryover.
- [ ] Recheck all26 assets, original archive inventory, frozen current sources/runtime proof and new raw seals; workers exited, GPU foreign-compute state and resources restored. Write local exact full inventory and separate sanitized results/accounting/integrity/phase summary. Do not claim a complete remote raw reproduction package.
- [ ] Explicit-path commit/push sanitized verified results; confirm local/upstream/remote SHA equality. Preserve execution commit separately from delivery commit. Report actual seven-case fraction and blockers plainly, including valid-suite versus all-case-pass, software versus native/cloud versus physical/formal layers.

## Review focus and acceptance

The fresh reviewer must check: malicious/resealed execution/registry cannot lower prior or raise caps; current source admission cannot fall back to legacy globals; model/profile/lock/runtime binding precedes load/paid delegation; changed harness identity is authenticated without weakening legacy checks; historical time interval scopes remain offline and restore original methods. Tests above cover these conditions plus exact fixed7 and no raw mutation.

Development success requires scoped tests/lint/diff and fresh review. Runtime acceptance requires authentic fixed7 evidence and honest outcomes, not necessarily7 functional passes. Only valid evidence **and** actual3/3 positives+4/4 negatives permits claiming all7 interface validation passed. It still proves no physical stability, full closed-loop motion, real robot task success or formal research acceptance. N04 is a synthetic paused occlusion case. A successor Astra plan should bind the resulting reviewed current source and define bounded current-source MuJoCo motion/closed-loop evidence separately, retaining user-selected visible markers, top-view camera and controller architecture. No physical execution is authorized here.

## Planning verification

All22 local +1 external intake byte/SHA values were verified before this plan. Existing24 inherited source paths were checked to exist under current ROOT. This planner changed no code/test/runtime/registry and made zero model/cloud/physics calls. Machine-readable `plan.json` holds exact inputs and mandatory runtime source paths. Revalidate applicability before implementation, and again freeze final post-review hashes before actual run.
