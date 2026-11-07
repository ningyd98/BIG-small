# R447 — static checks and final regression repair

Actual planner: `gpt-6-astra`. Date: 2026-11-08 Asia/Shanghai. PLAN_ONLY. All original stages have now finished; source was read while frozen and no products/tests were run or edited by this planner. Fifty-two source/plan/evidence SHA256 pins, original stage output copies, failure index and source excerpts are retained in intake. Earlier results are not overwritten.

## Original evidence

R439 final-regression: **224 PASS, 6 FAIL, 2 deselected**, pytest 67.73 s; supervisor elapsed 68.56162695000057 s; child returncode 1, reaped true, no remaining_live/source_drift/ports. Ruff: 22 errors, child rc1 (19 import/unused/modern import fixes, 3 B023 loop closure bindings). Mypy: 33 errors in six files, child rc1, checking the original ten source paths. Format: child rc0, 16 files already formatted. Successful outer runner execution is not successful child validation. Exact stdout/stderr/JUnit/spec/result bytes are copied into intake.

Six final failures:

- Shield-config recording and grounding evidence-sink recording fail on JSON serialization of `mappingproxy` source hashes.
- Two R446 cases fail before their real synthetic-pixel/handoff assertions because TaskContract rejects `control_mode="PCSC"`.
- Normal guard-exit test expects one COMMAND but sees two.
- Worker-after-body failure test expects FAILED but the actual old worker reports BLOCKED_BY_ENV.

The 224 PASS does not prove the six skipped target paths. R446 marker/region failure subcases have not yet been exercised past contract creation in this final run. R443 and earlier T3 97 PASS remain separate evidence for their then-current source generations.

Root mechanisms are separable but all are exposed by the same first whole-change validation: new serialization/domain/type integration issues, two inaccurate test expectations, and two preexisting worker typing errors. This bounded repair round handles those explicit mechanisms; anything further unexpected requires another actual Astra round.

## Scope and exact fixes

Allowed paths are the ten exact files listed in plan.json: five new research modules; existing simulation_runtime/worker.py only in `_owns_artifact_publication`; and four new collection/authority/grounding/reader test files. No old backend, recorder, geometry, tracker, binding/compiler, contracts/schema, configuration, assets, validators or test filters change. Do not patch original evidence or weaken UNKNOWN, generation/assignment or source checks.

### 1. Immutable source maps at JSON boundaries

The original source maps are immutable mappings, already validated as string→SHA256 maps. Convert their representation explicitly with `dict(source_hashes)` only at the four identified digest call sites:

- native_full_horizon_recorder: record_shield_config and check_shield source_generation;
- native_collection_grounding: release_reference_registration and grounded_collection_step evidence sink.

The plain dict preserves all keys/values and produces the same canonical digest as an equal original dict. Do not mutate the original mapping. Do not change global canonical()/digest() to accept arbitrary unknown objects, repr/default=str, discard fields, coerce values, or turn errors into success. Keep R443's strict JSON equality and all original source hashes. Other digest inputs inspected are already plain payloads, detached original inputs, or existing domain digest methods; do not broadly refactor them.

Strengthen the existing Shield/sink tests to assert recorded source_generation equals digest(dict(original source mapping)). In the existing RELEASE transform test, pass an actual MappingProxyType source map and compare descriptor/digest with the equivalent plain dict; ensure the mapping stays unchanged. This extends an existing test, not a new collected node.

### 2. Contract domain values and model construction

Job/draft control mode `PCSC` is an existing experiment-runtime shorthand and remains unchanged in startup/job identity. The worker already maps that shorthand to `PERIODIC_CLOUD_SUPERVISION` at the planner contract boundary. New build_collection_contract must use `ControlMode.PERIODIC_CLOUD_SUPERVISION`, the exact old contract enum. Do not add an enum alias or alter the job's source payload.

Construct TaskTarget, SafetyConstraints and FailurePolicy using their existing typed models with exactly the same current field values; this resolves four argument-type findings and the genuine runtime enum failure without changing policy. Preserve all eight skills, original conditions, durations, deadlines and completion criteria. Existing R446 tests must then reach real B/lease/R/E compilation, fresh E pixel bootstrap, binder and independent reader checks, including all negative cases, rather than merely accepting a different exception from contract construction.

