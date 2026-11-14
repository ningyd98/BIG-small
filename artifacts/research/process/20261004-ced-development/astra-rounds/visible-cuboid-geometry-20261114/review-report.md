# Whole-change review — original reviewer response

Model: gpt-6-astra. Agent: /root/review_visible_cuboid_geometry.
Reviewed snapshot: bab220435ab3211adc40b2916325edc28477a00f..fb4e05c0d11b4b9bdb5c2feaeeb4f97cfd1687ed.
This is the original pre-fix review. The final implementation was subsequently fixed
and verified by the author; no second review or final Astra approval is claimed.

---

**Readiness: not ready.** One Important correctness gap remains in the central repair. No Critical or separate Minor finding identified.

**Strengths**

- Rectangle validation uses observed pixels and retains hole, invalid-depth, exterior-ring and reference-size checks.
- Missing calibration still leaves metric extent and effects UNKNOWN.
- Invalid-depth diagnostics preserve refusal and explicitly avoid identifying a physical occluder.
- Entry source sealing includes both modified geometry modules and the newly imported `top_grasp.py` dependency.
- The regression suite covers useful rotated positives, isolated foreground/interior outliers and missing-color/depth cases.

**Important — unresolved single groups still become the whole top**

Verified location: `src/cloud_edge_robot_arm/vision/tracking.py:172`, with acceptance at lines 179–185.

The 8 mm span check executes only when `len(choices) > 1`. However, the partition algorithm can retain a highly nonplanar group whenever its largest gap does not exceed both remaining spreads. That single group is accepted wholesale without a bound. Foreground pixels included in that group also escape the boundary check, which examines only `~top`.

I reproduced both cases using the changed production module, with `PYTHONPATH=src:.` and bytecode disabled:

1. Start with `tests.test_visible_cuboid_geometry.cuboid()`.
2. Set all target depths, `[113:128,172:187]`, to `1.3125`.
3. Set two pixels to `1.28125` and `1.25`.
   - Interior case: `(y=116,x=175)` and `(116,176)`.
   - Boundary case: `(113,175)` and `(113,176)`.
4. Rebuild `RGBDObservation` with its checksum recalculated and invoke `track(observation)` without a bound.

Both return:

```text
target_visible = True
top_pixels = visible_pixels = 225
observed_top_height_span = 0.0625 m
extent_complete = False
```

The exact binary depths produce equal 31.25 mm gaps, so this is deterministic rather than floating-point noise. In the boundary case the core is perfectly flat; merely removing the `len(choices) > 1` condition would therefore be insufficient.

This leaves the whole-mask fallback behavior present for unresolved distributions and violates the explicit foreground/internal-anomaly review requirement. Metric qualification remains protected; I did not demonstrate unsafe actuation.

**Recommendation**

Require every nominated top—including a single unsplit group—to satisfy an explicit admission check over the entire selected support. An unresolved broad group must refuse. Add both reproductions as no-bound negative regressions with specific refusal reasons, while preserving the permitted small interior-perturbation case and calibrated interval behavior.

**Test assessment**

The new single-outlier negatives produce clean separable clusters and therefore miss this failure class. Add equal-gap/multilevel depth distributions rather than another isolated spike. The source snapshot test currently asserts tracking inclusion; explicitly asserting `top_grasp.py` inclusion would also protect the new dependency.

I confirmed pytest’s configured `pythonpath=["src", "."]`; the editable-install concern does not invalidate the parent’s pytest results. My reproduction printed the intended worktree module path. Diff whitespace verification passed. I did not rerun the broad suite.

**Declined to judge**

- Fresh MuJoCo occluder/table-edge controls, broad tests and type comparisons: being performed independently by the parent.
- Replay performance/generalization and the reported 11→21 recovery: archived cases are disclosed regression data, and I did not independently replay them.
- Hardware behavior, paid-model performance and formal qualification: no corresponding new evidence or authorized runs.
- Physical interpretation of invalid depth: deliberately remains UNKNOWN.
- Whether ≤8 mm interior variation represents actual noise or an obstacle: the accepted ruling permits provisional nomination; it does not establish a sensor bound.
- Arbitrary object shapes, tilted-camera operation and unrelated pre-existing planner/global issues: outside this fixed-camera upright-cuboid change.

No files, index, HEAD or branch were modified; no agents or paid/model calls were used.
