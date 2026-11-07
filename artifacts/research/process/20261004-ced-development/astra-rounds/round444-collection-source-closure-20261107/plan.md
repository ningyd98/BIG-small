# R444 — collection source closure

Actual planner: `gpt-6-astra`. PLAN_ONLY; no product edits, tests, engine initialization, physics, rendering, network or Git writes. This round addresses three distinct mechanisms at one shared source-to-final-receipt boundary. It does not reset R439 or R443 validation or actual budgets.

## Evidence and applicability

34 SHA256 input pins are in `plan.json` and `intake/source-index.json`. Original relevant source excerpts are preserved. R443 original stdout/JUnit/result show 80 PASS, 1 deselected, supervisor 14.014447880 s; its step-report records pytest 12.88 s, 0 physics/render/model calls. R439 T3 original stdout/JUnit/result show the expected one API assertion (`full group reader missing`), pytest 0.06 s, supervisor 1.002635374 s. No R444 runtime failure occurred; these gaps were found statically before T3 source closure could be claimed.

S1: application `_evaluate_collection_admission` saves Shield result but not SafetyContext. The call of `grounded_collection_step` discards online/checkpoint objects; that function creates actual inputs/policy locally, then returns only contract/step/binding/online/checkpoint. A hash alone cannot recover original input bytes.

S2: `backend.enforce_execution_guard` calls `_close_execution_guard` on both success and failure. `_close_execution_guard` calls actual emergency_stop even on success. Current app exits its SETTLE/action purposes before this closure; old RawV3 `_on_boundary` then assigns COMMAND parent `unbracketed-operations`. Changing an event label afterwards would not repair the original parent.

S3: current `run_from_worker` calls check_active/check_sources/disk preflight before its try/finally, and constructs several resources before exception handling. Its finally joins capture close and backend shutdown in one try, so one failure can skip the other. It writes collection-result before worker publication/terminal status and operational-owner close. `execute_once` may receive no body receipt because worker catches failures internally; its finally can also replace the primary error with owner.close failure or leave live.closed unset. These are source-completeness and error-preservation gaps, not evidence of actual full-H failure.

## Scope

Allowed products: only the existing R439 new modules `research/native_collection_application.py`, `research/native_collection_grounding.py`, `research/native_full_horizon_recorder.py`. Allowed tests: `tests/test_native_collection_authority.py` and `tests/test_native_collection_grounding.py`. R439's independently implemented byte-reader is not part of this repair's edit scope; its handoff is below.

Do not change old backend, old recorder/RawV3 schema, worker, Shield configuration/rules, current grounder/controller, original conditions or UNKNOWN admission whitelist. Preserve marked asset/top camera and all source/assignment checks. No new trusted caller flag, calibration exception or truth-based control. All original plans, results and failed input bytes remain immutable.

## S1 — capture actual decision inputs before use

Extend `grounded_collection_step` with a new optional keyword-only evidence sink, preserving its existing five-value return interface for callers/tests. The actual collector MUST supply this sink. Within the function, after binding is constructed and before returning a dispatchable step, call the sink with the exact current objects/payloads, never later recomputation. Sink writes fail closed before controller dispatch. Save once to `grounding/step-N.json` (N is the existing original step number, 1..8):

- original plan digest and identity, index and source step id, source generation;
- complete checkpoint `model_dump(mode="json")`, checkpoint hash, and the exact `now` used for binding;
- `inputs.to_payload()`, `policy.to_payload()`, their existing digests;
- complete binding `to_payload()` and binding digest;
- full executed contract and grounded step; online robot_state and visual_facts, scene/plan/checkpoint metadata;
- observation identity/checksum plus exact acquisition/source-frame path and digest, rather than duplicating images or substituting a later frame.

The sink lives inside the new recorder's original-byte writer/inventory budget. Do not modify old GroundingFrameInputs or binding schemas. Reader rehydrates original inputs/policy/checkpoint and checks their own domain digests, binding links and deterministic resolved parameters. No call to current time during replay. Original pixels, not saved geometry alone, remain the source for independent geometry checks.

Save `shield/config.json` once before checks: actual hard limits, operational policy, merged constraints, original policy_version/hash, rule_count and current registered source generation. Pydantic models use JSON-mode payloads. The merged dataclass contains a frozenset: explicitly encode the known `low_height_exception_skills` as a sorted string list (and other nested models as their JSON payloads); preserve its set semantics on rehydration. Do not silently use repr/default=str, modify the old generic serializer, change the policy hash, or turn unordered sets into unverifiable object strings. Check config against the same registered `research_safety_shield` recipe; the recorded policy hash alone is insufficient.

