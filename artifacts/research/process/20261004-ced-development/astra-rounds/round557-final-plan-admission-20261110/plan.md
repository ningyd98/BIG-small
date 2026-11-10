# R557 Final Plan Admission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Parent performs this bounded repair inline; no new design approval or whole-change review loop.

**Goal:** Reject an expired or rebound post-cloud plan at the actual contract return and cached-success return boundaries.

**Architecture:** A private per-draft callable captures that invocation's original binding and fresh observation. The pipeline retains this callable in its private cache entry and invokes it after actual contract construction and before returning cached PLANNED results. No new orchestration layer or repeated planning.

**Tech Stack:** Existing Python/Pydantic PrivateAttr, existing pipeline/adapter, pytest/Ruff.

**Spec:** Adjacent `request.json`; R554-REV-1 in the frozen R554 review report. Actual planner: `gpt-6-astra`. Baseline HEAD `9f7e7064e2e5ba204517af95d5832330ad45112d`.

## Original failure and diagnosis

The independent review found **0 Critical / 1 Important / 0 Minor**. Its original reproduction delegates to real `pipeline.build_task_contract`, advances the fixture clock by 6 s, then observes **PLANNED, non-null contract, validation=true, fresh age=6.0 s, local refresh=PASSED**. Separate cache reproductions return the exact same PLANNED object after age=6 s or timeout changes from 30 to 31. Each is CPU-only, with one fake cloud call/four point queries/one refresh, not actual model/cloud execution.

The adapter's final `_fresh` runs before the pipeline's schema/semantic/trusted-field/final-contract work. Cache hits bypass the adapter entirely. Both are one missing final-admission boundary. R554's candidate-construction delay test did not cover real contract construction. Preserve all original scripts, commands, outputs, manifests and review conclusions; passing new tests must not overwrite historical failure evidence.

All **25 request inputs** were verified for exact size/SHA256. Both review manifests' file/source entries were also verified. The exact 25-entry inventory is in `plan.json`. Existing software evidence: 456 related CPU tests, 14 capture tests and 5 observer tests passed; these overlap and are not summed. The full suite stopped at a preserved preexisting docstring failure (94 passed / 1 failed); do not claim full-suite green or repair it here.

## Scope and invariants

Modify only `cloud/planning/models.py`, `cloud/planning/pipeline.py`, `vision/grounded_planner.py` under `src/cloud_edge_robot_arm`; create `tests/test_molmo_final_admission.py`; update `docs/research/molmo-opencv-grounded-planner.md` and round-local evidence. Existing adapter protocol, geometry/association/tracker, revalidation policy, captures, CLI, model runtime and SDK stay unchanged. Existing test files are reusable fixtures, not required modification targets.

Default supplier=None and legacy planners preserve their validation/idempotency behavior. Original request/captured bytes and genuine trusted-field construction remain untouched. TTL remains inclusive age **[-0.05, 5.0] s**, with rejection outside; no fresh timestamps, recapture, native generation, cloud retries or dispatch on final rejection. The final gate consumes the trusted new observation, never the old request frame or an evidence-reconstructed frame.

## Exact interfaces and ownership

1. In `models.py`, after InitialPlanningRequest, define type alias:
   `FinalPlanAdmission = Callable[[InitialPlanningRequest, object], None]`.
   Add only `PlannerDraft._final_plan_admission: FinalPlanAdmission | None = PrivateAttr(default=None)`. This is not a Pydantic field or public transport property. Callable/binding/supplier/secret references never enter `model_dump`, JSON or JSON schema. No response-model private field is needed.
