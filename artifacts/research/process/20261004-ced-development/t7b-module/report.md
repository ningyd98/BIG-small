# T7b tracker module: software evidence only

Implemented `vision/tracking.py` plus `tests/test_opencv_target_evidence.py` and
`tests/test_visual_effect_evidence.py`. Existing execution, conditions, task semantics,
dependencies and global documents remain root-owned. No model/network calls,
commits, GPU smoke, additional reviewers, or hardware actions were performed.

## Behavior and boundaries

OpenCV connected components and contours identify a unique colored block and a
green target region. Registered metric depth is deprojected into world coordinates;
outer pixel-footprint/depth-error bounds describe the target and eroded inner bounds
describe the usable region. Facts include observation ID/time, episode/calibration,
algorithm and calibration hashes, geometry, complete-extent flags and UNKNOWN reasons.
Initial/destination center/min/max fields preserve the old tracker's interface.

Missing/ambiguous color, invalid target depth, nonplanar top, split/nonconvex/hollow
contours, foreground at an outer boundary, image-edge truncation, large dimension
changes, temporal jumps, changed camera/episode/calibration, old crops and nonmonotonic
captures produce UNKNOWN. Explicit positive `depth_error_bound_m` is required for
metric lift and placement proof; the tracker never fabricates a calibrated bound.

Lift is independently measured from RGB-D top-height change, subtracting both
height error bounds. TCP motion does not contribute to object geometry. A lifted
object requires at least 50mm lower-bound displacement; stable lift requires at least
0.5s continuous valid geometry and holding feedback. Placement requires full XY
containment, support-height consistency, observable release and at least 1s stability.
Observation gaps above 0.2s, UNKNOWN geometry, loss of holding feedback and movement
above 12mm reset the applicable evidence window. Repeated observations do not extend
duration. Simulator observations use sensor simulation time for metric duration;
real camera observations use capture time. Both times are recorded and captures
remain fresh and strictly monotonic. No detached truth or independent physical
evaluator is imported or consulted.

## Validation commands and exits

- Initial RED: `MUJOCO_GL=egl .venv/bin/python -m pytest -q
  tests/test_opencv_target_evidence.py tests/test_visual_effect_evidence.py`, exit 1:
  25 failures because the new production module did not exist (`red.log`).
- Initial GREEN attempt: same command, exit 1, 24 passed/1 failed: fixture outer
  edge was hand-calculated incorrectly by 0.055mm; corrected its literal expected
  boundary to `(15.5 - 40) * 0.94 / 100 = -0.2303m` (`green-initial.log`).
- Additional RED tests reproduced adjoining-foreground extent uncertainty, missing
  whole upright-body bounds, and unpaced simulator clock mapping; each exited 1
  (`red-edge-occlusion.log`, `red-body-extent.log`, `red-sim-clock.log`).
- Final targeted command above: exit 0, **28 passed** (`green.log`).
- `.venv/bin/python -m ruff check src/cloud_edge_robot_arm/vision/tracking.py
  tests/test_opencv_target_evidence.py tests/test_visual_effect_evidence.py`, exit 0
  (`lint.log`).
- `.venv/bin/python -m mypy src/cloud_edge_robot_arm/vision/tracking.py`, exit 0
  (`mypy.log`); the project emits an unrelated unused-overrides note.
- Began the skill-requested full `MUJOCO_GL=egl .venv/bin/python -m pytest -q`,
  then stopped gracefully at root request to preserve root-only GPU/rendering
  scheduling. Exit 2, **344 passed, 2 skipped, 2 failed**, unfinished
  (`full-suite.log`). The two failures were
  `tests/test_chinese_comment_checker.py::test_auto_mode_public_api_has_chinese_docstrings`
  and `tests/test_chinese_comment_checker.py::test_default_paths_cover_all_tracked_code_files`.
  Existing root-owned/doc-audit concerns; no fixes were attempted outside ownership.
  Root owns the complete integrated broad-suite run.

## Self-review and integration advice

The tests exercise real OpenCV on small manually constructed RGB-D rasters, with
literal independently calculated metric expectations. Self-review corrected compact
contours next to a foreground occluder and clock conflation between fresh wall
captures and accelerated simulation time. No test-only wrappers or truth paths exist
in production. The published upright-body bounds are derived from the initially
measured top-to-support height; they are scope assumptions, not arbitrary-object
completion. Sensor error/calibration coverage is supplied externally and remains
unvalidated by this software-only module.