For each actually invoked PRE/POST Shield call save, BEFORE invocation, `shield/step-N-pre-input.json` or `...-post-input.json`: full actual SafetyContext JSON, exact method, index/step_id, config file digest, source generation, acquisition/source-frame id and grounding file digest. The full contract, wall/monotonic time fields and measured robot/joint state are retained as supplied; no synthesized future clock reading. After the call write matching `...-result.json` containing input file digest plus full result, or actual exception type/message if the call raised. Save output before admission/controller continuation. On input or output write failure, stop; no fabricated PASS/default result.

Admission inputs retain their existing complete Shield result and add immutable references/digests to its original input/result files and grounding source. The TERMINAL admission currently reuses last POST; record that exact POST reference with `reused_from=POST`. Do not claim a second Shield invocation or silently substitute a new context. Any existing source incompleteness remains a failure/UNKNOWN in the independent reader.

## S2 — real termination context around guard exit

Implement a private context helper in the new app, retaining the existing backend guard implementation. Enter the actual guard once. Execute the body under unchanged SETTLE/action/HOLD purposes. On both normal and exceptional body exit, call the actual guard context's `__exit__` with the original exception triple while `recorder.purpose("TERMINATION")` is active. Do not wrap the entire physics body in TERMINATION and do not call an additional emergency_stop. Preserve the guard's exception propagation/no-suppression behavior; never replace an exceptional exit with `close()` that supplies no exception.

Lifecycle order: body sampler unwinds; actual guard closure occurs with TERMINATION parent while recorder/owner/backend remain live; termination interval ends; freeze active checks/originals; detach recorder; close capture and backend independently; close operational owner at outer execute boundary. A guard already closed by an inner failure may make outer exit idempotent: retain original earlier STOP and empty actual terminal interval, do not invent another command. Required command ancestry must match the original events, not a filtered list.

Record failures from purpose/guard exit and the backend guard ledger's actual secondary stop/snapshot errors. If purpose entry itself fails, the backend guard still MUST be exited for safety; preserve the purpose failure and resulting raw incompleteness rather than pretending the STOP was bracketed. Do not bypass shutdown because receipt writing failed. Never edit old STOP semantics or operation ledgers.

## S3 — body evidence plus one final lifecycle result

Make the actual app's protected lifecycle encompass preflight and resource construction. Maintain explicit attempted/entered flags for backend initialization, capture entry, recorder entry and guard entry; avoid closing unopened scopes or reading unavailable model/state as if it existed. Once the private actual worker identity is established, preflight errors belong to this collection's failure record. Entry identity violations remain rejected and must not confer recording/execution authority on fabricated callers.

`run_from_worker` retains a body result in memory and, if output remains writable, writes a separate exclusive `collection-body-result.json` after its resources are closed. This is explicitly intermediate and cannot be presented as final success. Do not write final `collection-result.json` here. Capture primary phase/error_type/error and each subsequent cleanup error without replacing earlier errors. Separate recorder freeze/detach, capture exit and backend shutdown cleanup attempts; a failure in one must not skip the rest. Freeze failure still detaches observer; detach failure still attempts capture/backend closure. Every stage runs at most once, no retry. Include observed backend guard secondary errors even if backend intentionally preserves the original exception instead of raising the secondary.

`execute_once` is the sole finalizer. Its try/finally covers prepare/enqueue, worker.poll_once, missing body receipt and owner.close. After poll, preserve actual repository job/attempt/event originals through `get_job`, `list_attempts`, `list_events`, filtering to this exact job and attempt, with originals' ids/status/error text unchanged. Preserve repository query errors too. Do not infer the original error merely from generic `worker returned without a collection receipt`; a failed worker's error_message and attempt.error are the evidence. Worker may report SUCCEEDED for collection completion while physical task_success stays false: retain that runtime status verbatim, never equate it with native/physical success.

Close the operational owner in an independent protected block, and set live.closed in an unconditional finally even if close raises. Only AFTER actual worker outcome and owner.close outcome are known build/write `collection-result.json` exclusively once. Keep in-memory live.result for existing software fixtures; `run_from_worker` may produce a body result but cannot determine final lifecycle success. No return value is selected before cleanup. Any preflight/worker/body/recording/cleanup/owner failure yields COLLECTION_PARTIAL, teacher_collection_admitted=false, online_effect_status/native_qualification UNKNOWN, execution_admitted=false, joint_bound_m/qualified_group_score None. Missing receipt is explicit, not silently successful. Preserve primary exception with secondary details; exceptions should still propagate after recording, not be converted into successful returns.

