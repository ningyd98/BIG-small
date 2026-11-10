# R554 Post-cloud Fresh Revalidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The user has authorized continuation and the parent implements inline; no additional approval round. Steps use checkboxes.

**Goal:** After one valid cloud skill decision, optionally acquire and independently ground one genuinely new observation before the existing pipeline constructs a validated contract.

**Architecture:** Add an optional capture supplier to the existing grounded adapter/factory; reuse its two-query perception and the unchanged association, calibrated geometry and OpenCV tracker on each observation. A narrow paused-MuJoCo consistency policy links the cloud reference to the new observation. The existing draft carries the fresh scene and the existing pipeline issues trusted fields; no pipeline rewrite.

**Tech Stack:** Existing Python/Pydantic, NumPy/OpenCV, Molmo native runtime, MuJoCoCaptureSession, selected Sol transport and PlanningPipeline.

**Spec:** `request.json` and `design.md` in this round. Planner: actual `gpt-6-astra`. Baseline HEAD: `ae9cbf0b6bb5330de799004c664749ee462c3329`.

## Problem, evidence and diagnosis

R550 performed a real native load/two generations and one paid request. The cloud completed in **5.796200640994357 s**; the reference capture was **7.956878 s** old. The actual pipeline correctly returned `REQUEST_MORE_OBSERVATION`, reason `capture_time_not_fresh`, contract null. Offline parsing/skill success did not establish an actual accepted contract. Preserve the frozen R550 response, pipeline return, execution result and all raw originals.

The current adapter checks the original observation's age after the cloud response. A cloud request longer than the immutable 5 s observation TTL therefore cannot produce a contract. The repair is a new observation and new measurements, not a refreshed timestamp. The existing pipeline accepts `draft.observed_scene` and issues trusted `issued_at` after planning; source inspection found no need to modify it.

All **21 request inputs** were verified for SHA256 and byte count. `plan.json` contains their complete exact inventory plus the request, design, focused baseline and additionally inspected camera/session sources. Baseline `baseline-focused.log`: **102 passed**. MuJoCo camera source adds fresh Gaussian depth noise with default sigma **0.001 m** even while physics is paused; exact depth byte equality is consequently not a valid same-scene requirement.

## Global constraints and acceptance boundary

- Default supplier `None` preserves legacy ordering, rejection behavior and unchanged 5 s / 50 ms age gates. No global TTL, clock, transport, calibration, tracker, association or model-runtime changes.
- Original request, task, provider, supplier, cloud instance/profile/settings remain bound throughout. No activation/profile switch: existing Sol official route, `low`, `max_completion_tokens=4096`, `json_object`, timeout 30 s, strict endpoint/security and no retry.
- The fresh path runs only after strict duplicate-key/nonfinite JSON rejection, typed skill parsing, nonempty list and the existing exact skill-order validation. Invalid/empty/wrong-order replies never call the supplier.
- One supplier invocation, two fresh native queries, no second cloud request, no fallback to old geometry. Any failed consistency/perception/depth/freshness gate fails closed with partial provenance retained.
- This opt-in is a **paused MuJoCo development** policy. Same pixels/component supports and bounded depth residuals are scene-consistency diagnostics, not proof of physical identity, continuous stability, metric effects or formal sensor error bounds. Do not populate `depth_error_bound_m` or promote tracker UNKNOWN facts.
- No hardware, robot movement, physics stepping, episode reset between captures, instance-label/scene-truth input, paid retry, or modification of frozen prior evidence.

## Review focus

- Skill parsing and context checks must occur before any refresh; T2 tests malformed and mutated replies/context.
- Metadata-only retiming and cached-frame reuse must not be treated as acquisition; T1/T3 test IDs, timestamps, checksum validation and the real capture method call.
- Paused capture can have different depth noise; T1 tests allowed noise and independent residual rejection boundaries.
- Two equal-colored candidates or a changed component cannot retain the reference identity; T2 tests component-support mismatch and unchanged tracker ambiguity gates.
- Freshness can expire during either fresh query or contract construction; T2 tests final rejection without a stale contract.

## Locked interfaces and consistency policy

