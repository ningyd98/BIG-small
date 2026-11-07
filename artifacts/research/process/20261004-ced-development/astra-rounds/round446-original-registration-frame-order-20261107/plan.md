# R446 — original registration and first dispatch frame order

Actual planner `gpt-6-astra`; PLAN_ONLY, static source inspection, 14 SHA256 pins with original excerpts in intake. No product edits, tests, physics, render, network or Git writes. No actual quota increase. R443 validation and R439 T3 RED remain preserved; R444/R445 implementation and independent reader work continue subject to their own boundaries.

## Proven conflict

The old rules impose both of these constraints:

```text
compile_worker_original_plan:
  lease.acquired_at <= bootstrap.captured_at <= registered_at
  lease.observed_at <= registered_at < lease.expires_at

bind_step_grounding:
  original.registered_at <= dispatch_frame.captured_at <= now
  now < min(original.effective_deadline_at, dispatch_frame.captured_at + original_TTL)
```

read_visual_worker_lease observes the real RUNNING job, open attempt and unique unreleased lease under the original publication guard. Its observed_at is the real read time; attempt.started_at must be after lease acquisition and no later than that observation.

Current application first captures, bootstraps, reads that current lease, and calls build_collection_contract with an actual datetime.now registration. It then uses the same old frame for grounding. The compiler rightly permits this chronology, but the binder rightly rejects it. A single frame could satisfy both only at exactly equal frame/registration timestamps, which is not the actual sequence.

Using prepare/enqueue/task-issued time, lease acquired time or worker-origin time for registered_at is not a valid repair. Those events precede the later required lease observation and do not witness this original's registration. Supplying a historical `now=` to read_visual_worker_lease would likewise misrepresent the actual repository observation. The user-requested real-source chronology cannot be solved by backdating a field.

## Narrow repair

Only new native_collection_application.py and, if needed for explicit timeline return, native_collection_grounding.py may change. Do not edit old worker_owner/compiler, owner_registration/binding, observation timestamp/TTL checks or recorder schema. Tests may change only existing test_native_collection_authority.py and test_native_collection_grounding.py.

Keep the **actual registration sample** taken at compilation after bootstrap and current lease observation. This is already the correct event in build_collection_contract. The original may be frozen/published after this sample, but the new execution frame is acquired only after the complete final original has been bound to the recorder. Preserve original contract issued_at, valid_until, original task deadline and pre-enqueue OC1 deadline; no new task origin or duration extension.

Sequence in the actual guarded app:

1. Finish registered 120-step settle. Capture original bootstrap observation B through the actual recorder; retain its actual acquisition id, payload/checksum, source-frame and OC1 bracket. Bootstrap tracker/calibrated pixel evidence from B.
2. Observe the actual RUNNING worker lease with the existing default read time, preserving its complete to_payload. Build and freeze original using actual compilation registration time R. Do not inject caller historical time. Bind that completed original to the sole recorder and write existing bootstrap/original/source binding originals.
3. Take **one new actual explicit capture E**, after registration/binding, through recorder.capture at exactly the same physics step. This is the first dispatch observation, not an edited B. It must have its own actual acquisition/observation identity, original timestamps and OC1 bracket, correct same episode/calibration, registration <= E.captured_at, and zero physics advance. Record check_active before/after as the existing recorder already does.
4. Replace only the application's current observation reference with E. The retained initial tracker/bootstrap evidence remains B-derived as intended; current-frame geometry, robot-state snapshot, checkpoint, inputs, deterministic parameters, binding, Shield context and decisions are computed afresh from E. No pre-E grounded payload or binding may be reused. Then execute the normal original eight-step loop.
5. Subsequent actions keep their existing valid same-step preceding terminal capture reuse and fresh per-action grounding. No extra recapture loop, sleep, timestamp adjustment or retry if E is stale/future/invalid. If UTC ordering fails (including clock reversal) or original TTL/deadline is exceeded, stop and retain partial evidence.