Root integration must preserve the native facts and collect fresh frames at <=0.2s
intervals during lift and release holds. A single final capture after a 1.2s passive
dwell cannot prove continuous placement stability. Condition evaluation must retain
`value=None` and reasons as UNKNOWN and require `placement_stable`/`object_placed`
for final completion. `target_reachable` retains initial stationary-support behavior
and is intended for pregrasp checks, not transported-object completion. UNKNOWN
observations must not be replaced by old TCP-based tracker or physical evaluator.

Limitations: fixed registered camera, unique distinguishable colors, initially
complete upright rigid cuboid top, planar region and supplied support height; 15%
dimension agreement and 1.5m/s temporal association are documented scope gates, not
validated learned confidence. Occlusion has no hallucinated completion/recovery;
additional approved views belong to the existing executor. Calibration error,
coverage/UNKNOWN rates, real capture, runtime smoke, independent physical disagreement
and full T7b acceptance remain unverified until root's integrated tests and new smoke.

## Independent review fixes — round 1/5

Review `review.md` found F1–F5 and rejected the earlier module. These findings were
accepted after reading the actual source/fixtures. Pre-fix copies are retained in
`fix-round-1-baseline/`, and the source/test changes are recorded in
`fix-round-1.diff`. Earlier passing tests are not evidence that the reviewed unsafe
paths were acceptable.

- F1: destination certification now explicitly supports an axis-aligned filled
  rectangular image region whose deprojected edges are axis-aligned in world XY.
  Rotated diamonds/rectangles, holes, notches and rotated world orientations are
  rejected. At later frames, only missing color beneath the currently complete,
  independently verified target mask and the original region support can be
  explained; arbitrary holes are never filled. Current observed depth still
  measures the region; no hidden region depth is invented.
- F2: the complete target perimeter requires valid neighboring depth whose lower
  bound is strictly farther than the target's upper depth bound. Invalid,
  coplanar and mildly nearer borders remain UNKNOWN. The previous 5mm exemption
  is removed. The retained 15% sampling/identity gate cannot shrink the full body
  envelope: any deficit against initial extent expands both current edges by
  that deficit. Tests cover two missing columns of an 18-pixel top, with 0,
  0.938m and 0.94m occluder depths, in addition to the obvious occlusion examples.
- F3: successive samples include center and orientation uncertainty. A new stable
  interval requires the measured displacement plus both center error radii divided
  by the actual source-specific interval to be <=0.02m/s, and the orientation
  difference plus both angle error bounds divided by that interval to be
  <=0.5rad/s. Violations reset the active hold. The 12mm total-displacement guard
  remains additional. Visible translation and five-degree orientation oscillation
  no longer accumulate stable duration. Low-resolution evidence that cannot prove
  those bounds remains UNKNOWN. No physical evaluator is imported.
- F4: lift now publishes both lower and upper displacement bounds; True requires
  lower>=50mm, False requires upper<50mm, and overlap is specifically UNKNOWN.
  Placement is True only for conservative full containment and support agreement;
  False requires guaranteed object interior outside the region's outer bounds or
  guaranteed support-height violation. Overlapping intervals remain UNKNOWN.
- F5: initial construction requires fresh capture time, present calibration and a
  nonempty episode ID before creating the reference geometry. The once-validated
  baseline can age while fresh captures from that legitimate episode continue;
  current acquisitions still require unchanged bindings and fresh monotonic times.

### Round-1 evidence

`fix-round-1-red.log`: targeted two-file pytest exit 1, **15 failed, 26 passed**,
covering every F1–F5 finding before changing production. `fix-round-1-red-additional.log`:
**5 failed**, exit 1, for exact small-strip/world-rotation/angular-oscillation
counterexamples loaded against the saved real pre-fix module in a separate Python
process; production was not temporarily replaced. Initial green iterations exposed
three now-unsupportable coarse positive fixtures, then one stale synthetic-timestamp
fixture; those records are preserved.

Final `.venv/bin/python -m pytest -q tests/test_opencv_target_evidence.py
tests/test_visual_effect_evidence.py`: exit 0, **46 passed** (`fix-round-1-green.log`).
The three positive stability fixtures now use real 800x640 RGB-D rasters with a
60-pixel top and an explicitly supplied 1µm synthetic sensor-error bound. This is
test-owned evidence precision, not a fabricated production calibration. Actual fresh
capture timestamps are used for the heavier simulator fixtures; physics duration
remains the simulator source clock. The coarse 6-pixel/1mm fixture has its own exact
UNKNOWN regression. Scoped Ruff and mypy both exit 0 (`fix-round-1-lint.log`,
`fix-round-1-mypy.log`). No broad suite, rendering, network or hardware operations
were performed in this fix round.

