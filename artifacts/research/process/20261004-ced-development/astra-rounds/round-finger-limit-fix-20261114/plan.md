# Finger limit monitoring implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline implementation and one final fresh-context review.

**Goal:** Stop the MuJoCo component run at the first finger position outside the unchanged physical bounds plus 1e-4 m.

**Architecture:** Extend `check_component_hard_state` using model joint addresses, live finger qpos and static ranges. Keep the existing arm loop and its 1e-6 rad tolerance. No evaluator truth enters online decisions. Use a separate offline verifier for recorded trajectories; keep the original pinned diagnosis script intact.

**Tech stack:** Existing Python, pytest, MuJoCo; CPU replay without models or rendering.

**Spec:** User-supplied `finger-limit-fix-plan.md` and message dated 2026-11-14, frozen with SHA256 in the delivery inputs. This bounded plan implements its monitoring scope, with the rulings below.

## Global constraints and rulings

- Preserve controller, physics asset, seven-arm-joint velocity checks, evaluator criteria and data classes.
- Check both finger lower/upper bounds and nonfinite readings; no new finger velocity threshold.
- Only robot feedback and static joint limits are added to online access.
- A true stop truncates each trajectory at its first bad step. The historical 5/54/426 violations remain a separate frozen-data check, not a live-run expectation.
- The online arm tolerance remains stricter than the evaluator. Claim equality of finger decisions, not universal equality of every safety decision.
- Regress the 40 frozen cases locally: replay recorded actions with the new guard and compare their physical prefix; 12 cases with no recorded actions are evidence-only checks. This does not constitute a fresh model-driven 40-case run or a new success-rate estimate.
- Existing paid-test approvals were consumed. This round makes zero model/API calls; no new spending authorization is needed for local replay.
- Monitoring does not remove overshoot or prove its relationship to GRASP_LOST. Do not change the 0.1 mm evaluator tolerance to accept overshoot below 0.5 mm.
- Correct the supplied failure accounting: 12 pre-action depth refusals, 5 visibility refusals (3 after MOVE_ABOVE, 2 after PLACE), 2 safety terminals, 1 GRASP_LOST. The last three have finger-limit evidence, leaving 17 other failed cases.

## Review focus

- Both fingers, both bounds, nonfinite qpos and exact tolerance boundary.
- Stop propagates out of a multi-step batch; safe_stop does not add a physics step.
- Online code must not consume object poses, contacts or independent outcomes for finger checks.
- Replay must bind original manifests, source/asset hashes and exact physical prefixes, including expected truncation.
- Preserve the distinction between evidence-only, recorded-action replay and fresh end-to-end evaluation.

### Task 1: Extend the online guard

**Files:** modify `src/cloud_edge_robot_arm/research/sol_molmo_components.py`; create `tests/test_finger_limit_fix.py`.

**Interfaces:** existing `check_component_hard_state(backend, robot) -> None`; reject with `ComponentStopped("HARD_FINGER_LIMIT")`.

- [x] Write real-MuJoCo tests for both fingers, lower/upper limits, NaN/infinity, allowed boundary readings, read-only behavior and callback abort.
- [x] Run tests before implementation. Expected: missing finger monitoring fails; ordinary readings pass.
- [x] Add the smallest finger position check after the existing arm checks; read by model qpos addresses.
- [x] Run new and existing component safety tests. Expected: all pass, original arm checks preserved.

### Task 2: Validate the frozen evidence and deliver

**Files:** create `scripts/verify_finger_limit_fix.py` and focused verifier tests; derived report under this round.

**Interfaces:** CLI accepts original 40-case root, frozen three-case diagnosis root and a new output root. Produces per-case verification, a 40-case summary and source/input hashes; it calls no planner.

- [x] Test evidence binding, physical-prefix mismatch detection and output isolation before implementing the verifier.
- [x] Check the new guard against all 485 frozen violation snapshots. Expected: all rejected as finger limits, original bytes unchanged.
- [x] Replay all 28 recorded-action cases. Expected: 3 stop at the original first violation during APPROACH; 25 match their full original physics; the 20 original successes are retained in recorded-action replay.
- [x] Verify the 12 no-action cases as evidence-only, not fresh planning decisions.
- [x] Run the prior 385-test selection plus affected/new tests, bare bounded project pytest, and six stored actual-occluder controls. Report baseline failures by name.
- [x] One independent final review; fix significant findings using RED/GREEN evidence.
Publication follows verification: freeze source/report hashes, commit explicit paths and push the existing user-authorized public research branch, then verify local/upstream/remote SHA. Actual publication status is recorded separately in git-delivery-receipt.json to avoid a self-referential commit SHA. Raw RGB/depth, DBs and credentials stay local.