2. On `MolmoGroundedPlannerAdapter`, add property `requires_final_plan_admission -> bool`, returning whether its supplier is non-None. Do not add it as a requirement to PlannerAdapter Protocol or other adapters. Add private factory `_make_final_plan_admission(self, binding: _PlanBinding, observation: RGBDObservation) -> FinalPlanAdmission`. It returns a fresh closure per successful opted-in invocation, never stores last-request state on the adapter.
3. The closure captures the original binding, this adapter identity and an independent validated copy of the **fresh** observation plus its fixed checksum. When called as `admission(original_request, active_planner)`, require active_planner is this adapter, require the passed original request's canonical configuration_hash equals binding.request_hash, revalidate the retained fresh observation/checksum, then call existing `_fresh(fresh, binding)` last. Existing `_context` thus still checks the original retained request, task identity/hash, provider, supplier, cloud/role identity/digest/settings. A hash-equivalent new request object is allowed; a different request/payload/adapter is not. Do not invoke supplier, native/cloud, geometry or contract construction from this closure.
4. Attach the closure to the successful opted-in draft immediately before returning it. Failed and legacy drafts have None. The closure must not depend on mutable public evidence, observed_scene or a per-adapter last result. Capture it in the pipeline immediately after plan returns; later public draft/evidence edits do not replace the trusted callable.
5. In `pipeline.py`, add a small frozen internal dataclass `_CachedPlanningResult(request_hash: str, response: InitialPlanningResponse, admission_required: bool = False, admission: FinalPlanAdmission | None = None)`. Replace existing tuple cache entries with this equivalent wrapper; ordinary failure/legacy writes use defaults. Required state is pipeline-owned, not inferred from serializable evidence or a response restored from JSON.
6. At process entry keep `original_request = request` before any observed_scene replacement, and snapshot `admission_required = bool(getattr(active_planner, "requires_final_plan_admission", False))`. After planning capture `draft._final_plan_admission`. A returned callable also requires the gate even if the property changes later. For a PLANNED cache hit, gate if its stored required flag, its stored callable, **or the current active planner requirement** is present. Removing the supplier or switching planners cannot disable a guard stored with a prior success.

## Exact final and cache behavior

Add one private pipeline helper:
`_admit_planned_response(response: InitialPlanningResponse, *, original_request: InitialPlanningRequest, active_planner: PlannerAdapter, required: bool, admission: FinalPlanAdmission | None, phase: Literal["final_contract", "cache_hit"]) -> InitialPlanningResponse`.

- Non-PLANNED responses and legacy success with no requirement/callable return unchanged. Do not evaluate freshness on other legacy cache hits.
- On first success, run original schema/semantic/repair/trusted-field/build_task_contract code and construct the response first. Prepare final evidence before the check; invoke the callable as the final substantive validation before cache/return. No expensive construction/serialization/perception after a successful gate. A valid guard returns exactly None; any other value is invalid. Missing/noncallable required guard fails closed.
- A valid cached success returns the **same response object**, unchanged; no refresh of created_at, issued_at, contract validity or prior evidence. The retained callback uses the actual current caller and active planner. A new request with the same ID but different request hash retains existing REQUEST_ID_CONFLICT behavior before any gate/plan. Never reuse another invocation's callback.
- Failure returns a **new copied response**, outcome REQUEST_MORE_OBSERVATION, contract=None, dispatch=None; never mutate an earlier response already returned to a caller. Set response and final-attempt validation.passed=False and append an error at field `final_plan_admission`; retain existing validation errors/warnings and raw/model history. For existing ValueError failures use the existing bounded reason (for example `capture_time_not_fresh` or context/settings change); missing/invalid hook uses `final_plan_admission_missing` / `final_plan_admission_invalid_result`; unexpected callback Exception uses `final_plan_admission_error:<ExceptionClass>` without printing exception payloads/secrets. Do not catch process-control BaseException.
- Cache the new contract-null rejection under the same original request hash, replacing that cache's executable success. Repeated calls return this rejection without planning or invoking the failed hook again, even if settings later recover. Previously returned external objects cannot be retroactively revoked; no claim otherwise. To plan anew, callers use the existing new-request flow.
- Preserve `post_cloud_revalidation.status=PASSED` when the local refresh really passed. Add separate serializable `observation_evidence["final_plan_admission"]` with status PASSED/REJECTED, phase `final_contract`/`cache_hit` and failure reason when present. Valid cache hits retain the initial PASSED record unchanged; failed cache returns annotate only the new response copy. Evidence is an output record, never authority for whether or how the gate runs. Clear the rejected draft's private callable in the copied rejection; the negative cache entry has no admission callable.
- Add `cloud/planning/models.py` and `cloud/planning/pipeline.py` to the grounded factory's role source-hash inventory alongside existing grounded adapter sources. No new helper module or protocol framework is required.

### Task 1: Expected RED, minimal final/cache admission implementation, GREEN

**Files:** The three source files and new `tests/test_molmo_final_admission.py` named above. Reuse R554 `refresh_fixture` and its phrase-aware bound provider.

