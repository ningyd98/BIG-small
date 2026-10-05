# T7b fix round 1 independent review

**Verdict: REQUEST CHANGES.** Spec compliance remains FAIL; code quality requires changes for the two load-bearing issues below. Reviewed the original review, `fix-round-1.diff`, appended report, current tracker and scoped tests. No suite rerun, GPU, network or live capture. One small CPU-only geometry probe was run, as detailed below; production/tests were not edited.

## Status of original findings

| Finding | Result |
| --- | --- |
| F1 conservative region interior | Partially fixed: rotated raster/world-yaw regions, holes and notches now reject; tilted-camera actual geometry still bypasses the new gate. |
| F2 uncertain target boundary | Addressed for reviewed cases: invalid/coplanar/nearer perimeter depth rejects, and accepted sampling shrinkage no longer reduces the full XY envelope. |
| F3 physical stability | Partially fixed: observable endpoint oscillation/uncertainty is checked; unobserved interval motion and square rotational symmetry still receive positive physical-effect facts. |
| F4 UNKNOWN versus definite failure | Addressed: lift interval overlap and placement overlap now remain UNKNOWN; definite failures have separate checks. |
| F5 episode/fresh baseline | Addressed: constructor validates initial freshness and nonempty episode before geometry; current acquisitions retain binding/freshness checks. |

## R1 — P1: endpoint consistency still becomes a full stability certificate

Locations: `src/cloud_edge_robot_arm/vision/tracking.py:226–240, 331–344, 496–510, 567–582`; positive assertions in `tests/test_visual_effect_evidence.py:29–51, 95–125, 141–162`.

`(endpoint displacement + endpoint uncertainty) / elapsed` bounds endpoint net displacement per unit time, not the maximum physical speed during that interval. An object can move away and return between samples, giving the same images as a stationary object. Increasing spatial precision or assigning a smaller synthetic depth error does not resolve that temporal ambiguity. The 0.2-second sample-gap cap alone supplies no bound on intervening dynamics.

The square top has a separate alias: `orientation_rad` is reduced modulo π/2 and the change uses the shortest modulo-π/2 distance. A uniform square rotating by 90 degrees between each pair of acquisitions produces the same top geometry as a stationary square; at 0.1-second intervals its rotation would be approximately 15.7 rad/s, despite the endpoint calculation indicating little or no angular change. The code has no independent observation or justified bound that excludes this. It nevertheless emits `object_stable=True` after 0.5 seconds and `placement_stable/object_placed=True` after 1 second. The appended report acknowledges the ambiguity but does not restrict these native completion facts.

**Required correction:** keep sampled endpoint consistency as a diagnostic measurement, with names that do not claim maximum physical speed. For native physical-effect conditions, unsupported inter-frame dynamics or unresolved square symmetry must produce `value=None` with explicit reasons. PASS requires independently justified, source-backed sensor/temporal bounds or validated state assumptions that establish the necessary interval behavior and resolve symmetry; neither arbitrary constants, endpoint calculations, synthetic precision, nor offline truth are substitutes. If such evidence is not available in this module, retaining UNKNOWN is the correct implementation. Do not loosen physical criteria or introduce a parallel completion path.

**Regression requirements:** fresh, high-precision, apparently identical square frames without interval/symmetry support must not certify full stability; distinguish endpoint consistency from physical effect status. Cover potential out-and-back motion and quarter-turn aliasing as indistinguishable observations with missing required support, rather than inventing hidden-motion ground truth for the estimator. The current low-resolution translation-oscillation negative fixture already returns UNKNOWN when completely still, so supplement it with precision sufficient to test the actual successive-displacement rejection.

## R2 — P1: world-region gate checks synthetic equal-depth corners, not the observed plane

Locations: `src/cloud_edge_robot_arm/vision/tracking.py:202–224, 528–532`.

The orientation test assigns the median optical depth to all four image corners. With a pitched camera, this fabricated rectangle can have world-axis-aligned edges even when the observed horizontal-plane image rectangle deprojects to a trapezoid. The actual point extrema are subsequently eroded into an AABB, again certifying points outside the true region. A rectangular image mask and flat world Z do not eliminate perspective distortion.

**Independently checked CPU counterexample:** build the existing valid 800×640 raster with a 30-degree pitch, rotation rows `(1,0,0)`, `(0,-cos(a),-sin(a))`, `(0,sin(a),-cos(a))`, translation `(0,0,1)`. Use observed plane depth `d=1/(cos(a)-sin(a)*(y-320)/1000)` and multiply target-top depth by `0.94`; supply the fixture-owned 1µm depth bound. The real constructor accepts this observation and the region has `extent_complete=True`. Its alleged inner corner `[0.05458505587737271, -0.6300360500597076, 0]` reprojects to pixel `[446.21765342886107, 358.6329778723874]`, outside the actual green pixel X interval `[450,609]` (Y interval `[200,359]`). Thus the purported guaranteed interior is demonstrably not an interior. Probe exit 0; no rendering/model/truth path used.

**Required correction:** either enforce the supported truly top-down camera/plane configuration and reject pitch/perspective cases as unsupported, or derive the actual world boundary/plane polygon from measured depths and propagate uncertainty into a genuinely conservative interior. Do not use constant-depth fabricated corners as proof of observed region shape. Add a valid-checksum pitched-camera counterexample that asserts rejection/UNKNOWN or correct conservative geometry.

## Evidence and scope

The reported 46-test green result was not rerun. New hole/notch, mild/invalid boundary-depth, binding/freshness and interval-overlap tests are relevant; valid observation reconstruction in the newer fixtures improves provenance coverage. The high-resolution 1µm fixtures are explicitly synthetic and acceptable for spatial unit-test precision, but their positive stability assertions currently claim evidence that spatial precision cannot supply.

No truth input, parallel action engine, or relaxed duration/lift thresholds was found in this fix. Runtime integration with `OnlineEvidenceSnapshot`, the existing `evaluate_conditions` and executor, telemetry provenance, calibrated operational bounds, and real smoke/independent physical agreement remain **cannot verify runtime** in this module review. These external acceptance items do not resolve R1/R2.