Add `post_cloud_observation_supplier: Callable[[], RGBDObservation] | None = None` to `MolmoGroundedPlannerAdapter.__init__` and `build_molmo_grounded_planner`. Capture its reference at plan entry, along with provider/cloud identities; recheck these and existing request/task/settings hashes before/after cloud, supplier and each local query. Separate context checking from age checking so the opt-in can reject drift after cloud without requiring the old observation to become fresh. Record UTC and monotonic cloud-return/capture boundaries honestly.

Create `vision/revalidation.py` with:
`validate_post_cloud_observation(reference: RGBDObservation, candidate: RGBDObservation, *, not_before: datetime) -> dict[str, Any]`.
It raises `ValueError` with a specific rejection reason and otherwise returns serializable policy/measurement evidence. Policy ID: `paused_mujoco_rgb_depth_v1`; fixed, not user-tunable in this round:

1. Revalidate both payloads through `RGBDObservation.model_validate(model_dump())`; never repair their checksums. Require nonempty same scene/episode/calibration, source `mujoco_camera`, identical dimensions, intrinsics, transform, optical-depth convention and **exactly equal sim_time_s**. Candidate frame/observation ID and checksum must differ from reference. Require candidate captured_at strictly later than reference and at or after `not_before`, recorded immediately before the sole supplier invocation after cloud return. Existing fresh-age checks also apply.
2. Require identical RGB SHA and valid-mask bytes, with at least one valid pixel. This deliberately rejects lighting/render changes and simulation motion rather than claiming semantic matching of changed scenes. It may false-reject; do not relax it in response to a real failure without another Astra plan.
3. On all mutually valid optical-depth pixels, compute float64 `delta = fresh - old`; require `max(abs(delta)) <= 0.010 m`, `sqrt(mean(delta**2)) <= 0.002 m`, and `abs(mean(delta)) <= 0.00025 m`. Record all three and the valid count. These **new engineering anomaly guards** allow the inspected 1 mm independent rendering noise (expected pair RMS about 1.414 mm), reject large local/coherent changes, and make no statistical guarantee or calibrated physical-error claim. They are separate from every existing geometric threshold. Exact equality of depth bytes is allowed for a genuine capture; payloads alone cannot prove trusted acquisition against a malicious supplier.
4. After both independent local grounding passes, require identical SHA256 of each target and destination tracker boolean support mask, including its shape, old versus fresh. Keep target and destination roles separate. No global nearest-object matching, IoU relaxation, label-based identity certificate or substitution of old pixels. Fresh points must independently bind to their fresh RGB/checksum/query and pass existing uniqueness, contour, raw-depth and calibrated-height rules.

CLI is the trusted acquisition boundary; arbitrary caller-supplied observations cannot themselves prove when a sensor exposure happened. Its supplier must call `MuJoCoCaptureSession.capture()`, never copy/relabel/retime an observation or call cached `get_sensor_frame()`. The unchanged sim_time is documented as paused scope, not temporal-motion coverage.

### Task 1: Pure fresh-observation policy and shared skill-order check

**Files:** Create `src/cloud_edge_robot_arm/vision/revalidation.py`, `tests/test_molmo_revalidation.py`; minimally modify `src/cloud_edge_robot_arm/vision/planner.py` to extract the existing exact sequence check as `validate_grounded_skill_order(skills: list[SkillIntent]) -> None`, and have `build_grounded_contract` call it without changing errors or allowed optional boundary HOME skills. No geometry changes.

- [ ] Write parameterized RED tests for valid independently captured payloads with deterministic zero-mean +/-1 mm residuals; each threshold independently exceeded; invalid mask/nonfinite/malformed/checksum; same ID, old capture time, pre-callback time, scene/episode/camera/source/calibration/sim-time changes; one-pixel RGB change; no valid depth. Build valid fixture models including required `sim_time_s`; assert exact returned metrics/policy and rejection reason. Test each equality boundary and a value clearly above it without floating-point ambiguity.
- [ ] Run `.venv/bin/python -m pytest tests/test_molmo_revalidation.py -q` using the original app interpreter and worktree cwd/PYTHONPATH. Preserve raw RED output; expected missing new function/module or missing behavior, not a broken fixture. Run existing RGBD planning tests for the extracted validator.
- [ ] Implement only the policy and shared validator described above. Keep numeric operations bounded by the validated image size; no model/OpenCV tracker invocation in the pure policy.
- [ ] Run new policy and existing RGBD planning tests; save GREEN results and scoped diff. Commit explicit verified T1 paths.