- [ ] Reverify 25 inputs and preserve exact pre-edit source snapshots/hashes locally. Convert the original reproduction into RED tests that wrap and delegate **real pipeline.build_task_contract**, then advance fixture time by 6 s. Assert contract=None/REQUEST_MORE_OBSERVATION/final validation false, local refresh PASSED and final admission REJECTED, with no extra calls. Add independent delays in real semantic_validate and complete_trusted_fields (prefill and final completion), preserving their real return values.
- [ ] Add cache RED tests: still-valid repeat returns the identical response without additional queries/capture/cloud; expired, settings/task/provider/supplier/cloud/role drift and switched active_planner return a new contract-null rejection. Include original retained request mutation while the caller supplies an unchanged equivalent request; same-ID changed payload still conflicts. A second call after failed admission remains rejected without new calls or hook execution.
- [ ] Add per-invocation tests for two request IDs using one adapter: each cached result checks its own fresh timestamp and request binding, never the newest invocation's state. Interleave results so one expires while the other remains valid. Counts must remain each original 4 queries/1 cloud/1 refresh.
- [ ] Test final and cache boundaries at age exactly 5.0 and -0.05 (pass), and 5.000001/-0.050001 (reject). Advance the existing fake UTC clock for final checks; do not retime observation bytes. Test required missing/noncallable hook, unexpected exception and non-None result; all fail closed with no repeated work. Forged public evidence cannot supply or bypass a private hook; a serialized/deserialized opted-in draft loses its hook and is rejected where required. Assert callable/binding/private attribute absent from draft and response model_dump/JSON/schema. Legacy/defaultNone and legacy idempotency retain existing outcomes and same-object caching.
- [ ] Run new tests before edits, saving exact RED outputs. Expected failures expose both missing final checks and absent new private interfaces, not fixture-construction errors. Keep the original review reproductions unchanged.
- [ ] Implement only the exact interfaces/semantics above. Maintain all actual validation and trusted constructors; wrap neither cloud requests nor clocks. Re-run focused tests to GREEN, including assertions that earlier returned success objects and original requests remain unchanged after cache rejection. Save source hashes and result evidence.

### Task 2: Regression, delivery and closure of the existing review finding

**Files:** Guide and round-local reports; no unrelated source repair.

- [ ] Run new tests with existing grounded/revalidation/CLI and `tests/test_phase4_cloud_planning.py`; then the previously used adjacent RGBD/role/top-grasp/tracker suites and observer tests. Run scoped Ruff and git diff --check. Use exact commands/logs; do not sum overlapping case counts. The unchanged full-suite known failure remains explicitly recorded; no repeat full-suite run or unrelated fix is required solely for this narrow repair.
- [ ] Re-run both preserved CPU reproduction scripts read-only, writing new outputs in R557. Require delayed construction and expired/settings-drift cache cases now contract-null; compare output fields and zero extra calls, not byte equality to failing outputs.
- [ ] Update guide and step/phase reports with final-admission/cache semantics, local-versus-final statuses, private serialization boundary, source provenance and known full-suite limitation. Mark R554-REV-1 resolved only from these fresh tests/results. This closes the one Important repair; **do not dispatch another whole-branch review or request design approval**.
- [ ] Commit/push only explicit verified source/test/derived-evidence paths, check local/upstream/remote SHA per AGENTS. Retain raw originals and the existing publication boundary. R554 actual-run prerequisites remain; this plan itself authorizes no extra real attempts beyond its already-approved allocation.

## Runtime prerequisites and layered acceptance

CPU uses `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python`, managed-worktree cwd and explicit `PYTHONPATH=/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src`. Managed-worktree writes may need scoped escalation. Source drift outside the planned scope or a different root cause requires the next actual Astra plan. No model/runtime/package/SDK changes or credential output.

Development acceptance: both final-return exits closed, legacy/default compatibility, private non-serialized binding and correct evidence proven by RED→GREEN and scoped checks. Review acceptance: existing R554-REV-1 is closed with the repair evidence, not a second review cycle. Real native/cloud/actual contract acceptance remain separate R554 gates; current planning/repair tests are not real-run success. Physical/formal remain NOT_RUN.

Actual totals stay **3 loads / 6 generations / 1 paid attempt**. R554's still-unused maximum **+1 load / +4 generations / +1 paid attempt** remains, cumulative ceilings **4 / 10 / 2**, no retry, zero hardware/formal. This Astra planning turn uses **0 actual calls**. No unresolved interface decisions.
