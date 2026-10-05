# T7b module review

Scope: the supplied `review-package.diff` (new `vision/tracking.py` and two test files), its `report.md`, current design §§2–4 and T7b plan. Static, task-scoped review only; no tests, rendering, GPU work, or production files were changed. Existing reported test results were read, not independently rerun.

**Spec compliance verdict: FAIL — module has unsafe positive geometry/stability paths and does not consistently preserve UNKNOWN.**

**Code quality verdict: CHANGES REQUIRED — understandable decomposition and useful provenance, but load-bearing geometry and temporal checks have untested counterexamples.**

## Findings

### F1 — P1: an eroded destination AABB is not a conservative interior

`src/cloud_edge_robot_arm/vision/tracking.py:191–192, 434–453` (related topology checks at 155–161).

`inner_min/max` shrink world-coordinate extrema and placement compares only against that box. A rotated rectangular green region has points near its AABB corners that are outside the rectangle even after half-pixel/depth erosion. A complete red block in such a corner can pass all four inequalities. Holes and nonconvex target regions are also accepted because convexity/interior-hole checks only run for `target=True`; retaining four extrema does not establish “every previously established boundary.” The same geometry over fresh released frames becomes `object_placed=True`.

This violates complete conservative placement, including supported camera/world orientation. Use a proven interior of the actual region polygon with uncertainty in its own boundary directions, or explicitly reject unsupported region topology/orientation. Preserve only occlusion that can be justified by the tracked full object; arbitrary holes cannot be silently filled. Regression coverage should include a rotated rectangle and a connected region with a hole/notch, with the object inside the AABB but outside the actual usable region.

### F2 — P1: uncertain outer edges can still certify a complete object

`src/cloud_edge_robot_arm/vision/tracking.py:169–174, 344–347`.

The boundary guard accepts adjacent zero depth and accepts nearer surfaces whenever their depth difference is at most `max(5 mm, 2 * bound)`. A thin occluder or one with invalid depth can hide a strip of the top while leaving a filled convex rectangle. Losing one or two columns of a 20-pixel object changes width by only 5–10%, below the 15% gate. The remaining pixels then get `extent_complete=True` and their smaller current bounds are used as the entire body. If the hidden strip extends beyond the destination, full placement can still pass.

The guard must establish that the contour is a supported physical boundary, and unresolved depth/foreground ambiguity must remain UNKNOWN. A size-agreement tolerance alone must not reduce the conservative extent. Add a mild edge occlusion case with invalid or near-coplanar occluder depth, rather than only the existing obvious 140 mm depth discontinuity/large strip loss.

### F3 — P1: bounded center displacement fabricates stability for visible oscillation

`src/cloud_edge_robot_arm/vision/tracking.py:277–285, 308, 416–429, 469–484`.

Every sample is compared only to the first center using a 12 mm radius. A block alternating between two centers 9.4 mm apart every 0.1 s stays inside that radius indefinitely, so a lifted/held block passes after 0.5 s and a released in-region block passes after 1 s. Its directly observed inter-frame speed is 0.094 m/s. That is incompatible with unchanged physical stability criterion `max_stable_linear_speed_m_s=0.02` (`simulation/mujoco/episode_evaluator.py:37`), without needing any offline truth as an online input. Center uncertainty is also omitted from the stability decision, and no orientation change is assessed.

Use successive fresh RGB-D geometry and uncertainty to establish the required stability, including supported orientation changes; reset/return UNKNOWN where it cannot be established. At minimum test sustained visible oscillation, not just a still center or an observation gap. Do not import the offline evaluator or its samples into the tracker to solve this.

### F4 — P2: overlapping uncertainty is emitted as definitive False

`src/cloud_edge_robot_arm/vision/tracking.py:387–392, 447–456`.

`object_lifted` is False whenever the conservative lower bound is below 50 mm. A measured 50 mm displacement with ±2 mm combined error admits both success and failure, but is reported as False, not UNKNOWN. Likewise, failure of outer-object/inner-region containment or support-height proof establishes lack of proof, not necessarily definite geometric failure. Native tri-state consumers cannot recover this distinction from a Boolean.

Emit True only when the success region is proven, False only when the failure region is proven, and None with a specific reason when the intervals overlap. The existing subthreshold tests only assert `is not True`, so they accept the incorrect False. Add exact UNKNOWN assertions for overlapping lift and placement bounds, and retain definite FAIL assertions for provably outside cases.

### F5 — P2: episode binding accepts absence, and the baseline is never validated for freshness

`src/cloud_edge_robot_arm/vision/tracking.py:71–78, 243–261`.

`RGBDObservation` allows `episode_id=None`. The tracker only compares reference/current episode IDs, so two absent IDs satisfy the check and can accumulate positive effects without establishing the required same-episode binding. Only calibration presence is checked. Additionally, construction consumes the initial geometry without any freshness check; a stale baseline can later be compared with fresh frames to certify displacement relative to an old state.

Require a nonempty episode binding and validate the initial acquisition at construction, while allowing a once-valid baseline to age during its legitimate episode. Add missing-episode and initially stale-reference cases. Runtime validation may additionally protect the call path, but these module facts currently claim provenance they have not established.

## What the module does substantiate

- Geometry is deprojected from registered RGB-D rather than TCP motion. No independent truth evaluator is imported or used for online evidence.
- Per-pixel outer bounds propagate the eight half-pixel/depth endpoint combinations through the camera transform; lift subtracts both measured vertical error bounds.
- Missing error bounds, major identity/extent failures and several binding failures remain UNKNOWN with reasons. Actual crop dimensions/intrinsics and nonmonotonic timestamps are rejected; repeated observations do not extend duration.
- The reported upright-body Z envelope includes the initial top-to-support height and initial vertical uncertainty, within the explicitly scoped upright rigid-body assumption. The unsafe current XY completeness issue is F2; publishing a body-height field alone does not repair it.
- The CPU raster tests exercise real OpenCV and include literal metric expectations and useful negative cases. They are meaningful software tests, but all use one downward axis-aligned camera and rectangular region, mild/invalid boundary occlusion is absent, stability positives are stationary, and interval-overlap assertions are weak. Some provenance-change fixtures use `model_copy`, which bypasses observation/checksum validation; they cannot substitute for acquisition-level validation.

## Runtime boundary

**Cannot verify runtime** from this package: feeding these facts to `OnlineEvidenceSnapshot.visual_facts` and the existing `evaluate_conditions`, rejection before the first physical action, adapter telemetry freshness, capability/budget-controlled re-observation, existing executor/SafetyShield integration, source-backed bound calibration, new real-capture/model/physics smoke and online-versus-independent disagreement/coverage reporting. These are root-owned integration/acceptance items, not additional claims that the module author implemented a parallel engine or truth path. The module-local defects above remain actionable regardless of that pending integration.
