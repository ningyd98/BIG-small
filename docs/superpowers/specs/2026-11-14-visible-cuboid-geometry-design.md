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

1. Depth: partition sorted measured heights only across an observed gap greater than
   either partition's spread and, when supplied, twice the calibrated depth bound.
   Require one cluster to contain every eroded RGB-interior pixel and at least eight
   measured points. A different interior cluster, higher foreground boundary cluster,
   missing depth or missing interior fails explicitly. Lower clusters must be boundary
   only. With a calibrated bound they must not lie below calibrated support; top-plane
   depth intervals must overlap. Without a supplied bound, extent/effects stay UNKNOWN.
   Never revert an unresolved split to the whole color mask as top. Preserve every
   original silhouette/depth sample in conservative outer bounds; do not synthesize depth.

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