### 3. Test expectations grounded in actual sources

The backend's existing emergency_stop **always calls hold_current_joints before _emergency_stop_observed** when an observer is present. Both are original COMMAND operations. The extra hold is part of actual STOP semantics, not an unrelated fixture record to delete. Recorder.__enter__ only installs its observer and reads previous state; it does not issue hold. Snapshot any pre-guard command baseline without clearing it, then assert the exact two appended commands in order `[hold_current_joints, emergency_stop]`, original sequence/acceptance and same real TERMINATION parent for both, zero physics, and unchanged guard closure flags. Do not filter the hold, clear recorder lists or modify backend behavior. Existing exceptional/secondary-error assertions remain intact.

The injected RuntimeError in the worker-after-body test occurs inside `_run_rgbd`'s existing VISION_CLOSED_LOOP call. That old worker catches RuntimeError/ImportError/OSError and records BLOCKED_BY_ENV before propagating. The preserved actual fixture (copied and pinned in intake) has job.error_message `publication failed after body`, sole attempt result BLOCKED_BY_ENV and error `RuntimeError: publication failed after body`. Although outer _execute prefers FAILED, _settle_failure_status sees this already-terminal status outside its active set and returns BLOCKED_BY_ENV unchanged; terminal publication keeps it. The test must assert this exact actual status, original job error_message/attempt evidence and final COLLECTION_PARTIAL/teacher_admitted=false/qualified None. Make the comment or injected-error description accurately say failure after a software body inside the worker route; it is not evidence of a failure at a later publication call. Do not change worker classification or broaden the assertion to accept any status. Preserve original error text and do not reclassify it as a successful collection.

### 4. New-module typing and loop hygiene

Resolve exact current errors without adding blanket Any, ignore comments, excluded files or disabling rules:

- native_calibration_collection: annotate `groups` as `list[dict[str, Any]]`, matching the existing sink's JSON object payloads. Do not change registry denominator/output.
- native_full_horizon_originals `_restore_frame`: validate the decoded frame is a string-keyed dict and retain its type through both returns. Keep null/missing distinction, every blob/hash/schema comparison and malformed-input rejection. In physics(), use an explicit branch/raise to narrow missing reset before indexing (same original missing-reset failure). In reference(), validate/read a dict before returning rather than returning untyped JSON. In `_contact_reference`, return a typed list of Python floats from the actual computed three-vector rather than Any from ndarray.tolist; do not round/coerce nonfinite or missing input into an accepted reference.
- native_full_horizon_recorder.bind_collection_source: take a local backend episode id and explicitly reject None/empty before constructing RawEpisodeIdentityV3. Do not replace missing ids with fallback strings.
- native_collection_application: give the existing slots explicit repository/worker/output annotations, using TYPE_CHECKING concrete SQLiteSimulationJobRepository and SimulationWorker imports to avoid new runtime cycles. This annotates real factory-assigned fields, not caller-created authority. Validate protocol/policy JSON object shapes before dict-returning properties; do not discard extra keys. Narrow purpose before its `__exit__` call in the existing entered branch without skipping cleanup. Check last_captured_frame is present before post-state access and fail closed with original context if absent. Rename synthesized errors outside except blocks (`terminal_error`, `missing_body_error`, `guard_secondary_error`) so they do not reuse Python's deleted exception-target variable; preserve original primary/secondary ordering and exact messages.
- authority loop closure B023: bind stops, actual_stop and case per iteration in helper factory/default arguments. Keep the exact stop/body/purpose failure behavior and once-only calls; do not suppress the warning or remove negative cases.

Runtime shape checks at JSON/Optional boundaries should be explicit and narrow. A local cast is acceptable only after an actual runtime type check that establishes its exact type; never cast an unknown handle or use cast(Any). Existing valid inputs and event ordering must not change.

### 5. Two preexisting worker findings

`intake/preexisting-HEAD-worker.py` is the read-only `git show` original at HEAD 8534419b7e22396985f66d1b0f2714fe8e16e5fb. It already contains `_owns_artifact_publication` accessing `_local_read_scope` through the general SimulationJobRepository protocol and invoking evaluate_locked on the Optional session. These findings were exposed by the current expanded check; they are not introduced by R446 source handoff. Preserve that classification in the step report.

