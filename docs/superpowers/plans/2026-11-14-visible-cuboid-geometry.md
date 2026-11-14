# Visible Cuboid Geometry Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one fresh whole-change reviewer at the end. Steps use checkbox tracking.

**Goal:** Repair raster contour and edge-depth handling without weakening missing/occluded evidence gates.
**Architecture:** Measured top support anchored directly to visible RGB interior; half-pixel rectangle support; explicit invalid-depth diagnostics. Existing pipeline and authority remain.
**Tech Stack:** Python, NumPy, OpenCV, pytest, MuJoCo.
**Spec:** docs/superpowers/specs/2026-11-14-visible-cuboid-geometry-design.md

## Global Constraints

- Base bab220435ab3211adc40b2916325edc28477a00f; reuse current isolated research branch.
- No invented depth/error bounds; missing bound leaves extent/effects UNKNOWN.
- No filled pixels, relaxed foreground/invalid ring checks, altered camera or controller.
- One-cloud/four-native/two-phase budget unchanged; no paid development calls.
- Preserve all original raw and expose failures/limits, not a global-green claim.

## Review Focus

- Foreground or internal depth anomalies must not become a nominated top support.
- Small clipped convex silhouettes must still fail via boundary depth or reference size.
- A rectangle fit cannot supply unseen corners or calibrated metric confidence.
- Missing/invalid depth and insufficient interior must fail, including no-bound input.
- Production source sealing must include every modified geometry implementation.

### Task 1: Measured top support and refusal semantics

**Files:** Modify vision/tracking.py; create tests/test_visible_cuboid_geometry.py.
**Interfaces:** Keep _top_support(points, selected, ys, xs) -> selector, interval, reason.

- [x] Add tests: noisy lower boundary with no bound recovers visible top but not extent;
  near boundary/core spike rejects without a bound; calibrated support violation rejects.
- [x] Run new tests RED, then implement measured-gap clusters and explicit failure reasons (initial design; replaced
  with direct interior anchoring after the final review).
- [x] Run new depth tests + test_opencv_target_evidence.py GREEN; commit task.

### Task 2: Raster contour and invalid-background diagnostics

**Files:** Modify vision/tracking.py, vision/point_association.py,
research/sol_molmo_single_episode.py; extend tests/test_visible_cuboid_geometry.py.
**Interfaces:** Preserve tracker geometry and association result contracts; add audit fields.

- [x] Add rotated raster positives (14/24/32px, several yaw angles), notch/hole and
  foreground negatives; invalid-background/interior diagnostics; observe RED.
- [x] Implement half-pixel rectangle interior support, unchanged exterior depth checks,
  additive invalid-depth evidence, explicit tracking source hash in episode snapshot.
- [x] Run geometry, association, planner, cloud fallback and worker regression GREEN;
  update the fixture that formerly expected a raster-only failure; commit task.

### Task 3: Actual controls, frozen replay and delivery

**Files:** Add a bounded offline verification script and research usage/result documentation.
**Consumes:** Original frozen RGB-D evidence and modified production geometry.

- [x] Replay all 40 archived observations with diagnostic-only capture-time clock;
  store before/after reasons and immutable-input hashes. No plan/action authority.
- [x] Render fresh host MuJoCo normal, actual foreground occluder and table-edge controls
  at original resolution; archive renderer/settings and show refusal remains active.
- [x] Run appropriate broad tests, lint, type comparison and bounded full-project check.
- [x] Obtain one read-only whole-change review; fix important findings once with RED/GREEN.
- [x] Freeze an exact new 40-item matrix/source manifest, separately from old evidence.
- [x] Commit/push verified source, tests, derived docs only; verify local/upstream/remote SHA.
  Source delivery afc43e80 verified equal locally/upstream/remotely; external receipt retained.

**Expected:** Positive regression fixtures recover visible support; malformed, occluded,
invalid or unresolved evidence stops. No claim all 40 pass or task rate improves before
an independently authorized actual-model batch. Keep actual remaining blockers explicit.

Final verification: 385 affected tests passed in 62.52s; Ruff clean. Two targeted mypy
diagnostics and the global Chinese-docstring audit failure reproduce on exact base.
The single reviewer Important was reproduced, then fixed with direct measured-interior
anchoring and entire selected-top span checks; no final Astra approval is claimed.
Final visibility replay: fixed 10/10, development 8/15, disclosed old held-out 10/15,
28/40 overall; all 40 baseline gates reproduced, six actual occluders still refused.
The subsequently authorized actual-model paired batch completed 40/40: component physical
success 20/40 versus original11/40, image candidates12/12 but zero geometry recoveries,
40 cloud calls,136 native generations,195 actions; no retry/timeout/source drift. Remaining
12 depth refusals,5 moving-frame identity failures,2 safety terminals,1 grasp-lost terminal;
hard-limit evidence3 including grasp-lost. These remain explicit unresolved limits.
Post-push SHA receipt is saved externally in the
chat output package so it can refer to the exact delivered commit without self-reference.
