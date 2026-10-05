# T8 raw-hook independent review

Date: 2026-10-04. Reviewed the refreshed `review-package.diff`, `source-hashes.json`, source copies/current backend, teacher, and new tests. The refreshed package includes requested/applied terminal hold targets. All three current files match the submitted hashes. T10 condition changes are outside this package/review.

**Scoped software/specification and quality verdict: REQUEST CHANGES.** The additions are passive logging/callback surfaces and do not replace the executor or alter actuator target rules. Their command/control/action provenance is useful, but a reentrant teacher call can defeat callback mutation protection, and actuator callbacks survive reset.

## P1 — teacher reentry clears an existing observer's mutation guard

Location: `datasets/rgbd/teacher.py:110-127`, `:166-170`; guard consumption in `simulation/mujoco/backend.py:546-548`.

`run_teacher_episode` does not reject entry from an active backend observer. If its optional initial `physical_observer` is provided, it sets `_in_observer_callback=True` and then unconditionally resets it to False, even when it was already True for an outer callback. The nested teacher can subsequently fail because another physics observer is active, but after the caller catches that error the outer callback has lost its guard and can call backend mutators successfully. With no existing physics observer, nested teacher execution can also proceed after the guard is cleared. This violates the claimed read-only observer contract through the public teacher entry point, without direct private-array mutation.

A synthetic CPU-only dummy-backend check reproduced: nested teacher error `a physics step observer is already active`; outer callback guard after reentry `false`; `apply_joint_targets` mutation blocked `false`; one command recorded. No MuJoCo initialization/step, rendering, hardware, network, or research evidence was involved.

Reject teacher entry while the backend is in a callback, before recorder/state changes. Use a shared guard context that preserves/restores the previous guard state for initial/action callbacks, and cover a callback that invokes the teacher, catches the rejection, then attempts a backend write/step. The outer callback must remain protected throughout.

## P2 — reset leaves the actuator observer registered across episodes

Location: `simulation/mujoco/backend.py:246-268`, `:392-408`.

`reset` clears `_step_observer` and replaces episode/step/command state, but omits `_actuator_observer`. An actuator-observer context active during an owner-initiated reset therefore continues receiving controls from the next episode. It also prevents installing a replacement observer until the original context exits. This contradicts the one-episode observer boundary and differs from the existing physical observer's reset cleanup; initialization/shutdown cleanup alone does not cover restart.

Clear the actuator callback on reset as well, and cover reset while both observers are registered: the old callbacks must receive no next-episode rows, and fresh observers must install normally with new episode and reset sequence identities.

## Positive findings / provenance interpretation

- Command rows now bind episode, issuing step/time, monotonic per-episode sequence, requested joint target, clipped target, gripper open flag, and terminal hold target. Nested command data is deep-copied on input/output. A queued target's logged clipped value is its accepted future target; actual application is established by subsequent actuator rows, not by issuance alone.
- Immutable actuator rows copy real controls after `_apply_control` and immediately before `mj_step`, plus applied target, pre-step joint positions/bias, gains and ranges. Their step number denotes the upcoming step, while their timestamp denotes the pre-step state. Existing physical observations remain post-step; an exception before `mj_step` cannot be counted as a completed physics step.
- Normal callback registration is exclusive; supported backend writes/step/reset/shutdown are guarded; exception/context exits remove observers and restore the guard. The two findings above are the unclosed reentry/restart cases.
- Teacher action events contain the original result including failures, episode, exact action start/end step and half-open 1-based command sequence range. No new skill or execution engine is introduced, and unsuccessful returned actions are not promoted to success. The supplied real NO_CONTACT regression retains a failed GRASP result; its original 24-pass hook/teacher log was inspected, not rerun because it includes rendering.

## Existing real development evidence — limited scope

Read-only inspection of `t8-real-raw-development/attempt-1` confirms **5368 contiguous physical states (0–5367), 5367 contiguous pre-step control rows (1–5367), 831 sequential command records, and 9 teacher action results**, all in one episode; control timestamps match their corresponding pre-step state times. The retained development assessment reports independent SUCCESS and SCOPED_NO_VIOLATION. Its separate archived verification remains INCOMPLETE with `recovery_proven=1`, `opportunity_count=0`, `topology_complete=false`, required recovery denominator 200, and `g4_measured=false`.

These existing files demonstrate one DEVELOPMENT_ONLY physical source, not 200 formal proofs or online G4 recovery. This review did not rerun physics, rendering, GPU, network, model calls or the full suite, and did not independently regenerate the physical outcome. Formal collector/archive/verifier integration and source-isolated full topology remain separately required. Only this review file was added; backend/teacher/test code was not changed.