### Task 2: Optional adapter revalidation, fresh-only contract and provenance

**Files:** Modify `src/cloud_edge_robot_arm/vision/grounded_planner.py` and `tests/test_molmo_grounded_planner.py`. Reuse T1 helper and validator. Keep `pipeline.py`, tracker, top-grasp, observations, pointing and association sources unchanged.

- [ ] Add RED tests for an initially fresh reference whose cloud reply takes >5 s: default path still rejects; opted-in valid reply invokes one supplier and four total point queries, with final contract/observed_scene/geometry all derived from fresh payload. Use a deterministic clock and a **phrase-aware, observation-bound** provider; the existing FixturePoints len(queries)==1 shortcut is unsuitable for a third query. Verify original request bytes/hash are unchanged and pipeline trusted issued_at follows fresh capture.
- [ ] Add RED negatives: malformed/duplicate/nonfinite/unknown/extra-field JSON, empty or wrongly ordered skills => 0 refresh and only initial two queries; supplier exception/invalid type or model_copy checksum bypass; context/task/profile/settings/provider/supplier drift during cloud or refresh; reused/pre-cloud/wrong-episode frames; changed RGB/depth or component mask; ambiguous/truncated/missing/invalid-depth fresh support; fresh TTL expiration during each query and at the final return. Assert no cloud retry and contract null. A second same-colored candidate must be rejected by the existing tracker, not rescued by the comparison policy.
- [ ] Extract only the duplicated local sequence into a private adapter helper returning grounded scene, per-frame evidence and target/destination support-mask hashes. It must run unchanged domain checks, two exact task queries, point binding, normalized1000 mapping, bounded association, `ground_observation` and initial tracker gates for both frames. Preserve old exception/sentinel behavior on the default path.
- [ ] In opted-in path, strictly validate skills and context first, call supplier exactly once, apply T1 metadata/depth policy, run both fresh queries/grounding, compare support masks, and build the candidate using **only fresh** GroundedScene. Recheck context/freshness after construction before returning the draft. Fail closed at every stage with original real response retained.
- [ ] Keep final top-level observation evidence and native_results exclusively fresh; nest immutable original reference/query/geometry evidence separately as `cloud_reference`, and put policy, timing, hashes, residuals and outcome under `post_cloud_revalidation`. Record two unique perception frames/four queries on success; cloud images remain zero. Partial failure retains whichever fresh records actually exist and never marks validation complete.
- [ ] Factory passes the optional supplier and adds `revalidation.py` plus the acquisition `capture.py` source to role provenance. Do not leave new safety logic outside the source-hash inventory. Run new/default adapter tests, T1 tests, RGBD planning/top-grasp/role-model/tracker suites and pipeline integration assertions. Save outputs and commit explicit verified T2 paths.

### Task 3: Same-session CLI, verification, review and one bounded real attempt

**Files:** Modify `scripts/probe_molmo_grounded_planner.py`, `tests/test_molmo_grounded_cli.py`, `docs/research/molmo-opencv-grounded-planner.md`. Round-local implementation/evidence files may be created under this R554 directory; raw files go to a new local ignored dataset directory. Do not edit R545/R550 launchers or any historical raw.

