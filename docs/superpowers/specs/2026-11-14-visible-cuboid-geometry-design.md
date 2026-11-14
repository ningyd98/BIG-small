# Visible cuboid geometry repair

The user asked to start the complete repair after reviewing the frozen three-mechanism
diagnosis and repair order. Continue inline in the existing isolated research worktree.
Base: bab220435ab3211adc40b2916325edc28477a00f. Old inputs and failed trials stay frozen.

## Intent and approach

Recover supported small rotated colored cuboids without turning missing depth,
foreground occlusion or uncertainty into execution authority. Retain camera resolution,
marker, native/cloud model selection, controllers, action budgets and metric qualification.
A lower solidity threshold or higher render resolution would not fix the depth failure;
they are excluded. Use measured visible support and the existing half-pixel footprint.

1. Depth: use all measured eroded RGB-interior pixels as the top anchor. Require
   their height span to fit the existing 8mm top-grasp flatness admission without a
   sensor bound, or twice a supplied bound. A boundary point can nominate top support
   only if its height remains within that admission of every interior height.
   Require at least eight measured top points and validate the entire nominated top's
   span too. Any higher excluded boundary point, missing depth or missing interior
   refuses. Lower excluded points must be boundary only; with a calibrated bound
   they cannot lie below calibrated support. Calibrated top-plane depth intervals
   must overlap. Without a supplied bound, extent/effects stay UNKNOWN. The 8mm rule
   is an existing visibility/flatness admission, never an invented sensor error bound.
   Preserve every original silhouette/depth sample in conservative outer bounds;
   never synthesize depth or fall back to the whole mask after unresolved separation.

   The initial gap-based partition proposal was rejected during verification: equal
   gaps can hide multilevel anomalies and merge normal visible side levels. Explicit
   equal-gap negatives and side-level positives now pin the interior-anchor approach.

2. Contour: replace area/convex-hull >=0.95 with a rotated-rectangle interior support
   check, limited to the existing upright cuboid scope. minAreaRect fits observed pixel
   centers; project the existing half-pixel square onto each rectangle axis
   (0.5*(abs(axis.x)+abs(axis.y))). Every pixel center strictly inside that inset
   rectangle must already be observed color. Do not fill any pixels. Keep hole,
   original-depth, exterior-ring, identity, freshness and later size-consistency gates.
   Near/invalid/coplanar boundary evidence still rejects; the rectangle alone cannot
   prove a complete physical object. Record rectangle dimensions, inset and missing count.

3. Diagnosis: retain invalid-depth rejection and report boundary versus interior invalid
   pixels and adjacency to invalid exterior background. This is image evidence, not a
   claim of arm occlusion or table support. Offline reports keep actual table-edge/
   foreground-occlusion/normal-rotation controls separate. Missing original depth stops.

## Acceptance and limits

Positive tests cover several pixel sizes/yaws, calibrated and uncalibrated top supports,
visible lower sides and noisy background edge samples. Negative tests cover missing
interior color, foreground boundary depth, interior depth spikes, calibrated support
violations, invalid depth and ambiguous identity. Actual host MuJoCo occluder controls
must still reject. Replay all original 40 observations without changing their bytes;
old held-out cases are now disclosed regression data, not unseen qualification data.

Use real SQLite/worker/MuJoCo software integration with model-boundary fixtures; no
paid requests in development verification. After fixes and review, freeze a new exact
40-item matrix and source hashes. A new paid actual-model run needs its own concrete
request authorization. No hardware or formal research qualification is introduced.

Builder calls above are implementation choices within the user-selected repair order;
any ambiguity remains an explicit rejection, not an assumed completion.