Repair only that LOCAL_TEMPORAL_PUBLICATION_V1 branch: retain `repository=self.repository` and `session=self._operational_lease_session` locals; inside its existing protected path validate `isinstance(repository, SQLiteSimulationJobRepository)` and `session is not None` (otherwise fail closed with existing OperationalLeaseError/False path), then use those narrowed locals for `_local_read_scope` and evaluate_locked. Keep the call in the same method: SQL validates its real caller code identity. Do not move it into a helper, change session issuance or add a private method to the public repository protocol. Keep owner._check_app_live and all same-job, lease, source and view checks. Preserve UTC_LEGACY_VETO branch behavior. The expected concrete route remains unchanged; missing session cannot grant publication.

The earlier missing-session case already fails closed in `_local_read_scope`; the narrowing makes that requirement explicit. Add a small assertion to an existing authority test that this local mode with no session refuses publication and causes no side effect, restoring any fixture mode afterwards. No new collected node, no fake positive session, and no unrelated worker refactoring.

## Implementation/validation schedule

Before changes, verify pins applicable and all original stages FINISHED/reaped. Preserve original inputs and old results. Parent implements the manual changes and strengthens the existing tests above. Run exactly one import-cleanup implementation command and one formatting implementation command, as frozen in plan.json (`ruff check --select I,F401,UP035 --fix <ten allowed files>`, then `ruff format <same ten>`). These are implementation transformations, not replacement evidence for validation; capture output and review the resulting diff. No unsafe fixes or repo-wide formatting.

Create a new R447 implementation runner and commands file. It reuses unchanged R413 bounded_stage and freezes expanded spec/environment plus new source generation. **Do not edit R439 commands-r440, stage specs or results.** Exact new stage specs derived from originals are in plan.json.verification_specs. Replace only stage id/directory/env/artifact paths and regression basetemp; preserve the original full validation argv file list, plugins, deselection and `-k` filter.

Run sequentially, once each:

```text
.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round447-static-and-final-repair-20261108/implementation/run_stage.py ruff
.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round447-static-and-final-repair-20261108/implementation/run_stage.py format
.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round447-static-and-final-repair-20261108/implementation/run_stage.py mypy
.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round447-static-and-final-repair-20261108/implementation/run_stage.py repair-regression
```

Static inner bounds 120 s / outer 240 s each. Repair regression inner 900 s / outer 1020 s, fresh `/tmp/bigsmall-r447-repair-regression`; **230 PASS, 2 deselected**, no removed/skipped cases. This is the same original final test set, with stronger existing assertions only. The true MuJoCo two-step test and actual guard diagnostic retain original exact exclusions. No extra collect-only, RED, focused rerun, fullsuite or T3 rerun. Prior actual failures are the repair baseline. Failure stops dependents; unexpected remaining/new failure requires another actual Astra plan, not a renamed rerun.

All runs require fresh exclusive stage directories, actual startup-prerequisite records, setup/call/teardown logs, child returncode, timeout/cancellation recording, reap and no remaining processes/source drift/ports. New source generation must be frozen before launching; current-source software fixtures regenerate honestly, never rewrite old registration source hashes. Stage results distinguish child status from wrapper/supervisor process completion.

## Acceptance and actual boundary

Acceptance: all four child commands pass; every old failed node reaches intended assertions, especially source sink/Shield replay and both actual synthetic-pixel R446 paths; typed mapping/enum/closure fixes preserve original semantics and evidence. Record old failure and new outcome side by side, including preexisting worker errors and the exact two-command source proof. Do not claim the original 224 passing cases demonstrated the blocked paths.

No physics/render/model request is authorized by R447. The already planned first full group remains blocked until repaired software/static checks and **one fresh whole-change reviewer** pass. No new actual quota, nine-group expansion, threshold relaxation or native qualification. Any fresh review finding or later actual failure follows the user's next-Astra rule. Final independent calibration remains subject to all original R91/R439 source, UNKNOWN and denominator requirements.

Self-review: original failure bytes retained; all six runtime failures covered; all 33 type diagnostics have a narrow proposed resolution; STOP and worker status assertions now trace to existing source; old worker typing is explicitly distinguished; one bounded repair regression and three static runs only; actual remains gated on evidence and review.