Final result includes body-result digest/path when present; actual worker snapshot and its failures; phase progress/entered flags; all errors with primary/secondary roles; owner closure outcome; observed counts and their provenance. If no backend was ever initialized, record NOT_STARTED and zero physical effects only when supported by the explicit stage flags. If counters cannot be read after a partially initialized failure, use null/UNAVAILABLE instead of claiming zero. Cache actual counters before shutdown as needed; retain raw originals as count authority. A final file write failure is itself a failure: preserve it in memory/raised error, never claim persistence or retry overwrite. Disk failure cannot guarantee a file exists; this limit must be reported honestly.

Final result is a lifecycle artifact outside the already-frozen recorder inventory; do not mutate inventory after freeze to add it. It carries the exact inventory hash when one exists, and T3/phase reporting separately pins the final file. Every downstream reader must require both source inventory and final lifecycle evidence for a complete group; neither self-label alone establishes completeness.

## Tests and validation budget

No extra RED/GREEN stage or actual run is authorized. Preserve R443 80 PASS and R439 T3 expected RED. Add these eight CPU-only tests to the already-included two test files and run them once within the not-yet-run original R439 final-regression; use internal case loops without adding parameterized nodes:

1. `test_grounding_originals_roundtrip_and_write_failure_prevents_dispatch`: exact input/policy/checkpoint/binding roundtrip plus sink exception prevents dispatch; synthetic RGBD/proprio fixture only.
2. `test_shield_original_context_replays_and_failed_write_stops`: call real pure Shield on saved context and compare full result; cases include rejection/exception and original-file write failure. No engine or render.
3. `test_guard_normal_exit_has_termination_parent`: fake/no-physics backend with real software RawV3 recorder fixture; normal actual guard closure emits one STOP COMMAND whose parent is the real TERMINATION interval; no invented command or physics.
4. `test_guard_exception_exit_preserves_primary_and_secondary`: exceptional body, STOP/observer failure and purpose-entry failure cases; preserve primary, ledger secondary, cleanup attempt and no extra stop.
5. `test_collection_preflight_failure_retains_worker_original`: existing real SQLite/worker software-body pattern; inject disk/source/preflight failure before backend initialization, verify actual worker error retained in final result, no false success.
6. `test_collection_worker_failure_after_body_downgrades_final`: simulate worker publication/finalization failure after an apparently complete body; final verdict partial, actual repository failure preserved.
7. `test_collection_owner_close_failure_preserves_final_failure`: owner close fails after otherwise clean software body; live.closed remains true and final result records failure before returning/raising.
8. `test_collection_cleanup_failures_preserve_all_and_close_once`: fake staged resources fail freeze/detach/capture/shutdown independently; remaining cleanup still attempted once, primary/secondary order retained; final save failure raises without fake persisted success.

No test initializes MuJoCo or renders; existing exact two-step and guard actual diagnostics remain excluded. `plan.json.verification.final_regression_command` pins the R440-approved original final-regression argv. Existing R439 runner discovers tests in these same files, so no command overlay mutation or new stage is needed. Command remains:

```text
.venv/bin/python artifacts/research/process/20261004-ced-development/astra-rounds/round439-full-execution-independent-calibration-20261107/implementation/run_stage.py final-regression
```

Inner 900 s / outer 1020 s, attempt 1, original fresh stage/temp paths and R413/r235 startup plugins. Freeze expanded expected collected node list/count from final implemented files without a separate collect-only invocation; result must show all eight new test names passing, all existing selected nodes passing and only predeclared deselections. T3 GREEN remains R439's one independently implemented reader stage; it may validate new reader expectations through its original tests but does not consume an extra collector stage. Original final static and one fresh whole-change reviewer remain required before first actual group. Any unexpected failure stops its dependents and needs new actual Astra; no rename/retry.

## Reader handoff and completion boundary

ROOT's independent T3 reader must consume the named original files, verify inventory bytes/hash and all cross-file input/result references, rehydrate the saved SafetyContext and execute the same source-pinned pure Shield with exact original values, validate actual grounding/checkpoint joins, and verify termination ancestry and final lifecycle outcome. Missing files, altered fields, orphan STOP, failed closures, or retained required UNKNOWN cannot be made acceptable with new labels, filtered reasons or aggregate flags. Old raw/UNKNOWN remain unchanged; a failed partial group is retained in the denominator and cannot produce a finite qualified score.

R444 is accepted only after source capture and finalization are implemented, the eight CPU cases pass in the original final stage, static checks and final review pass, and exact sources are re-registered before the already-authorized actual attempt. These software results still do not prove full-H native completion. All original actual prerequisite checks, physics/render/raw/RSS/wall budgets and single-assignment release remain unchanged. No new actual allowance and no nine-group expansion.

Self-review: source inputs are captured before effects; closure invokes the actual guard once; cleanup cannot skip unrelated resources; final success is decided after worker and owner closure; new cases fit an existing unused stage; actual authority and UNKNOWN boundaries remain intact.