- [ ] Add RED CLI tests for `--post-cloud-revalidate`: require native mode, `--capture-fresh`, explicit `--allow-paid`, **exactly one request/task pair** and `--generation-limit >= 4` (existing max8 retained). Reject bad combinations before resource/model/paid start. Existing default CLI tests remain unchanged.
- [ ] Add RED tests with fake resources/session/provider/transport: exactly one load/session, two calls to the same session's `capture`, no reset/step/cached getter between them, initial capture after model load, second capture only after a valid cloud response; malformed response causes one capture/two generations; supplier failure consumes no repeat. Verify lock/session/model cleanup on each failure and exact attempt counters/raw manifests. CPU tests do not instantiate native models or real HTTP clients.
- [ ] Implement flag and factory wiring. Hold one `MuJoCoCaptureSession` in the existing ExitStack across both captures; session owns setup/reset once. Preserve old capture helper path when flag absent. Save initial and refresh raw separately immediately after each actual capture, including full observation/request snapshot, RGB, original float32 depth and valid mask. Reports distinguish initial checksum from final plan checksum, one paid start, native generation starts and refresh capture start/outcome. No replacement or edits of saved initial files.
- [ ] Run focused tests, all adjacent suites (including `tests/test_opencv_target_evidence.py`, `tests/test_rgbd_capture_session.py`) and the repository full suite once. Run scoped Ruff, `git diff --check`; preserve exact command/output/status and distinguish known environment/preexisting failures from regressions. Do not repair unrelated failures under this plan. Update guide with opt-in semantics, paused scope, exact policy limits, provenance and no-retry budget. Commit verified explicit paths.
- [ ] Obtain a **fresh independent whole-change review** of implementation, tests, policy and provenance before real execution. Resolve only already-planned behavior; a new root cause or required scope expansion needs the next actual Astra plan. Review is an implementation gate, not another user permission loop.
- [ ] After software/review/resource gates pass, perform at most one new actual attempt using R545 original configure_overlay/launcher and the existing selected profile. A new R554 observational runner may reuse the frozen R550 pattern: original CLI/pipeline/process/_post called normally, return identical original objects, record UTC/monotonic times and real response/contract separately; hard paid-start cap1 before delegate, failures count, no retry. Test any new wrapper on CPU before native execution. Do not fabricate or reconstruct PLANNED.
- [ ] Save full local raw/manifest, native timings/query bindings, old/fresh captures and both geometry records, real cloud request/response/usage/model, actual returned contract and validation outcome. Verify manifest bytes/SHA. Produce step/phase reports with layered results, then explicit-path commit/push and compare local/upstream/remote SHA under AGENTS. Frozen whitespace-sensitive raw may use byte-preserving gzip publication rather than normalization.

## Execution preconditions and accounting

Before each mutation, recheck request/plan applicability and unchanged frozen inputs; after planned source changes, record output hashes rather than pretending original hashes still match. Managed-worktree writes and host GPU/loopback may require scoped escalation. CPU commands must use `PYTHONPATH=/home/ningyd/.codex/worktrees/molmo-opencv-integration/BIGsmall/src` and original `/home/ningyd/文档/ChatGPT/BIGsmall/.venv/bin/python`; the abbreviated `.venv` commands above refer to that original interpreter, not a missing worktree runtime.

Before native execution: R545 overlay identity/import/ABI preflight on the original validated Molmo interpreter, original assets only; no install/network/download/runtime/SDK changes. Verify selected profile snapshot/settings hash and secret presence without printing credentials. Verify GPU admission lock, no foreign compute, adequate VRAM/RAM/disk, writeable fresh raw root and no existing attempt directory. Native model construction stays on main thread after resource admission; no raw image/scene oracle is injected into task descriptions. Fresh task/request templates retain the already-authorized red-block to green-region instruction and use a new request_id; bind exact template hashes before load.

This planning turn consumes **0 model/0 generation/0 paid calls**. Prior actual totals are **3 loads / 6 generations / 1 paid attempt**. This round permits **at most +1 load / +4 generations / +1 paid attempt** after tests and independent review: cumulative ceilings **4 / 10 / 2**, zero hardware and zero formal research runs. Count starts including failure; unused allowance is not automatic permission for retries. Unexpected real rejection remains evidence and requires a new plan for any repair; do not change thresholds or clocks to obtain success.

## Separate acceptance levels

1. **Development:** Intended RED, all targeted GREEN, scoped lint/diff checks and independent review; full-suite failures classified honestly. Legacy default strict behavior retained.
2. **Real native:** Actual four query results bound to two genuine same-session captures, local policy/geometry passes within unchanged fresh TTL. Captures at equal sim_time do not establish physical motion coverage.
3. **Real cloud:** One actual selected Sol response with real usage/model and strict skill validation; this alone is not contract acceptance.
4. **Actual software contract:** Only the original pipeline returning PLANNED with non-null validated contract, fresh measured scene/evidence and genuine trusted fields counts. Otherwise report exact sentinel/error/null contract, even if offline replays pass.
5. **Physical/formal:** NOT_RUN. No hardware, controller effects, stability/placement or formal research claims.

Complete input SHA256 inventory is embedded in adjacent `plan.json`; its original 21 entries are copied verbatim from the verified request. Self-review completed against request/design; no unresolved interface decisions remain.
