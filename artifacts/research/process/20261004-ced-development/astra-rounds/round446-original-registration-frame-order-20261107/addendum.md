# R446 addendum — separate bootstrap and dispatch trackers

Actual planner `gpt-6-astra`, PLAN_ONLY. This addendum supersedes only the original R446 step 4 instruction to retain B-derived tracker/evidence as the active dispatch tracker, and the corresponding reader's single-bootstrap assumption. Original plan files are preserved. Twelve current input pins and original excerpts are in `intake/addendum-source-index.json` and `addendum-original-source-excerpts.json`. No product edits/tests/physics/render occurred here.

R439 T3 GREEN is preserved: original stdout records 97 PASS in 52.29 s; supervisor 53.04780488799952 s, rc0, reaped true, no remaining_live/source_drift/ports. Original stdout/JUnit/result are copied into intake. This is validation of the then-current reader, not proof that the new B/R/E handoff already works. Do not rerun that consumed stage.

## Static conflict

OpenCVTargetTracker constructor stores its exact initial observation as `_reference` and `_last_observation`. facts rejects a **different** observation id when dt <= 0 or capture_dt <= 0. It permits repeated use of the same original id/payload, rejecting changed checksum. Grounding calls facts before admission calls it again.

E is a genuinely new observation acquired at B's same physics step. Feeding E into B's tracker therefore correctly produces `capture_not_new_and_monotonic`; target_visible becomes UNKNOWN and R441 does not allow that missing identity gate. The original addendum candidate is necessary: initial compilation evidence and active first-dispatch tracker must be distinct. Do not weaken the old rule or add that UNKNOWN to the collection whitelist.

## Exact source sequence

1. Retain B acquisition and its bootstrap exactly as planned. `bootstrap_collection_tracker(B, geometry)` yields a B tracker and evidence_B. Preserve evidence_B in existing `bootstrap.json`, and retain B as original compiler/dependency/registration input. Do not mutate its observation id, checksum, captured_at, sim_time or pixel evidence. B's tracker is never fed E and never used for executed-action grounding.
2. Read the actual lease, compile at the actual R and bind the frozen original as original R446 specifies. Acquire E once through the recorder, at the same physical step, after registration. Verify original B/R/E temporal and identity constraints without timestamp substitution.
3. Call the unchanged `bootstrap_collection_tracker(E, geometry)` on E's actual image/depth bytes. This performs its real marker, geometry, unique region, profile and top-grasp checks. Obtain a **new** tracker_E and evidence_E; do not copy B's tracker fields, relabel evidence_B, assign private `_reference/_last_observation`, or clear history on an existing tracker.
4. Write `dispatch-bootstrap.json` through the existing recorder original writer. Its content is the complete evidence_E payload in the same shape as bootstrap.json. Extend `registration-timeline.json` with B bootstrap file/digest and acquisition reference, E dispatch-bootstrap file/digest and acquisition reference, and `active_tracker_reference_acquisition_id=E`. An explanatory tracker_transition field may say BOOTSTRAP_TO_DISPATCH_BEFORE_FIRST_ACTION, but original pixels and joins, not this label, prove the handoff.
5. Only after both writes succeed set the app's active `live.tracker=tracker_E` and `live.grounding_evidence=evidence_E` (equivalent local assignment ordering is acceptable if no dispatch is possible beforehand). Use the **same actual E observation instance** for first grounding and admission. The first and repeated facts(E,state) calls then follow the existing repeat/reference path naturally; they do not falsely claim temporal progress or continuity evidence.
6. Continue the normal tracker_E across all subsequent actual frames/actions. Never restart it per action or to discard an old UNKNOWN, sample history or identity failure. Required physical lift/release scoring continues to use original recorded physics, not a fabricated rebaselined physical state. Both B and E remain allocated original frames included in all-frame geometry G.

The active tracker has no lost action history: transition happens before the first action and at unchanged physics state. Nevertheless E must be independently identifiable from pixels. If E bootstrap cannot identify marker/object/region or fails geometry/profile checks, retain the real failure, both existing frames and partial bootstrap evidence, then follow R444 cleanup and COLLECTION_PARTIAL. Do not fall back to tracker_B, force evidence equality, retry capture, or advance one physics step to obtain a positive dt. Original required calibrated-depth and physical-stability UNKNOWN remain unchanged.

## Independent reader handoff

Allowed source edits now explicitly include new `native_full_horizon_originals.py` in addition to R446's new app/grounding files. Old tracker/compiler/binder/recorder remain read-only. Existing `bootstrap.json` stays B evidence. The reader must:

- Read and validate timeline against original original-plan/lease and both source-frame references, rather than infer B from the first admission's E acquisition.
- Reconstruct B from original bytes, run unchanged bootstrap_collection_tracker on B and compare complete evidence_B with bootstrap.json; retain it solely for original registration/dependency checks.
- Reconstruct E from original bytes, run the same bootstrap function on E and compare complete evidence_E with dispatch-bootstrap.json; use the resulting tracker_E/evidence_E for all actual grounding/admission replay.
- Reuse the reconstructed E observation object for its initial/repeated E replay calls. A per-acquisition object cache is permitted only as a faithful view of already hash-validated bytes; it cannot skip validation or replace original bytes. Later same-id calls must preserve original payload/checksum and source call order. No E geometry/facts may be obtained by mutating B's object.
- Verify first action BEFORE_SUBMIT, grounding/Shield sources and timeline active tracker all join E. Verify there was no intervening physics transition and both captures are retained in coverage/render counts. Missing/wrong/mixed B/E evidence, missing timeline, nonidentifiable E or mismatched replay remains incomplete/UNKNOWN.

Do not remove old reasons, make bootstrap labels confer authority, or pretend same-step B→E is a temporal stability sample. No online truth input is introduced.

## Validation and limits

Extend the **same two already planned R446 CPU tests**, using internal subcases, not additional collected tests. They may live in the existing authority/grounding test files and invoke independent reader helpers; existing reader tests/fixtures may be adapted for the new required fields, but no new test stage or consumed T3 rerun is allowed.

- In the positive registration test, demonstrate unchanged B tracker rejects new same-step E; separately bootstrap real synthetic-pixel E through the actual bootstrap function; then call its facts twice as grounding/admission do and verify no capture_not_new_and_monotonic reason. Keep real compiler/binder ordering checks. Independently replay both saved evidence payloads and reject swapping their acquisition links. Do not mock facts/bootstrap success to manufacture this assertion.
- In the negative handoff test, include E marker/region/bootstrap failure, mixed B evidence/E id, changed payload reuse, timeline write failure and false sim-time advance. Confirm failure before dispatch and partial provenance. A later new-id same-time frame must still be rejected by the active E tracker; no general exception was created.

Run these only in the original unused final-regression, 900 s inner / 1020 outer, attempt 1; original remaining static/reviewer requirements remain. Existing T3 97 PASS is preserved separately. New unexpected failure requires actual Astra. Current pins must be checked for applicability before edits; preserve original pin snapshots when documenting any concurrent independent changes.

No extra capture beyond R446's E, no physics, no resource increase: successful explicit boundaries remain 10 within 16; original physical 12960, explicit maximum 12976, implicit maximum 12962, render maximum 64852. This addendum executes 0 tests/physics/render/model calls. Original first actual group release and nine-group prohibition are unchanged.

Acceptance is independent B/E pixel reconstruction, correct original registration and tracker chronology under unchanged old rules, same-frame repeated-call behavior preserved, raw evidence and UNKNOWN retained, and the two expanded tests passing in original final. It is not a claim of full-H actual success or calibration qualification.