Remaining limits: these are conservative sampled image estimates in a documented
upright rigid-body scope. The uniform-color square provides orientation modulo its
90-degree visual symmetry; angular aliasing and unobserved inter-frame dynamics need
separate source-backed observability/calibration validation, not claims of arbitrary
continuous physical motion proof. Scope restrictions may reduce real-capture coverage
and increase UNKNOWN. Root still owns integrated runtime/real smoke and independent
physical agreement, and the independent reviewer must re-assess this revised module.

## Independent review fixes — round 2

`fix-round-1-review.md` rejected the remaining physical-stability certificate and
pitched-camera geometry. The earlier limitation paragraph did not make those native
facts safe; this round changes their behavior and supersedes all earlier stability
PASS claims. Exact pre-fix files are retained in `fix-round-2-baseline/`; the review
diff is `fix-round-2.diff`.

R1: RGB-D endpoints cannot bound unobserved interval motion or distinguish complete
quarter turns of a uniform square. This module now emits **UNKNOWN unconditionally**
for `object_stable`, `placement_stable` and `object_placed`. Spatial precision,
duration, TCP endpoints and user-supplied grounding booleans cannot enable PASS.
Fresh height measurements can still prove the instantaneous metric lift; supported
complete geometric containment can still prove `object_inside_target_region`.
Neither implies continuous physical stability/completion.

Sample histories remain useful diagnostics. They publish
`net_endpoint_displacement_rate_upper_m_s` and
`modulo_quarter_turn_endpoint_rate_upper_rad_s`, explicitly naming their endpoint
and symmetry limitations. `endpoint_window_consistent` reports whether the sampled
endpoint history meets the duration/consistency checks, while native status remains
UNKNOWN. The required independent evidence is explicit in
`physical_stability_support`: source-attested same-episode identity/capture coverage,
validated interval-wide object linear-speed bounds <=0.02m/s and symmetry-resolved
interval-wide angular-speed bounds <=0.5rad/s. Status is `UNAVAILABLE`, accepted
support sources are empty, and no unsupported future provider/gate is invented.
Reasons identify `inter_frame_motion_not_bounded` and
`quarter_turn_symmetry_unresolved`.

R2: acquisition now explicitly requires a downward optical axis aligned with world
Z and pixel axes aligned with world X/Y. Pitch, roll and arbitrary yaw are unsupported
and rejected before geometry construction. Destination corner geometry uses those
actual corners' measured depths, never a fabricated median-depth plane. All region
points must observe one level plane within 1e-7m float32 rounding tolerance; noisy,
warped or unresolved region depth remains unsupported. This is intentionally narrow
scope until a separately validated measured polygon estimator exists.

### Round-2 evidence

`fix-round-2-red.log`: `.venv/bin/python -m pytest -q
tests/test_opencv_target_evidence.py tests/test_visual_effect_evidence.py`, exit 1,
**6 failed, 43 passed**. It reproduces the valid-checksum 30-degree pitched plane,
the formerly positive high-precision lift/placement endpoint claims, and identical
acquisitions consistent with either out-and-back motion or quarter-turn aliasing.
The latter tests provide no hidden trajectory to the estimator and explicitly show
that grounding flags do not resolve missing observability.

`fix-round-2-red-translation.log`: exit 1 for the high-precision visible translation
oscillation diagnostic. Unlike the coarse still-negative fixture, these endpoints
have sufficient spatial precision to exercise displacement-rate rejection. The
GREEN test requires visibility, rejects endpoint consistency and checks an observed
net-displacement-rate upper bound >0.08m/s. `fix-round-2-red-plane.log`: exit 1 for
equal corner depths with a deformed region interior, before the measured-plane check.

Final targeted command: exit 0, **51 passed** (`fix-round-2-green.log`, 21.58s). Scoped
Ruff and mypy both exit 0 (`fix-round-2-lint.log`, `fix-round-2-mypy.log`). No GPU,
capture rendering, network or full-suite work occurred in this round. Saved baselines
and RED records establish that these changes address observed failures rather than
silently weakening assertions.

Native full stability/completion is deliberately unavailable in this sensor-only
module. Root must preserve UNKNOWN through the existing runtime and obtain validated
interval-wide evidence before any future supported completion extension. Runtime,
calibration coverage, real-capture smoke and independent physical agreement remain
unverified; T7b is not claimed complete. The narrower camera/plane scope may reject
the current rendered camera and noisy inputs, which is a documented capability limit.
