# Real development capture adaptation — software/CPU replay only

Scope: adapt `vision/tracking.py` and the two owned evidence test files to the saved
320x240 nominal S01 development capture. The accepted fail-closed baseline is retained
in `baseline/`; `adaptation.diff` records the complete scoped change. No source image
or depth payload was modified. No GPU rendering, fresh capture, model/network calls,
robot actions, commits or broad suite were performed. Physical success is NOT_RUN.

## Actual observation and correction

The unique red RGB component includes a visible upright side as well as its top.
The old algorithm demanded one flat plane for the whole color component and rejected
it. The adaptation keeps all registered colored pixels for observed silhouette/body
geometry, then proposes a separate top support using a data-derived Otsu height split.
A discarded lower mode must lie exclusively on the complete silhouette boundary and
between the supplied support height and the observed top; interior anomalies cannot
be relabelled as sides. This is a measured candidate segmentation, not confidence or
calibration. It does not widen a fixed millimetre plane threshold.

A positive externally supplied `depth_error_bound_m` can validate a horizontal top
only when all retained per-pixel height intervals intersect. No bound means
`top_plane_status=UNVALIDATED_DEPTH_ERROR_BOUND`, `extent_complete=False` and
`conservative_full_extent_min/max=None`. Full measured points and top/side quantities
remain observed-only diagnostics. The source noisy capture has no supplied finite
bound, so target reachability, lift, containment and all native physical-stability/
completion conditions remain UNKNOWN. Unique visible identity can be reported.

The green region has one antialias corner outside the selected color support. The
algorithm now uses a narrower rectangle whose entire interior is actually supported
by observed color, rather than filling that corner or declaring the whole bounding
box interior. Holes, deep notches and rotated unsupported regions still reject. A
validated horizontal plane intersects the rectangle's inside pixel rays; intersecting
the possible rectangles across the common calibrated height interval supplies the
conservative usable interior. Without a calibrated plane, its measured corner geometry
is diagnostic only and cannot authorize metric membership. Camera pitch/roll/arbitrary
yaw restrictions and native continuous-completion UNKNOWN remain unchanged.

## Immutable source and replay clock

Source: `../t7b-real-capture-v2/initial/observation-full.json`, `rgb.png`, `depth.f32`.
These development-only inputs are referenced directly and their exact SHA256 values
are asserted by the tests and recorded in `cpu-replay-assessment.json`:

- observation-full.json: `937f1044ee36332db0bc23598c026fcd67a226ece2e0225787f71cc25b2376e3`
- rgb.png: `419cab290f50df585986df994273154f5aafa10d50c9b72cd8edac65f6a1c77c`
- depth.f32: `3b6561d8de1b196dbac5dbc4fff466c09bfbaebd19a5062d568abd19da355481`

Original checksum: `55a2feabf510705f2029650a0a7decde0a3923e154e5c173d74a45e546966c7b`;
captured_at: 2026-10-04T08:33:45.968288Z. Tests explicitly replay the original acquisition
clock at +1s to inspect the immutable archived payload. This does not create a fresh
frame, edit its timestamp/checksum or claim new runtime evidence. The RGB image was
visually inspected before adaptation. Source/algorithm hashes and observed positions
are in the CPU replay assessment, which explicitly marks `new_capture=False`.

## Verification and remaining work

RED: the three new actual-observation/AA regressions failed against the accepted
baseline, exit 1 (`red.log`). Initial scoped GREEN: 54 passed, exit 0
(`green-initial.log`). Final targeted pytest: **54 passed**, exit 0, 22.28s
(`green.log`); scoped Ruff and mypy both exit 0 (`lint.log`, `mypy.log`). The two test paths are
`tests/test_opencv_target_evidence.py` and `tests/test_visual_effect_evidence.py`.

Root owns source-backed engineering sensor calibration and future clean `apply_scene`
captures. Required calibration shape: registered optical-z depth errors in metres,
positive finite bound tied to the actual sensor/noise/precision configuration,
intrinsics/extrinsics/calibration hash, episode/capture provenance and validated
coverage; observed top-plane intervals must intersect under that bound. Unknown
Gaussian noise is not converted into a fictional hard bound here. Registration,
RGB edge sampling and supported upright rigid-asset assumptions need independent
coverage validation as well. Continuous motion/symmetry evidence remains unavailable;
sampled endpoint consistency never enables completion. This handoff demonstrates CPU
adaptation to actual saved development pixels, not action success or full T7b DONE.
