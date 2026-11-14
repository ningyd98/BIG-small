# Cloud Vision Fallback Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. Steps use checkbox tracking.

**Goal:** Add the user-selected cloud image assistance route after local grounding fails.
**Architecture:** A strict image-candidate protocol replaces the single cloud skill-only
request on eligible failures. The existing worker-owned fresh capture validates all
candidates locally before any simulated action.
**Tech Stack:** Python, Pydantic, existing Chat Completions transport, OpenCV, MuJoCo, pytest.
**Spec:** `docs/superpowers/specs/2026-11-14-cloud-vision-fallback-design.md`

## Global Constraints

- Opt-in MuJoCo component diagnostics only; default disabled; no hardware qualification.
- One cloud request, four native generations, two planning phases, no retries.
- Keep selected Sol profile, camera, marker, controller and geometry gates.
- Freeze route policy and source hashes; archive image/request/response provenance.

## Review Focus

- Invalid or injected cloud coordinates must never reach geometry or execution.
- Native binding/configuration/freshness failures must never send images.
- A cloud reply delayed beyond five seconds must require a new actual worker frame.
- Fresh RGB/session/calibration/depth changes must prevent candidate reuse.
- Flag/configuration changes after binding must fail before paid requests or actions.

### Task 1: Candidate protocol and guarded planner route

**Files:** Create `vision/cloud_vision_fallback.py` and `tests/test_cloud_vision_fallback.py`;
modify `vision/grounded_planner.py` (paths under `src/cloud_edge_robot_arm/`).
**Consumes:** RGBDObservation and GroundingTaskDescriptor, existing paid cloud transport.
**Produces:** Validated 2-D candidate + whitelisted skill intent, reused only after owned capture.

- [x] Write failing tests for candidate recovery, unchanged successful route, malformed/refused
  replies, binding/freshness rejection, depth/contour rejection and post-cloud frame changes.
- [x] Run tests red; implement strict protocol, eligible fallback and fresh local recheck.
- [x] Run targeted tests green; preserve original local failure and cloud point provenance.

### Task 2: Bound opt-in entry and real worker integration

**Files:** Modify `research/sol_molmo_single_episode.py`, `vision/molmo_worker.py`,
`research/sol_molmo_components.py`, `scripts/run_sol_molmo_single_episode.py` and focused tests.
**Consumes:** Task 1 constructor flag and fresh-candidate route.
**Produces:** CLI opt-in frozen into job and role policy, audited under unchanged request budget.

- [x] Write/run failing entry, binding and real MuJoCo worker tests with external boundaries replaced.
- [x] Implement flag propagation, exact policy validation and source sealing.
- [x] Run green CPU and real-MuJoCo integration checks; verify a rejected candidate causes zero actions.

### Task 3: Verification and delivery

**Files:** Update existing research usage documentation and this plan's ledger.
**Consumes:** Tasks 1–2 behavior and test evidence.
**Produces:** Reviewable patch, validation report and pushed research-branch commit.

- [x] Run focused and related tests, lint, type checks and bounded full-project regression.
- [x] Obtain one fresh read-only branch review; address actionable findings with regression tests.
- [x] Record actual-model testing separately; do not claim an accuracy/success-rate improvement.
- [ ] Commit only source/tests/docs, push the existing research branch, verify local/upstream/remote SHA.

## Verification record

Final affected suite: 343 passed (35.39s); related suite: 103 passed (75.29s).
Ruff passes for the eight changed Python files. Targeted mypy reports 15 existing
diagnostics, identical to exact base `21203c46808e2e253b3e539cb1104fa9c81a20b6`
after normalizing line numbers; no added diagnostics.

Bounded full-project pytest stopped after 94 passes at
`test_model_control_public_api_has_chinese_docstrings`; the same failure (seven
missing Chinese docstrings) reproduces in an isolated exact-base snapshot.
This delivery does not claim the full project suite is green.

One read-only Astra review found two upload-eligibility gaps. Regression tests first
reproduced seven failures, then passed after restricting native exception fallback
to inference timeouts and validating raw/result consistency before absence/invalid
classification, with a narrow evidence-checked token-cap exception.

Live image smoke is separately prepared for at most three archived synthetic cases,
with zero execution and no retries. Host credential preflight succeeds. Automatic
approval review rejected image transmission because the prior explicit permission
covered text and geometry; a separate image-upload question is pending. No live
request has been sent. This does not block committing the opt-in implementation.