The bootstrap remains an original dependency/evidence source in the original compiled plan. It is not relabeled as the first action's current acquisition. Source-order metadata is evidence only, never execution authority.

## Record exact chronology

The new app uses existing recorder._write_original to write `registration-timeline.json` (within inventory/raw byte budget), once E is captured and before first grounding/dispatch. Include original plan digest and registered_at; contract issued_at/unchanged deadline; original worker/task/lease/attempt identity and full actually observed lease; B and E acquisition ids, observation ids/checksums, actual captured_at values, source-frame paths/digests and OC1 brackets; actual backend physics step before/after E; original source_generation. Use existing recorder capture receipts/maps, not reconstructed timestamps or synthetic event ids.

Failure before completion retains already-written frames/partial records and the R444 lifecycle failure. If writing the timeline fails, do not dispatch. No need to invent a successful complete timeline for a failed capture. Do not construct a UTC↔BOOTTIME mapping from adjacent reads. Both domains retain their own actual events; OC1 TTL still uses E's original bracket, UTC binder TTL uses E.captured_at. B's timestamp/age remains unchanged.

Reader handoff under already-authorized T3: verify timeline's original hashes/identities and inequalities against actual original plan, lease and both frames; first action BEFORE_SUBMIT/grounding/Shield must link E, never B. Old missing timeline stays incomplete. Reader must not accept the file's boolean summary as proof. This does not add another reader stage or product scope beyond T3's existing independent work.

## Counts and remaining resources

No physics is added. A normal path uses 1 bootstrap + 1 post-registration first-dispatch + 8 terminal explicit captures = 10, within the existing allowance of 16 boundaries. Seven next-action preframes reuse the preceding actual terminal at the same step as before. The bootstrap is not silently dropped from all-frame geometry G or raw inventory.

Original bounds stay: physical 12960; required per-physics captures 12960; explicit acquisition maximum 12976; implicit maximum 12962; renderer-pass maximum 64852. The one new explicit capture uses three actual render passes inside these existing ceilings; it does not authorize an extra actual stage or enlarge the registered maximum. Truth remains offline, 5 s TTL unchanged. The new full path has 12970 successful explicit acquisitions if complete, but actual counts are obtained from original events, never filled from this arithmetic. Failed/partial captures remain counted according to existing rules.

## Two CPU tests, existing final stage

Add exactly two tests in the allowed existing files and run them in the not-yet-run original final-regression (900 s inner/1020 outer; attempt 1; existing R413/startup plugins and deselections). No extra RED/GREEN or collect-only stage, no real backend/camera initialization:

- `test_original_registration_requires_new_first_dispatch_frame`: controlled actual software-clock/lease fixture follows B < lease.observed_at <= R < E <= binding.now, using the real old compiler/binder. Verify B-based binding is rejected and freshly computed E-based grounding succeeds, distinct identities/checksums joined, original payload derived only after E, physics counter unchanged. Assert original task/OC1 deadlines unchanged. Test application ordering through injected software capture/clock fixtures rather than mocking the binder's verdict.
- `test_registration_handoff_rejects_backdating_and_stale_capture`: case-loop tests old prepare timestamp preceding lease observation, reused B, stale E at expiry equality, future E, capture failure, timeline write failure and unwanted physics advance. Each must fail before controller dispatch; no new registration/time stamp rewrite or retry. Retain both frame originals where produced and original error in R444 lifecycle evidence.

Existing R444 eight cases and R445 cases retain their assigned stages. T3 GREEN remains its original quota. Existing final static and one fresh whole-change review still precede original first actual group. Unexpected failure requires actual Astra; no rename/retry. This round itself runs 0 tests, physics, renders or model calls.

Acceptance is real source chronology satisfying both unchanged old rule sets, complete original B/R/E evidence, all first-action inputs based on E, and zero resource-budget increase. Software acceptance is not native qualification or proof of actual full-H completion. Missing or failed evidence keeps UNKNOWN and the independent denominator.
